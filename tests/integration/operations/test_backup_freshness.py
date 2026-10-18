"""Backup metadata observations must never outlive their sampling lifecycle."""
import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from discordbot.operations.adapters import probe as module
from discordbot.platform.errors import DatabaseUnavailableError


@pytest_asyncio.fixture
async def harness(monkeypatch):
    now = [100000.0]
    metadata = [99900.0]
    pending, futures, stats = [], [], []

    def start(spec, factory):
        future = asyncio.get_running_loop().create_future()
        futures.append(future)
        pending.append((factory, future))
        return future

    def stat():
        stats.append(now[0])
        if isinstance(metadata[0], BaseException):
            raise metadata[0]
        return SimpleNamespace(st_mtime=metadata[0])

    async def run(work):
        return work()

    runtime = SimpleNamespace(
        clock=SimpleNamespace(monotonic=lambda: now[0] - 100000,
                              now=lambda: datetime.fromtimestamp(now[0], timezone.utc)),
        metrics=SimpleNamespace(increment=lambda *a, **kw: None, dropped_series=0),
        telemetry=SimpleNamespace(emit=lambda *a, **kw: None),
        telemetry_buffer=SimpleNamespace(dropped_count=0), executor=SimpleNamespace(run=run),
        supervisor=SimpleNamespace(start=start, capacity=10, snapshot=lambda: SimpleNamespace(active=[])))
    database = SimpleNamespace(probe=AsyncMock(), observations=[], admitted=(0, 0))
    probe = module.Probe(database, runtime, SimpleNamespace(stat=stat))
    probe.database_ready = True
    monkeypatch.setattr(module, "asyncio", SimpleNamespace(sleep=AsyncMock(), gather=asyncio.gather))

    async def sample():
        factory, future = pending.pop(0)
        await factory()
        future.set_result(None)
        await asyncio.sleep(0)

    try:
        yield SimpleNamespace(probe=probe, database=database, runtime=runtime, now=now,
                              metadata=metadata, pending=pending, futures=futures, stats=stats, sample=sample)
    finally:
        await probe.stop()
        assert all(future.done() for future in futures)
        pending.clear()


def unknown(probe):
    gauges = probe.gauges()
    assert gauges['backup_age_seconds'] == -1
    assert gauges['backup_rpo_exceeded'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', [False, True])
async def test_elapsed_time_publication_and_probe_count(harness, terminal):
    h = harness
    h.probe.schedule()
    try:
        await h.sample()
        assert h.probe.gauges()['backup_age_seconds'] == 100
        if terminal:
            h.database.probe.side_effect = DatabaseUnavailableError('synthetic')
            await h.sample()
            assert h.probe.policy.hard and not h.probe.ready()
            unknown(h.probe)
        calls, stats = h.database.probe.await_count, len(h.stats)
        h.now[0] += 7 * 3600
        if terminal:
            unknown(h.probe)
            h.probe.schedule()
            assert not h.pending
        else:
            assert h.probe.gauges()['backup_age_seconds'] == 25300
            assert h.probe.gauges()['backup_rpo_exceeded'] == 1
        h.metadata[0] = h.now[0]
        # Reading gauges never issues a stat, DB request or task, even after publish.
        for _ in range(3):
            if terminal:
                unknown(h.probe)
            else:
                assert h.probe.gauges()['backup_age_seconds'] == 25300
        assert h.database.probe.await_count == calls and len(h.stats) == stats
        if not terminal:
            await h.sample()
            assert h.probe.gauges()['backup_age_seconds'] == 0
            assert h.probe.gauges()['backup_rpo_exceeded'] == 0 and h.probe.ready()
        else:
            assert h.probe.policy.hard and not h.probe.ready()
    finally:
        await h.probe.stop()
    assert all(f.done() for f in h.futures)
    unknown(h.probe)


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [FileNotFoundError(), PermissionError(), float('nan'),
                                     float('inf'), float('-inf'), None, 'invalid', True])
@pytest.mark.parametrize('terminal', [False, True])
async def test_missing_invalid_metadata_never_keeps_previous_safe_value(harness, invalid, terminal):
    h = harness
    h.probe.schedule()
    try:
        await h.sample()
        assert h.probe.gauges()['backup_rpo_exceeded'] == 0
        h.metadata[0] = invalid
        if terminal:
            h.database.probe.side_effect = DatabaseUnavailableError('synthetic')
        await h.sample()
        unknown(h.probe)
        assert h.database.probe.await_count == 2
        assert h.probe.policy.hard is terminal
        if not terminal:
            assert h.probe.ready()  # A metadata failure does not change DB readiness.
            h.metadata[0] = h.now[0]
            await h.sample()
            assert h.probe.gauges()['backup_age_seconds'] == 0
    finally:
        await h.probe.stop()
    assert all(f.done() for f in h.futures)


@pytest.mark.asyncio
@pytest.mark.parametrize('end', ['cancel', 'exception', 'stop'])
async def test_sampling_termination_invalidates_metrics_without_restart(harness, end):
    h = harness
    unknown(h.probe)
    h.probe.schedule()
    await h.sample()
    assert h.probe.gauges()['backup_age_seconds'] == 100
    if end == 'cancel':
        h.probe.task.cancel()
    elif end == 'exception':
        h.probe.task.set_exception(RuntimeError('synthetic'))
    else:
        await h.probe.stop()
    await asyncio.sleep(0)
    unknown(h.probe)
    assert len(h.futures) == 2 and h.database.probe.await_count == 1
    await h.probe.stop()
    h.probe.schedule()
    assert len(h.futures) == 2 and all(f.done() for f in h.futures)


@pytest.mark.asyncio
async def test_shutdown_during_metadata_sampling_cancels_and_drains(harness):
    h = harness
    entered = asyncio.Event()

    async def blocked(work):
        entered.set()
        await asyncio.Event().wait()

    h.probe.schedule()
    await h.sample()
    h.runtime.executor.run = blocked
    factory, placeholder = h.pending.pop(0)
    placeholder.cancel()
    task = asyncio.create_task(factory())
    h.probe.task = task
    try:
        await entered.wait()
        await h.probe.stop()
        assert task.cancelled() and h.probe.closed
        unknown(h.probe)
        h.probe.schedule()
        assert len(h.futures) == 2 and h.database.probe.await_count == 2
    finally:
        await h.probe.stop()
    assert all(f.done() for f in h.futures)


@pytest.mark.asyncio
@pytest.mark.parametrize('age,rpo', [(0, 0), (21600, 0), (21600.001, 1), (-100, 0)])
async def test_existing_rpo_threshold_and_future_mtime_clamp(harness, age, rpo):
    h = harness
    h.metadata[0] = h.now[0] - age
    h.probe.schedule()
    try:
        await h.sample()
        assert h.probe.gauges()['backup_age_seconds'] == pytest.approx(max(0, age))
        assert h.probe.gauges()['backup_rpo_exceeded'] == rpo
    finally:
        await h.probe.stop()


@pytest.mark.asyncio
async def test_no_metadata_configured_is_unknown(harness):
    h = harness
    h.probe.backup_latest = None
    h.probe.schedule()
    try:
        await h.sample()
        unknown(h.probe)
        assert not h.stats and h.probe.ready()
    finally:
        await h.probe.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', [False, True])
async def test_temporary_metadata_replacement_and_removal(harness, tmp_path, terminal):
    h = harness
    latest = tmp_path / 'latest.json'
    latest.write_text('{}', encoding='utf8')
    os.utime(latest, (99900, 99900))
    h.probe.backup_latest = latest
    h.probe.schedule()
    try:
        await h.sample()
        assert h.probe.gauges()['backup_age_seconds'] == 100
        if terminal:
            h.database.probe.side_effect = DatabaseUnavailableError('synthetic')
            await h.sample()
        replacement = tmp_path / 'replacement.json'
        replacement.write_text('{}', encoding='utf8')
        os.utime(replacement, (100000, 100000))
        replacement.replace(latest)
        if terminal:
            unknown(h.probe)
        else:
            await h.sample()
            assert h.probe.gauges()['backup_age_seconds'] == 0
        latest.unlink()
        if not terminal:
            await h.sample()
        unknown(h.probe)
        assert h.database.probe.await_count == (2 if terminal else 3)
    finally:
        await h.probe.stop()


@pytest.mark.asyncio
async def test_latched_health_endpoints_remain_live_but_not_ready(harness):
    import httpx
    from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
    from discordbot.composition.runtime import ProcessRuntime
    from discordbot.operations.adapters.hosting import health_app

    h = harness
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'synthetic'))
    await runtime.start()
    h.probe.schedule()
    try:
        await h.sample()
        h.database.probe.side_effect = DatabaseUnavailableError('synthetic')
        await h.sample()
        app = health_app(runtime, h.probe.ready, h.probe.gauges)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
            assert (await client.get('/health/live')).status_code == 200
            assert (await client.get('/health/ready')).status_code == 503
            metrics = (await client.get('/metrics')).text
            assert 'backup_age_seconds -1.0' in metrics
            assert 'backup_rpo_exceeded 1.0' in metrics
        assert h.database.probe.await_count == 2 and not h.pending
    finally:
        await h.probe.stop()
        await runtime.shutdown()
