import asyncio
import threading

import pytest

from discordbot.composition.config import Environment, PlatformConfig, RuntimePolicy, ServiceKind
from discordbot.composition.runtime import ProcessRuntime, RuntimeState, require_clean_shutdown
from discordbot.platform.errors import ShutdownError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec


@pytest.mark.asyncio
async def test_resistant_work_returns_remaining_without_closing_its_dependency():
    release, started = asyncio.Event(), asyncio.Event()
    closed = []

    class Resource:
        name, required = 'dependency', True

        async def start(self):
            pass

        async def stop(self):
            closed.append(True)

    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'test',
        runtime=RuntimePolicy(1, .1)), resources=(Resource(),))
    await runtime.start()

    async def resistant():
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    work = runtime.supervisor.start(TaskSpec('resistant', 'test', 'one', 'one', 5,
        cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), resistant)
    await started.wait()
    shutdown = asyncio.create_task(runtime.shutdown())
    try:
        done, _ = await asyncio.wait({shutdown}, timeout=.4)
        assert done, 'shutdown exceeded its total application grace'
        report = shutdown.result()
        assert report.tasks.remaining == 1
        assert not closed and runtime.supervisor.snapshot().active
        assert runtime.state is RuntimeState.FAILED
        with pytest.raises(ShutdownError):
            require_clean_shutdown(report)
        assert await runtime.shutdown() == report
    finally:
        release.set()
        await asyncio.wait_for(work, 1)
        await asyncio.wait_for(shutdown, 1)
        await runtime.executor.close()


@pytest.mark.asyncio
async def test_cancelled_shutdown_caller_does_not_cancel_the_cleanup_owner():
    release, started = asyncio.Event(), asyncio.Event()
    stops = []

    class Resource:
        name, required = 'resource', True
        async def start(self):
            return
        async def stop(self):
            stops.append(True)
            started.set()
            await release.wait()

    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'test',
        runtime=RuntimePolicy(1, .1)), resources=(Resource(),))
    await runtime.start()
    caller = asyncio.create_task(runtime.shutdown())
    await started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    require_clean_shutdown(await runtime.shutdown())
    assert stops == [True]


@pytest.mark.asyncio
async def test_finite_thread_gets_remaining_grace_before_dependency_close():
    started, release = threading.Event(), threading.Event()
    stops = []

    class Resource:
        name, required = 'resource', True
        async def start(self):
            return
        async def stop(self):
            assert runtime.executor.admitted == 0
            stops.append(True)

    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'test',
        runtime=RuntimePolicy(1, .2)), resources=(Resource(),))
    await runtime.start()
    def block():
        started.set()
        release.wait(1)
    work = runtime.supervisor.start(TaskSpec('finite', 'test', 'one', 'one', 2,
        cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), lambda: runtime.executor.run(block))
    try:
        while not started.is_set():
            await asyncio.sleep(.001)
        asyncio.get_running_loop().call_later(.02, release.set)
        require_clean_shutdown(await runtime.shutdown())
        assert stops == [True] and work.cancelled()
    finally:
        release.set()
        await runtime.executor.close(grace_seconds=1)


@pytest.mark.asyncio
async def test_resistant_resource_retains_ownership_and_does_not_close_next_dependency():
    release, started = asyncio.Event(), asyncio.Event()
    calls = []

    class Resource:
        required = True

        def __init__(self, name):
            self.name = name

        async def start(self):
            pass

        async def stop(self):
            calls.append(self.name)
            if self.name == 'owner':
                started.set()
                while not release.is_set():
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        continue

    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'test',
        runtime=RuntimePolicy(1, .1)), resources=(Resource('dependency'), Resource('owner')))
    await runtime.start()
    task = asyncio.create_task(runtime.shutdown())
    try:
        await asyncio.wait_for(started.wait(), 1)
        done, _ = await asyncio.wait({task}, timeout=.4)
        assert done, 'resistant resource exceeded application grace'
        with pytest.raises(ShutdownError):
            require_clean_shutdown(task.result())
        assert calls == ['owner']
        assert runtime._started_resources
    finally:
        release.set()
        await asyncio.wait_for(task, 1)
        await asyncio.sleep(.01)
        await runtime.executor.close()
