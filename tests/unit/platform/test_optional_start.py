import asyncio

import pytest

from discordbot.composition.config import Environment, PlatformConfig, RuntimePolicy, ServiceKind
from discordbot.composition.runtime import ProcessRuntime, RuntimeState, require_clean_shutdown
from discordbot.platform.errors import ShutdownError, StartupError
from discordbot.platform.health import HealthStatus


class Resource:
    def __init__(self, name, calls, *, required=True, fail=False):
        self.name, self.calls, self.required, self.fail = name, calls, required, fail
        self.active = False
        self.partial = False
        self.stops = 0

    async def start(self):
        self.calls.append('start:' + self.name)
        if self.fail:
            # Required resources already own failure rollback in the existing
            # contract; this fake has no retained state when required=True.
            self.partial = not self.required
            raise ValueError('synthetic-private-error')
        self.active = True

    async def stop(self):
        self.calls.append('stop:' + self.name)
        self.stops += 1
        self.partial = self.active = False


def runtime(*resources):
    return ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'test',
        runtime=RuntimePolicy(.5, .1)), resources=resources)


@pytest.mark.asyncio
@pytest.mark.parametrize('optional_before_failure', [False, True])
async def test_optional_failure_preserves_independent_survivors_and_closes_exactly_once(optional_before_failure):
    calls = []
    mandatory = Resource('mandatory', calls)
    optional = Resource('healthy-optional', calls, required=False)
    broken = Resource('broken', calls, required=False, fail=True)
    later = Resource('later', calls)
    survivors = (mandatory, optional) if optional_before_failure else (mandatory,)
    app = runtime(*survivors, broken, later)
    try:
        await asyncio.wait_for(app.start(), .4)
        assert app.state is RuntimeState.RUNNING and app.health.snapshot().ready
        assert all(item.active and not item.stops for item in (*survivors, later))
        assert not broken.partial and broken.stops == 1
        assert app._started_resources == [*survivors, later]
        assert app.health.snapshot().capabilities['broken'].status is HealthStatus.DOWN
        events = app.telemetry_buffer.drain()
        assert any(event.event == 'runtime.optional_start_failed' for event in events)
        assert 'synthetic-private-error' not in repr(events)
        require_clean_shutdown(await asyncio.wait_for(app.shutdown(), .4))
        require_clean_shutdown(await app.shutdown())
        assert all(item.stops == 1 for item in (*survivors, broken, later))
    finally:
        if app.state in (RuntimeState.RUNNING, RuntimeState.FAILED):
            await app.shutdown()


@pytest.mark.asyncio
async def test_all_resources_succeed_and_stop_in_reverse():
    calls = []
    a, b = Resource('required', calls), Resource('optional', calls, required=False)
    app = runtime(a, b)
    await app.start()
    assert app._started_resources == [a, b] and app.health.snapshot().ready
    require_clean_shutdown(await asyncio.wait_for(app.shutdown(), .4))
    assert calls == ['start:required', 'start:optional', 'stop:optional', 'stop:required']


@pytest.mark.asyncio
async def test_required_failure_still_rolls_back_survivors_and_never_becomes_ready():
    calls = []
    a, b = Resource('required', calls), Resource('broken', calls, fail=True)
    app = runtime(a, b)
    with pytest.raises(StartupError):
        await asyncio.wait_for(app.start(), .4)
    assert a.stops == 1 and not a.active
    assert not app.health.snapshot().ready
    assert app.health.snapshot().capabilities['broken'].status is HealthStatus.DOWN
    require_clean_shutdown(await asyncio.wait_for(app.shutdown(), .4))
    assert a.stops == 1


@pytest.mark.asyncio
async def test_adapter_owned_partial_cleanup_is_not_called_twice():
    calls = []
    class SelfCleaning(Resource):
        startup_cleanup_complete = False
        async def start(self):
            try:
                await super().start()
            except Exception:
                await self.stop()
                self.startup_cleanup_complete = True
                raise
    broken = SelfCleaning('optional', calls, required=False, fail=True)
    app = runtime(Resource('required', calls), broken)
    await app.start()
    require_clean_shutdown(await app.shutdown())
    assert broken.stops == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['resistant', 'exception', 'adapter-incomplete'])
async def test_incomplete_optional_cleanup_is_terminal_and_retains_dependencies(failure):
    calls, release = [], asyncio.Event()
    class Broken(Resource):
        async def stop(self):
            self.stops += 1
            if failure == 'exception':
                raise RuntimeError('synthetic cleanup failure')
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            self.partial = False
    broken = Broken('optional', calls, required=False, fail=True)
    if failure == 'adapter-incomplete':
        broken.startup_cleanup_complete = False
    mandatory = Resource('mandatory', calls)
    app = runtime(mandatory, broken)
    try:
        with pytest.raises(StartupError):
            await asyncio.wait_for(app.start(), .4)
        assert not app.health.snapshot().ready and app.state is RuntimeState.FAILED
        assert mandatory.active and mandatory.stops == 0
        assert app._partial_resources == [broken]
        assert broken.stops == (0 if failure == 'adapter-incomplete' else 1)
        report = await asyncio.wait_for(app.shutdown(), .4)
        with pytest.raises(ShutdownError):
            require_clean_shutdown(report)
        assert mandatory.stops == 0
    finally:
        release.set()
        if app.lifecycle.pending:
            await asyncio.wait_for(asyncio.gather(*app.lifecycle.pending, return_exceptions=True), 1)
        await app.executor.close()


@pytest.mark.asyncio
async def test_cancelled_optional_start_never_becomes_degraded_running():
    calls, entered = [], asyncio.Event()
    class Cancelled(Resource):
        async def start(self):
            self.partial = True
            entered.set()
            await asyncio.Event().wait()
    mandatory, optional = Resource('mandatory', calls), Cancelled('optional', calls, required=False)
    app = runtime(mandatory, optional)
    task = asyncio.create_task(app.start())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, .4)
    assert app.state is RuntimeState.FAILED and not app.health.snapshot().ready
    # A cancellation that has not yet been observed as complete stays owned;
    # no concurrent stop races it and dependencies are preserved in that case.
    report = await asyncio.wait_for(app.shutdown(), .4)
    if app._partial_resources:
        assert report.resource_errors and mandatory.stops == 0
    else:
        assert optional.stops == 1 and mandatory.stops == 1


@pytest.mark.asyncio
async def test_degraded_start_later_resistant_shutdown_remains_bounded():
    calls, release = [], asyncio.Event()
    class Owner(Resource):
        async def stop(self):
            self.stops += 1
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
    owner = Owner('mandatory', calls)
    broken = Resource('optional', calls, required=False, fail=True)
    app = runtime(owner, broken)
    try:
        await asyncio.wait_for(app.start(), .4)
        report = await asyncio.wait_for(app.shutdown(), .4)
        with pytest.raises(ShutdownError):
            require_clean_shutdown(report)
        assert broken.stops == 1 and owner.stops == 1
        assert await app.shutdown() == report
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(*app.lifecycle.pending, return_exceptions=True), 1)
