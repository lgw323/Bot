import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.discord_app import build_discord_runtime
from discordbot.composition.runtime import require_clean_shutdown
from discordbot.platform.errors import StartupError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseDeadlineError, DatabaseRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [False, True])
async def test_real_database_resource_gates_next_capability_and_readiness(legacy_db, tmp_path, valid):
    path = legacy_db if valid else tmp_path / "empty.db"
    if not valid:
        path.touch()
    db = SqliteDatabase(DatabaseConfig(path))
    feature = AsyncMock()
    feature.name = "synthetic-feature"
    feature.required = True
    config = PlatformConfig(service=ServiceKind.DISCORD_BOT, environment=Environment.TEST, release="data-test")
    runtime = build_discord_runtime(config, resources=(db, feature))
    if valid:
        await runtime.start()
        feature.start.assert_awaited_once()
        assert runtime.health.ready_payload()["ready"]
    else:
        with pytest.raises(StartupError):
            await runtime.start()
        feature.start.assert_not_awaited()
        assert not runtime.health.ready_payload()["ready"]
        assert path.read_bytes() == b""
    require_clean_shutdown(await runtime.shutdown())
    assert db.admitted == (0, 0)


@pytest.mark.asyncio
async def test_waiting_deadline_cannot_execute_a_late_mutation(database):
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    called = False
    def hold(conn):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    def queued(conn):
        nonlocal called
        called = True
    first = asyncio.create_task(database.write(DatabaseRequest.within(5), hold))
    try:
        await asyncio.wait_for(started.wait(), 2)
        with pytest.raises(DatabaseDeadlineError) as failure:
            await database.write(DatabaseRequest.within(0.03), queued)
        assert failure.value.retryable is False
    finally:
        release.set()
        await first
    await database.write(DatabaseRequest.within(5), lambda conn: None)
    assert not called and database.admitted == (0, 0)
