"""Independent M4 observations through real tasks, executor, files and ASGI HTTP.

Only the five-second sleep is replaced by an explicit permit; no network/server.
The actual supervisor owns sample tasks, callbacks and shutdown. DB is synthetic.
"""
import asyncio
from datetime import datetime, timezone
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.runtime import ProcessRuntime, require_clean_shutdown
from discordbot.operations.adapters import probe as module
from discordbot.operations.adapters.hosting import health_app
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.storage.ports.contracts import DatabaseState


@pytest_asyncio.fixture
async def rig(tmp_path, monkeypatch):
    now = [100000.0]
    clock = SimpleNamespace(now=lambda: datetime.fromtimestamp(now[0], timezone.utc),
                            monotonic=lambda: now[0] - 100000)
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST,
                                                   'a8v4-synthetic'), clock=clock)
    latest = tmp_path / 'latest.json'
    latest.write_text('{}', encoding='utf8')
    os.utime(latest, (99900, 99900))
    permits = asyncio.Queue()
    async def tick(delay):
        assert delay == 5
        await permits.get()
    monkeypatch.setattr(module, 'asyncio', SimpleNamespace(sleep=tick, gather=asyncio.gather))
    db = SimpleNamespace(inspect=AsyncMock(return_value=SimpleNamespace(
        state=DatabaseState.VALID, migration_version=5)), probe=AsyncMock(),
        observations=[], admitted=(0, 0))
    probe = module.Probe(db, runtime, latest)
    await runtime.start()
    await probe.start()
    async def sample(error=None):
        now[0] += 5
        db.probe.side_effect = error
        previous = probe.task
        permits.put_nowait(None)
        await asyncio.wait_for(asyncio.shield(previous), 2)
        await asyncio.sleep(0)
    app = health_app(runtime, probe.ready, probe.gauges)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
        async def metrics():
            response = await client.get('/metrics')
            assert response.status_code == 200
            return {line.split()[0]: float(line.split()[1]) for line in response.text.splitlines()}
        try:
            yield SimpleNamespace(probe=probe, db=db, runtime=runtime, now=now, latest=latest,
                                  sample=sample, metrics=metrics, client=client, permits=permits)
        finally:
            await probe.stop()
            require_clean_shutdown(await runtime.shutdown())
            assert not runtime.supervisor.snapshot().active
            assert runtime.executor.admitted == 0


@pytest.mark.asyncio
async def test_http_clock_boundary_atomic_replace_and_removal(rig):
    h = rig
    assert (await h.metrics())['backup_age_seconds'] == -1
    await h.sample()
    assert (await h.client.get('/health/ready')).status_code == 200
    assert (await h.metrics())['backup_age_seconds'] == 105
    calls = h.db.probe.await_count
    h.now[0] = 99900 + 21600
    assert (await h.metrics())['backup_rpo_exceeded'] == 0
    h.now[0] += 1
    assert (await h.metrics())['backup_age_seconds'] == 21601
    assert (await h.metrics())['backup_rpo_exceeded'] == 1
    replacement = h.latest.with_name('new.json')
    replacement.write_text('{}', encoding='utf8')
    os.utime(replacement, (h.now[0], h.now[0]))
    replacement.replace(h.latest)
    assert (await h.metrics())['backup_age_seconds'] == 21601
    assert h.db.probe.await_count == calls
    await h.sample()
    assert (await h.metrics())['backup_age_seconds'] == 5
    h.latest.unlink()
    await h.sample()
    observed = await h.metrics()
    assert (observed['backup_age_seconds'], observed['backup_rpo_exceeded']) == (-1, 1)
    assert (await h.client.get('/health/ready')).status_code == 200


@pytest.mark.asyncio
async def test_http_classified_busy_recurrence_and_unobserved_publication(rig):
    h = rig
    busy = DatabaseUnavailableError('synthetic', context=dict(operation='select1_probe',
        stage='probe_configure', exception_family='sqlite_operational', sqlite_errorcode=5,
        sqlite_family='busy', connection_opened=True, close_succeeded=True, cleanup_failed=False))
    for error in (busy, None, None, busy):
        await h.sample(error)
    assert h.probe.policy.hard and h.db.probe.await_count == 4
    assert h.probe.task.done() and not h.runtime.supervisor.snapshot().active
    h.now[0] += 7 * 3600
    h.latest.write_text('{malformed synthetic metadata', encoding='utf8')
    os.utime(h.latest, (h.now[0], h.now[0]))
    for removed in (False, True):
        if removed:
            h.latest.unlink()
        observed = await h.metrics()
        assert (observed['backup_age_seconds'], observed['backup_rpo_exceeded']) == (-1, 1)
        assert (await h.client.get('/health/live')).json()['live'] is True
        assert (await h.client.get('/health/ready')).status_code == 503
        h.probe.schedule()
        assert h.db.probe.await_count == 4 and not h.runtime.supervisor.snapshot().active


@pytest.mark.asyncio
@pytest.mark.parametrize('end', ['cancel', 'exception', 'stop', 'runtime_shutdown'])
async def test_real_task_termination_is_unknown_over_http(rig, end):
    h = rig
    await h.sample()
    assert (await h.metrics())['backup_rpo_exceeded'] == 0
    if end == 'cancel':
        h.probe.task.cancel()
        await asyncio.gather(h.probe.task, return_exceptions=True)
    elif end == 'exception':
        with pytest.raises(RuntimeError, match='synthetic'):
            await h.sample(RuntimeError('synthetic'))
    elif end == 'stop':
        await h.probe.stop()
    else:
        require_clean_shutdown(await h.runtime.shutdown())
    await asyncio.sleep(0)
    calls = h.db.probe.await_count
    h.now[0] += 7 * 3600
    observed = await h.metrics()
    assert (observed['backup_age_seconds'], observed['backup_rpo_exceeded']) == (-1, 1)
    assert (await h.client.get('/health/ready')).status_code == 503
    assert not h.runtime.supervisor.snapshot().active and h.db.probe.await_count == calls


@pytest.mark.asyncio
async def test_malformed_json_is_only_local_mtime_observation_not_backup_validation(rig):
    h = rig
    h.latest.write_text('not JSON', encoding='utf8')
    os.utime(h.latest, (99900, 99900))
    await h.sample()
    observed = await h.metrics()
    # C15's existing signal is local mtime, not metadata parsing or restore proof.
    assert (observed['backup_age_seconds'], observed['backup_rpo_exceeded']) == (105, 0)
    assert h.db.probe.await_count == 1
