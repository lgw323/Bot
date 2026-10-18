"""A4-M2: drain admitted observations, including their failure, before flush."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import threading
from unittest.mock import AsyncMock

import pytest

from discordbot.engagement.domain.policy import Progress
from discordbot.engagement.ports.events import VoicePresence
from discordbot.platform.errors import ConflictError, DatabaseUnavailableError, ShutdownError


@asynccontextmanager
async def held_writer(database, service, monkeypatch):
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    tasks = []

    def hold(conn):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)

    tasks.append(asyncio.create_task(database.write(service.request(), hold)))
    queued = asyncio.Queue()
    original_write = database.write

    async def observe_write(request, work):
        queued.put_nowait(True)
        return await original_write(request, work)

    try:
        await asyncio.wait_for(started.wait(), 2)
        monkeypatch.setattr(database, "write", observe_write)
        yield queued, release, tasks
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert tasks[0].exception() is None


async def seed(service, clock):
    service.gateway_session("stream")
    await service.voice(100, 10, "stream", 2, 101, False)
    clock.advance(70)
    await service.voice(100, 10, "stream", 3, 102, False)


async def assert_settled(service, database, seconds):
    # Repeated flushes must not re-credit or revive the epoch.
    await service.stop()
    row = await service.repository.get_member(100, 10, service.request())
    assert row.total_vc_seconds == seconds
    assert Progress(row.xp, row.total_vc_seconds).voice == seconds // 60 * 5
    counts = await database.read(service.request(), lambda conn: (
        conn.execute("SELECT count(*) FROM v2_engagement_voice").fetchone()[0],
        conn.execute("SELECT count(*) FROM v2_engagement_runtime").fetchone()[0],
    ))
    assert counts == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "ready"])
@pytest.mark.parametrize("outcome", ["failure", "cancel", "success"])
async def test_pending_observation_shutdown(service, database, clock, monkeypatch, kind, outcome):
    await seed(service, clock)
    original_apply = service.events._apply_voice

    def apply(conn, event, capacity):
        result = original_apply(conn, event, capacity)
        if outcome == "failure":
            raise DatabaseUnavailableError("synthetic observation failure")
        return result

    monkeypatch.setattr(service.events, "_apply_voice", apply)
    async with held_writer(database, service, monkeypatch) as (queued, release, tasks):
        clock.advance(30)
        observation = asyncio.create_task(
            service.voice(100, 10, "stream", 4, 102, True) if kind == "event" else
            service.voice_ready("stream", (VoicePresence(100, 10, 102, False),)))
        tasks.append(observation)
        await asyncio.wait_for(queued.get(), 2)
        clock.advance(600)
        stop = asyncio.create_task(service.stop())
        tasks.append(stop)
        await asyncio.sleep(0)  # Run stop to its first await, with writer held.
        assert not service._accepting
        assert not stop.done()
        with pytest.raises(ConflictError):
            await service.voice(100, 10, "stream", 5, None, False)
        with pytest.raises(ConflictError):
            await service.voice_ready("stream", ())
        if outcome == "cancel":
            observation.cancel()
        # A successful drain must still use the original stop tick, not this delay.
        clock.advance(300)
        release.set()
        if outcome == "failure":
            with pytest.raises(DatabaseUnavailableError):
                await observation
        elif outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await observation
        else:
            await observation
        await stop
    assert service._voice_faulted is (outcome != "success")
    expected = 70 if outcome != "success" else (100 if kind == "event" else 700)
    await assert_settled(service, database, expected)


@pytest.mark.asyncio
async def test_shutdown_waits_for_all_observation_outcomes(service, database, clock, monkeypatch):
    await seed(service, clock)
    entered, release = asyncio.Event(), asyncio.Event()
    original_apply = service.events.apply_voice

    async def delayed_failure(event, capacity, request):
        if event.sequence == 4:
            entered.set()
            await release.wait()
            raise DatabaseUnavailableError("synthetic delayed failure")
        return await original_apply(event, capacity, request)

    monkeypatch.setattr(service.events, "apply_voice", delayed_failure)
    first = asyncio.create_task(service.voice(100, 10, "stream", 4, 102, True))
    stop = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        # Another completed observation must not hide the unresolved first one.
        assert not await service.voice(100, 10, "stream", 3, 102, False)
        assert await service.message(100, 10, "text-while-pending", "a", clock.now())
        assert (await service.profile(100, 10)).total == 1
        clock.advance(630)
        stop = asyncio.create_task(service.stop())
        await asyncio.sleep(0)
        assert not service._accepting
        release.set()
        with pytest.raises(DatabaseUnavailableError):
            await first
        await stop
    finally:
        release.set()
        await asyncio.gather(*(task for task in (first, stop) if task is not None), return_exceptions=True)
    await assert_settled(service, database, 70)


@pytest.mark.asyncio
async def test_running_observation_cancellation_rolls_back_before_flush(service, database, clock, monkeypatch):
    await seed(service, clock)
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original_apply = service.events._apply_voice

    def hold(conn, event, capacity):
        result = original_apply(conn, event, capacity)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        return result

    monkeypatch.setattr(service.events, "_apply_voice", hold)
    clock.advance(30)
    observation = asyncio.create_task(service.voice(100, 10, "stream", 4, 102, True))
    stop = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        clock.advance(600)
        stop = asyncio.create_task(service.stop())
        await asyncio.sleep(0)
        assert not service._accepting
        observation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observation
        assert service._voice_faulted
        assert not stop.done()
        release.set()
        await stop
    finally:
        release.set()
        await asyncio.gather(*(task for task in (observation, stop) if task is not None), return_exceptions=True)
    await assert_settled(service, database, 70)


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
async def test_interrupted_drain_preserves_observation_and_can_retry(service, database, clock, monkeypatch, interruption):
    await seed(service, clock)
    entered, release = asyncio.Event(), asyncio.Event()
    original_apply = service.events.apply_voice
    original_config = service.config
    flush = AsyncMock(wraps=service.events.flush_voice)
    monkeypatch.setattr(service.events, "flush_voice", flush)

    async def delayed(event, capacity, request):
        entered.set()
        await release.wait()
        return await original_apply(event, capacity, request)

    monkeypatch.setattr(service.events, "apply_voice", delayed)
    clock.advance(30)
    observation = asyncio.create_task(service.voice(100, 10, "stream", 4, 102, True))
    stop = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        service.config = replace(original_config, request_seconds=0.05)
        stop = asyncio.create_task(service.stop())
        await asyncio.sleep(0)
        assert not service._accepting
        if interruption == "cancel":
            stop.cancel()
            with pytest.raises(asyncio.CancelledError):
                await stop
        else:
            with pytest.raises(ShutdownError, match="voice observations did not drain"):
                await asyncio.wait_for(stop, 2)
        flush.assert_not_awaited()
        assert not observation.done()
        persisted = await database.read(service.request(), lambda conn: conn.execute(
            "SELECT duration FROM v2_engagement_voice WHERE guild_id=100 AND user_id=10").fetchone())
        assert persisted == (70,)
        service.config = original_config
        release.set()
        assert await observation
    finally:
        service.config = original_config
        release.set()
        await asyncio.gather(*(task for task in (observation, stop) if task is not None), return_exceptions=True)
    await assert_settled(service, database, 100)
    assert not service._voice_faulted


@pytest.mark.asyncio
async def test_failed_flush_retains_observed_credit_for_retry(service, database, clock, monkeypatch):
    await seed(service, clock)
    original_apply = service.events._apply_voice

    def fail(conn, event, capacity):
        original_apply(conn, event, capacity)
        raise DatabaseUnavailableError("synthetic failure")

    monkeypatch.setattr(service.events, "_apply_voice", fail)
    with pytest.raises(DatabaseUnavailableError):
        await service.voice(100, 10, "stream", 4, 102, True)
    from discordbot.engagement.adapters import event_repository
    original_progress = event_repository._progress

    def fail_credit(conn, *args, **kwargs):
        original_progress(conn, *args, **kwargs)
        raise DatabaseUnavailableError("synthetic flush failure")

    monkeypatch.setattr(event_repository, "_progress", fail_credit)
    clock.advance(630)
    with pytest.raises(DatabaseUnavailableError):
        await service.stop()
    assert await service.repository.get_member(100, 10, service.request()) is None
    monkeypatch.setattr(event_repository, "_progress", original_progress)
    await assert_settled(service, database, 70)
