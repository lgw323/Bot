import asyncio
from contextlib import closing
import sqlite3
import threading
from unittest.mock import AsyncMock

import pytest

from discordbot.platform.errors import CapacityError, ConflictError, DatabaseUnavailableError


@pytest.mark.asyncio
async def test_cancel_between_receipt_and_xp_commit_rolls_back_both(service, database, clock, monkeypatch):
    from discordbot.engagement.adapters import event_repository
    original = event_repository._progress
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def hold(conn, *args, **kwargs):
        original(conn, *args, **kwargs)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    monkeypatch.setattr(event_repository, "_progress", hold)
    task = asyncio.create_task(service.message(100, 10, "cancelled", "가", clock.now()))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    await database.write(service.request(), lambda conn: None)
    assert (await service.profile(100, 10)).total == 0
    monkeypatch.setattr(event_repository, "_progress", original)
    assert await service.message(100, 10, "cancelled", "가", clock.now())
    assert (await service.profile(100, 10)).total == 2


@pytest.mark.asyncio
async def test_failed_voice_observation_stops_extrapolation_at_shutdown(service, database, clock):
    await service.voice(100, 10, "gateway", 1, 1001, False)
    clock.advance(61)
    await service.voice(100, 10, "gateway", 2, 1002, False)
    with closing(sqlite3.connect(database.config.path, isolation_level=None)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        clock.advance(30)
        with pytest.raises(DatabaseUnavailableError):
            await service.voice(100, 10, "gateway", 3, 1002, True)
        lock.rollback()
    clock.advance(300)
    with pytest.raises(ConflictError):
        await service.voice(100, 10, "gateway", 4, None, False)
    await service.stop()
    assert (await service.repository.get_member(100, 10, service.request())).total_vc_seconds == 61


@pytest.mark.asyncio
async def test_duplicate_voice_transition_racing_leave_and_shutdown_has_one_credit(service, clock):
    await service.voice(100, 10, "gateway", 1, 1001, False)
    clock.advance(125)
    results = await asyncio.gather(*(service.voice(100, 10, "gateway", 2, None, False) for _ in range(8)))
    assert sum(results) == 1
    await service.stop()
    assert (await service.repository.get_member(100, 10, service.request())).total_vc_seconds == 125


@pytest.mark.asyncio
async def test_closed_admission_rejects_messages_and_commands(service, clock):
    await service.stop()
    with pytest.raises(ConflictError):
        await service.message(100, 10, "late", "text", clock.now())
    with pytest.raises(ConflictError):
        await service.register_birthday(42, 100, 10, 1, 1)


@pytest.mark.asyncio
async def test_notification_query_failure_is_retryable_before_claim(service, monkeypatch):
    await service.register_birthday(42, 100, 10, 2, 29)
    read = service.events.birthdays
    monkeypatch.setattr(service.events, "birthdays", AsyncMock(side_effect=DatabaseUnavailableError("busy")))
    delivery = AsyncMock()
    with pytest.raises(DatabaseUnavailableError):
        await service.notify_guild(100, 1001, delivery)
    delivery.send.assert_not_awaited()
    monkeypatch.setattr(service.events, "birthdays", read)
    assert await service.notify_guild(100, 1001, delivery)
    assert delivery.send.await_count == 1


@pytest.mark.asyncio
async def test_scheduler_capacity_failure_creates_no_orphan(service, clock):
    from discordbot.engagement.adapters.scheduler import BirthdayScheduler
    from discordbot.platform.tasks import TaskSpec, TaskSupervisor
    supervisor = TaskSupervisor(capacity=1, history_capacity=4, clock=clock)
    hold = asyncio.Event()
    supervisor.start(TaskSpec("occupied", "test", "synthetic", "test", 5), hold.wait)
    scheduler = BirthdayScheduler(service, AsyncMock(), supervisor)
    with pytest.raises(CapacityError):
        scheduler.start()
    await scheduler.stop()
    assert len(supervisor.snapshot().active) == 1
    await supervisor.shutdown(grace_seconds=0)
    assert not supervisor.snapshot().active
