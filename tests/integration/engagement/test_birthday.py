import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from discordbot.engagement.adapters.scheduler import BirthdayScheduler
from discordbot.platform.errors import AuthorizationError, ExternalTemporaryError, ValidationError
from discordbot.platform.tasks import TaskSupervisor


@pytest.mark.asyncio
async def test_birthday_master_calendar_delete_and_guild_scope(service):
    with pytest.raises(AuthorizationError):
        await service.register_birthday(7, 100, 10, 1, 1)
    with pytest.raises(AuthorizationError):
        await service.delete_birthday(7, 100, 10)
    with pytest.raises(ValidationError):
        await service.register_birthday(42, 100, 10, 2, 31)
    assert await service.repository.get_member(100, 10, service.request()) is None
    await service.register_birthday(42, 100, 10, 2, 29)
    await service.register_birthday(42, 200, 10, 12, 31)
    assert (await service.birthdays(100))[0].birth_day == 29
    assert (await service.birthdays(200))[0].birth_month == 12
    assert await service.delete_birthday(42, 100, 10)
    assert await service.birthdays(100) == ()
    assert len(await service.birthdays(200)) == 1
    assert await service.delete_birthday(42, 100, 10)  # V1 counts existing user row, even null birthday.
    assert not await service.delete_birthday(42, 100, 11)


@pytest.mark.asyncio
async def test_daily_nine_kst_feb28_and_feb29_once_per_guild_across_restart(service, clock):
    await service.register_birthday(42, 100, 10, 2, 29)
    await service.register_birthday(42, 100, 11, 2, 28)
    await service.register_birthday(42, 200, 10, 2, 29)
    clock.wall = datetime(2027, 2, 27, 23, 59, 59, tzinfo=timezone.utc)
    delivery = AsyncMock()
    assert not await service.notify_guild(100, 1001, delivery)
    clock.advance(1)
    results = await asyncio.gather(*(service.notify_guild(100, 1001, delivery) for _ in range(4)))
    assert sum(results) == 1
    delivery.send.assert_awaited_once_with(100, 1001, (11, 10))
    supervisor = TaskSupervisor(capacity=2, history_capacity=8, clock=clock)
    restarted = BirthdayScheduler(service, delivery, supervisor)
    await restarted.tick()
    assert delivery.send.await_count == 2
    assert delivery.send.call_args.args == (200, 2001, (10,))
    await restarted.tick()
    assert delivery.send.await_count == 2
    clock.wall = datetime(2028, 2, 28, 0, tzinfo=timezone.utc)
    await restarted.tick()
    assert delivery.send.call_args.args == (100, 1001, (11,))
    clock.wall = datetime(2028, 2, 29, 0, tzinfo=timezone.utc)
    await restarted.tick()
    assert delivery.send.call_args.args == (200, 2001, (10,))
    await supervisor.shutdown(grace_seconds=0)


@pytest.mark.asyncio
async def test_uncertain_send_and_post_send_db_failure_never_duplicate(service, monkeypatch):
    await service.register_birthday(42, 100, 10, 2, 29)
    delivery = AsyncMock()
    delivery.send.side_effect = OSError("synthetic transport")
    with pytest.raises(ExternalTemporaryError):
        await service.notify_guild(100, 1001, delivery)
    delivery.send.side_effect = None
    assert not await service.notify_guild(100, 1001, delivery)
    assert delivery.send.await_count == 1
    await service.register_birthday(42, 200, 10, 2, 29)
    from discordbot.platform.errors import DatabaseUnavailableError
    monkeypatch.setattr(service.events, "finish_birthday", AsyncMock(side_effect=DatabaseUnavailableError("injected ack loss")))
    with pytest.raises(DatabaseUnavailableError):
        await service.notify_guild(200, 2001, delivery)
    assert not await service.notify_guild(200, 2001, delivery)
    assert delivery.send.await_count == 2


@pytest.mark.asyncio
async def test_cancel_in_flight_send_keeps_durable_claim(service):
    await service.register_birthday(42, 100, 10, 2, 29)
    started = asyncio.Event()
    forever = asyncio.Event()
    async def blocked(*args):
        started.set()
        await forever.wait()
    delivery = AsyncMock()
    delivery.send.side_effect = blocked
    task = asyncio.create_task(service.notify_guild(100, 1001, delivery))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not await service.notify_guild(100, 1001, delivery)
    assert delivery.send.await_count == 1


@pytest.mark.asyncio
async def test_supervised_clock_repeated_start_hour_handover_and_shutdown(service, clock):
    supervisor = TaskSupervisor(capacity=2, history_capacity=8, clock=clock)
    sleeping = asyncio.Event()
    hold = asyncio.Event()
    calls = 0
    async def fake_sleep(seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            clock.advance(3600)
        else:
            sleeping.set()
            await hold.wait()
    scheduler = BirthdayScheduler(service, AsyncMock(), supervisor, sleep=fake_sleep)
    scheduler.start()
    scheduler.start()
    await asyncio.wait_for(sleeping.wait(), 2)
    assert len(supervisor.snapshot().active) <= 2
    await scheduler.stop()
    assert not supervisor.snapshot().active
    assert len(supervisor.snapshot().observations) <= 8
    await supervisor.shutdown(grace_seconds=0)
