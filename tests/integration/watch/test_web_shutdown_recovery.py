"""Partial startup and shutdown failures keep independent owners reclaimable."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.platform.errors import DataIntegrityError, DatabaseUnavailableError, ShutdownError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.web_runtime import WatchWebResource


async def resource_fixture(tmp_path, clock, *, missing=False):
    database = SqliteDatabase(DatabaseConfig(tmp_path / 'synthetic-cleanup.db'))
    if not missing:
        await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    metadata = SimpleNamespace(start=AsyncMock(), close=AsyncMock())
    telemetry = TelemetryEmitter(buffer=TelemetryBuffer(32), clock=clock,
        service='watch-web', environment='test', release='synthetic')
    resource = WatchWebResource(database, 'https://watch.example.test',
        'synthetic-capability-secret-32-characters', 'synthetic-control-secret-32-characters',
        clock, telemetry, metadata=metadata)
    return resource, database, metadata


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['injected', 'missing'])
async def test_database_start_failure_preserves_error_and_completes_cleanup(tmp_path, clock, mode):
    resource, database, metadata = await resource_fixture(tmp_path, clock, missing=mode == 'missing')
    original = DatabaseUnavailableError('synthetic start failure')
    if mode == 'injected':
        database.start = AsyncMock(side_effect=original)
    resource.service.writer.release = AsyncMock()
    try:
        with pytest.raises(DatabaseUnavailableError if mode == 'injected' else DataIntegrityError) as captured:
            await resource.start()
        if mode == 'injected':
            assert captured.value is original
        assert resource.startup_cleanup_complete and database._closed
        metadata.close.assert_awaited_once()
        resource.service.writer.release.assert_not_awaited()
        await resource.stop()
        metadata.close.assert_awaited_once()
    finally:
        await database.stop()
        await metadata.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['metadata', 'writer'])
@pytest.mark.parametrize('cancelled', [False, True])
async def test_partial_start_keeps_original_when_metadata_cleanup_fails(tmp_path, clock, stage, cancelled):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    original = asyncio.CancelledError() if cancelled else RuntimeError('synthetic original start error')
    if stage == 'metadata':
        metadata.start.side_effect = original
    else:
        resource.service.writer.start = AsyncMock(side_effect=original)
    metadata.close.side_effect = RuntimeError('synthetic metadata cleanup error')
    try:
        with pytest.raises(type(original)) as captured:
            await resource.start()
        assert captured.value is original
        assert database._closed
        assert not resource.startup_cleanup_complete
        metadata.close.side_effect = None
        await resource.stop()
        assert resource.startup_cleanup_complete
    finally:
        metadata.close.side_effect = None
        await resource.service.stop()
        await database.stop()


@pytest.mark.asyncio
async def test_release_failure_closes_metadata_preserves_database_and_retries(tmp_path, clock):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    original_release = resource.service.writer.release
    original = DatabaseUnavailableError('synthetic release failure')
    release = resource.service.writer.release = AsyncMock(side_effect=original)
    try:
        await resource.start()
        with pytest.raises(DatabaseUnavailableError) as captured:
            await resource.stop()
        assert captured.value is original
        metadata.close.assert_awaited_once()
        assert not database._closed  # lease release still needs this dependency
        assert not resource.service.supervisor.snapshot().active
        assert not resource.startup_cleanup_complete
        release.side_effect = original_release
        await resource.stop()
        await resource.stop()
        assert release.await_count == 2 and database._closed
        metadata.close.assert_awaited_once()
        assert resource.startup_cleanup_complete
    finally:
        resource.service.writer.release = original_release
        await database.stop()
        await metadata.close()


@pytest.mark.asyncio
async def test_metadata_close_failure_does_not_block_database_close(tmp_path, clock):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    original = RuntimeError('synthetic metadata close failure')
    release = resource.service.writer.release = AsyncMock(wraps=resource.service.writer.release)
    try:
        await resource.start()
        metadata.close.side_effect = original
        with pytest.raises(RuntimeError) as captured:
            await resource.stop()
        assert captured.value is original and database._closed
        release.assert_awaited_once()
        metadata.close.side_effect = None
        await resource.stop()
        assert resource.startup_cleanup_complete
        release.assert_awaited_once()  # no DB access on retry after DB closure
    finally:
        metadata.close.side_effect = None
        await database.stop()
        await metadata.close()


@pytest.mark.asyncio
async def test_database_close_failure_retries_database_only(tmp_path, clock):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    original_stop = database.stop
    release = resource.service.writer.release = AsyncMock(wraps=resource.service.writer.release)
    original = RuntimeError('synthetic DB stop failure')
    try:
        await resource.start()
        database.stop = AsyncMock(side_effect=original)
        with pytest.raises(RuntimeError) as captured:
            await resource.stop()
        assert captured.value is original
        metadata.close.assert_awaited_once()
        database.stop.side_effect = original_stop
        await resource.stop()
        assert resource.startup_cleanup_complete and database._closed
        release.assert_awaited_once()
        metadata.close.assert_awaited_once()
    finally:
        await original_stop()
        await metadata.close()


@pytest.mark.asyncio
async def test_cancel_during_metadata_close_still_closes_database_then_retry(tmp_path, clock):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    entered = asyncio.Event()
    async def stall() -> None:
        entered.set()
        await asyncio.Event().wait()
    task = None
    try:
        await resource.start()
        metadata.close.side_effect = stall
        task = asyncio.create_task(resource.stop())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert database._closed
        metadata.close.side_effect = None
        await resource.stop()
        assert resource.startup_cleanup_complete
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        metadata.close.side_effect = None
        await database.stop()
        await metadata.close()


@pytest.mark.asyncio
async def test_unfinished_work_preserves_database_and_metadata_then_retry(tmp_path, clock, monkeypatch):
    resource, database, metadata = await resource_fixture(tmp_path, clock)
    entered, release = asyncio.Event(), asyncio.Event()
    async def hostile() -> None:
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
    original_shutdown = resource.service.supervisor.shutdown
    async def bounded(**kwargs):
        return await original_shutdown(grace_seconds=.01)
    monkeypatch.setattr(resource.service.supervisor, 'shutdown', bounded)
    task = None
    try:
        await resource.start()
        task = resource.service.supervisor.start(TaskSpec('hostile', 'test', 'one', 'one', 5,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), hostile)
        await entered.wait()
        with pytest.raises(ShutdownError):
            await resource.stop()
        assert not database._closed
        metadata.close.assert_not_awaited()
        release.set()
        await task
        await resource.stop()
        assert database._closed and resource.startup_cleanup_complete
    finally:
        release.set()
        if task is not None:
            await task
        await database.stop()
        await metadata.close()
