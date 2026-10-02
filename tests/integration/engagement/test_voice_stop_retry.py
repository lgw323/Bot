"""A4-M4: cancellation cannot move the closed voice admission boundary."""

import asyncio
from dataclasses import replace
import threading

import pytest

from discordbot.engagement.domain.policy import Progress
from discordbot.platform.errors import ConflictError, DatabaseUnavailableError, ShutdownError


async def assert_settled(service, database, expected):
    for guild, seconds in expected.items():
        row = await service.repository.get_member(guild, 10, service.request())
        assert row.total_vc_seconds == seconds
        assert Progress(row.xp, row.total_vc_seconds).voice == seconds // 60 * 5
    assert await database.read(service.request(), lambda conn: (
        conn.execute("SELECT count(*) FROM v2_engagement_voice").fetchone()[0],
        conn.execute("SELECT count(*) FROM v2_engagement_runtime").fetchone()[0],
    )) == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["connected", "resumed", "disconnected"])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
@pytest.mark.parametrize("interruption", ["cancel", "timeout"])
async def test_repeated_interrupted_drain_keeps_first_stop_tick(
        service, database, clock, monkeypatch, transport, outcome, interruption):
    service.gateway_session("stream")
    await service.voice(100, 10, "stream", 2, 101, False)
    clock.advance(10)
    await service.voice(200, 10, "stream", 2, 201, False)
    clock.advance(60)
    for guild in (100, 200):
        await service.voice(guild, 10, "stream", 3, 102, False)
    clock.advance(30)
    if transport != "connected":
        service.gateway_disconnected()
        clock.advance(600)

    entered, release, draining = asyncio.Event(), asyncio.Event(), asyncio.Event()
    apply = service.events.apply_voice
    wait = service._voice_drained.wait
    flush = service.events.flush_voice
    ticks, flushes = [], []

    async def held(event, *args):
        ticks.append(event.tick)
        entered.set()
        await release.wait()
        if outcome == "failure":
            raise DatabaseUnavailableError("synthetic admitted observation failure")
        return await apply(event, *args)

    async def drain():
        draining.set()
        return await wait()

    async def recording(epoch, tick, request, **kwargs):
        flushes.append((tick, kwargs["observed_only"], service._voice_pending))
        return await flush(epoch, tick, request, **kwargs)

    monkeypatch.setattr(service.events, "apply_voice", held)
    monkeypatch.setattr(service._voice_drained, "wait", drain)
    monkeypatch.setattr(service.events, "flush_voice", recording)
    observation = asyncio.create_task(service.voice(100, 10, "stream", 4, 103, False))
    stops = []
    original_config = service.config
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if transport == "resumed":
            service.gateway_resumed()
        clock.advance(61)
        expected_tick = 1100 if transport == "disconnected" else 1161
        for _ in range(2):
            draining.clear()
            if interruption == "timeout":
                service.config = replace(original_config, request_seconds=0.02)
            stop = asyncio.create_task(service.stop())
            stops.append(stop)
            await asyncio.wait_for(draining.wait(), 2)
            assert not service._accepting and not observation.done()
            if interruption == "cancel":
                stop.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await stop
            else:
                with pytest.raises(ShutdownError, match="voice observations did not drain"):
                    await asyncio.wait_for(stop, 2)
            service.config = original_config
            assert not flushes and service._voice_pending == 1
            assert not service._voice_faulted
            clock.advance(600)
            with pytest.raises(ConflictError):
                await service.voice(100, 10, "stream", 5, None, False)
            with pytest.raises(ConflictError):
                service.gateway_resumed()
            with pytest.raises(ConflictError):
                service.gateway_disconnected()
            with pytest.raises(ConflictError):
                service.gateway_session("late-replacement")
            with pytest.raises(ConflictError):
                await service.voice_ready("stream", ())
        if outcome == "cancel":
            observation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observation
        release.set()
        if outcome == "failure":
            with pytest.raises(DatabaseUnavailableError):
                await observation
        elif outcome == "success":
            assert await observation
        await service.stop()
        clock.advance(600)
        await service.stop()
        assert ticks == [1100]
        assert flushes == [(expected_tick, outcome != "success", 0)] * 2
        expected = ({100: int(expected_tick - 1000), 200: int(expected_tick - 1010)}
                    if outcome == "success" else {100: 70, 200: 60})
        await assert_settled(service, database, expected)
    finally:
        service.config = original_config
        release.set()
        await asyncio.gather(observation, *stops, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["failure", "cancel", "committed-cancel"])
async def test_interrupted_flush_retry_keeps_tick_and_atomic_credit(
        service, database, clock, monkeypatch, interruption):
    from discordbot.engagement.adapters import event_repository

    service.gateway_session("stream")
    await service.voice(100, 10, "stream", 2, 101, False)
    clock.advance(100)
    service.gateway_disconnected()
    clock.advance(600)
    service.gateway_resumed()
    clock.advance(61)

    entered, release = asyncio.Event(), threading.Event()
    ack_release = asyncio.Event()
    loop = asyncio.get_running_loop()
    progress = event_repository._progress
    flush = service.events.flush_voice
    flushes, requests = [], []

    def held_credit(conn, *args, **kwargs):
        progress(conn, *args, **kwargs)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        if interruption == "failure":
            raise DatabaseUnavailableError("synthetic flush rollback")

    async def recording(epoch, tick, request, **kwargs):
        flushes.append(tick)
        requests.append(request)
        await flush(epoch, tick, request, **kwargs)
        if interruption == "committed-cancel" and len(flushes) == 1:
            entered.set()
            await ack_release.wait()

    if interruption != "committed-cancel":
        monkeypatch.setattr(event_repository, "_progress", held_credit)
    monkeypatch.setattr(service.events, "flush_voice", recording)
    original_config = service.config
    stop = asyncio.create_task(service.stop())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        clock.advance(600)
        if interruption == "failure":
            release.set()
            with pytest.raises(DatabaseUnavailableError):
                await stop
        else:
            stop.cancel()
            with pytest.raises(asyncio.CancelledError):
                await stop
        release.set()
        # Writer barrier proves rollback/commit completed before changing the hook.
        await database.write(service.request(), lambda conn: None)
        row = await service.repository.get_member(100, 10, service.request())
        if interruption == "committed-cancel":
            assert row.total_vc_seconds == 161
        else:
            assert row is None
        monkeypatch.setattr(event_repository, "_progress", progress)
        assert not service._accepting and not service._voice_faulted
        # Distinct valid budgets prove renewed deadlines without assuming that
        # Windows' monotonic clock advances between adjacent synchronous calls.
        service.config = replace(original_config, request_seconds=original_config.request_seconds + 1)
        await service.stop()
        clock.advance(600)
        service.config = replace(original_config, request_seconds=original_config.request_seconds + 2)
        await service.stop()
        assert flushes == [1161, 1161, 1161]
        assert len({id(request) for request in requests}) == 3
        assert requests[0].deadline < requests[1].deadline < requests[2].deadline
        await assert_settled(service, database, {100: 161})
    finally:
        release.set()
        ack_release.set()
        await asyncio.gather(stop, return_exceptions=True)
        monkeypatch.setattr(event_repository, "_progress", progress)
        service.config = original_config


@pytest.mark.asyncio
async def test_successful_lifecycle_start_does_not_reuse_previous_stop_tick(service, database, clock):
    service.gateway_session("stream")
    await service.voice(100, 10, "stream", 2, 101, False)
    clock.advance(70)
    await service.stop()
    await assert_settled(service, database, {100: 70})
    clock.advance(600)
    await service.start()
    service.gateway_session("next-stream")
    await service.voice(100, 10, "next-stream", 2, 101, False)
    clock.advance(90)
    await service.stop()
    await assert_settled(service, database, {100: 160})
