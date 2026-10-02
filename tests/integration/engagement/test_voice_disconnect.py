"""A4-M3: synthetic transport gaps must never become voice duration."""

import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio

from discordbot.engagement.adapters.discord_runtime import EngagementResource
from discordbot.engagement.domain.policy import Progress
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.platform.tasks import TaskSupervisor


class Bot:
    _enable_debug_events = True

    def __init__(self):
        self.listeners = {}
        self.closed = False
        self.guilds = [SimpleNamespace(id=g, voice_channels=[],
            get_member=lambda user: SimpleNamespace(bot=False)) for g in (100, 200)]

    def get_guild(self, guild):
        return next(g for g in self.guilds if g.id == guild)

    async def add_cog(self, cog):
        pass

    async def remove_cog(self, name):
        pass

    def add_listener(self, callback, name):
        self.listeners.setdefault(name, []).append(callback)

    def remove_listener(self, callback, name):
        if callback in self.listeners.get(name, []):
            self.listeners[name].remove(callback)

    async def close(self):
        self.closed = True

    async def emit(self, name, *args):
        for callback in tuple(self.listeners.get(name, [])):
            await callback(*args)


@pytest_asyncio.fixture
async def owner(database, clock):
    resource = EngagementResource(Bot(), database, EngagementConfig(42), clock,
        TaskSupervisor(capacity=2, history_capacity=8, clock=clock), "disconnect-test")
    await resource.start()
    try:
        yield resource
    finally:
        await resource.stop()
        await resource.stop()
        assert resource.bot.closed
        assert not any(resource.bot.listeners.values())
        assert not resource.supervisor.snapshot().active


async def packet(owner, kind, sequence, data):
    await owner.bot.emit("on_socket_raw_receive",
        json.dumps(dict(op=0, t=kind, s=sequence, d=data)))


async def voice(owner, sequence, channel, *, guild=100, muted=False):
    await packet(owner, "VOICE_STATE_UPDATE", sequence, dict(guild_id=str(guild),
        user_id="10", channel_id=channel, self_mute=muted,
        member=dict(user=dict(id="10", bot=False))))


async def seed(owner, clock, *, two_guilds=False):
    await packet(owner, "READY", 1, dict(session_id="original"))
    for guild in ((100, 200) if two_guilds else (100,)):
        await voice(owner, 2, "101", guild=guild)
    clock.advance(70)
    for guild in ((100, 200) if two_guilds else (100,)):
        await voice(owner, 3, "102", guild=guild)


async def settled(owner, expected, *, guild=100):
    await owner.service.stop()
    await owner.service.stop()
    row = await owner.service.repository.get_member(guild, 10, owner.service.request())
    seconds = row.total_vc_seconds if row else 0
    assert seconds == expected
    assert Progress(0, seconds).voice == expected // 60 * 5


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["connected", "delayed-leave", "disconnected-stop"])
async def test_exact_m3_paths_preserve_connected_upper_bound(owner, clock, finish):
    await seed(owner, clock)
    stream = owner.gateway.stream
    clock.advance(30)
    if finish == "connected":
        await packet(owner, "RESUMED", 4, {})
        await voice(owner, 5, None)
    else:
        await owner.bot.emit("on_disconnect")
        clock.advance(600)
        if finish == "delayed-leave":
            await voice(owner, 4, None)
            await packet(owner, "RESUMED", 5, {})
            await voice(owner, 4, None)
    assert owner.gateway.stream == stream
    await settled(owner, 100)


@pytest.mark.asyncio
async def test_replay_burst_rejoin_mute_and_guild_isolation(owner, clock):
    await seed(owner, clock, two_guilds=True)
    clock.advance(30)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    await voice(owner, 4, None)
    clock.advance(100)  # Replay receipt times are not event occurrence times.
    await voice(owner, 5, "103")
    await voice(owner, 6, "103", guild=200, muted=True)
    clock.advance(100)
    await packet(owner, "RESUMED", 7, {})
    clock.advance(61)
    await voice(owner, 8, None)
    await voice(owner, 5, "103")  # Earlier replay cannot revive the tombstone.
    await voice(owner, 8, None, guild=200)
    await settled(owner, 161)
    await settled(owner, 100, guild=200)


@pytest.mark.asyncio
@pytest.mark.parametrize("replay_muted", [False, True])
async def test_replay_move_or_mute_then_live_unmute(owner, clock, replay_muted):
    await seed(owner, clock)
    clock.advance(30)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    await voice(owner, 4, "103", muted=replay_muted)
    clock.advance(100)
    await packet(owner, "RESUMED", 5, {})
    clock.advance(30)
    await voice(owner, 6, "103")
    clock.advance(31)
    await voice(owner, 7, None)
    await settled(owner, 131 if replay_muted else 161)


@pytest.mark.asyncio
async def test_repeated_disconnect_resume_preserves_fractional_observed_time(owner, clock):
    await packet(owner, "READY", 1, dict(session_id="original"))
    await voice(owner, 2, "101")
    clock.advance(35.75)
    await owner.bot.emit("on_disconnect")
    clock.advance(300)
    await owner.bot.emit("on_disconnect")  # Must not advance the frozen boundary.
    clock.advance(300)
    await packet(owner, "RESUMED", 3, {})
    clock.advance(10.5)
    await packet(owner, "RESUMED", 3, {})  # Repeated RESUMED is a no-op.
    clock.advance(10)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    await packet(owner, "RESUMED", 4, {})
    clock.advance(10)
    await voice(owner, 5, None)
    await settled(owner, 66)


@pytest.mark.asyncio
@pytest.mark.parametrize("present", [False, True])
async def test_replacement_ready_after_disconnect_keeps_m1_semantics(owner, clock, present):
    await seed(owner, clock)
    clock.advance(30)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    if present:
        member = SimpleNamespace(id=10, bot=False, voice=SimpleNamespace(
            self_mute=False, mute=False, self_deaf=False, deaf=False))
        owner.bot.guilds[0].voice_channels = [SimpleNamespace(id=101, members=[member])]
    await packet(owner, "READY", 1, dict(session_id="replacement"))
    await owner.gateway.ready()
    clock.advance(61)
    await voice(owner, 2, None)
    # M1 retains persisted observations only across a replacement stream.
    await settled(owner, 131 if present else 70)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_replay_outcome_drains_before_disconnected_stop(owner, clock, monkeypatch, outcome):
    await seed(owner, clock)
    clock.advance(30)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    app = owner.service
    entered, release, stop_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_apply = app.events.apply_voice
    original_clock = clock.monotonic

    async def held(event, *args):
        entered.set()
        await release.wait()
        if outcome == "failure":
            raise DatabaseUnavailableError("synthetic replay failure")
        return await original_apply(event, *args)

    def stop_clock():
        stop_entered.set()
        return original_clock()

    monkeypatch.setattr(app.events, "apply_voice", held)
    observation = asyncio.create_task(app.voice(100, 10, owner.gateway.stream, 4, 103, False))
    stop = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        monkeypatch.setattr(clock, "monotonic", stop_clock)
        stop = asyncio.create_task(app.stop())
        await asyncio.wait_for(stop_entered.wait(), 2)
        assert not stop.done()
        clock.advance(600)
        if outcome == "cancel":
            observation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observation
        release.set()
        if outcome == "failure":
            with pytest.raises(DatabaseUnavailableError):
                await observation
        elif outcome == "success":
            await observation
        await stop
    finally:
        release.set()
        await asyncio.gather(*(t for t in (observation, stop) if t is not None), return_exceptions=True)
    await settled(owner, 100 if outcome == "success" else 70)


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["before-resumed", "after-resumed"])
async def test_join_replayed_during_gap_starts_with_zero_elapsed_time(owner, clock, finish):
    await packet(owner, "READY", 1, dict(session_id="original"))
    clock.advance(100)
    await owner.bot.emit("on_disconnect")
    clock.advance(600)
    await voice(owner, 2, "101")
    clock.advance(100)
    if finish == "after-resumed":
        await packet(owner, "RESUMED", 3, {})
        clock.advance(61)
    await settled(owner, 61 if finish == "after-resumed" else 0)


@pytest.mark.asyncio
async def test_sdk_dispatch_captures_replay_tick_before_await_and_resumed(database, clock, monkeypatch):
    from discordbot.engagement.adapters.discord_runtime import create_engagement_bot

    bot = create_engagement_bot()
    tasks = []
    original_schedule = bot._schedule_event

    def schedule(*args, **kwargs):
        task = original_schedule(*args, **kwargs)
        tasks.append(task)
        return task

    monkeypatch.setattr(bot, "_schedule_event", schedule)
    monkeypatch.setattr(bot, "get_guild", lambda guild: SimpleNamespace(
        get_member=lambda user: SimpleNamespace(bot=False)))
    async with bot:  # SDK loop initialization only; no login or Gateway connection.
        resource = EngagementResource(bot, database, EngagementConfig(42), clock,
            TaskSupervisor(capacity=2, history_capacity=8, clock=clock), "sdk-dispatch")
        await resource.start()
        entered, release = asyncio.Event(), asyncio.Event()
        app = resource.service
        original_apply = app.events.apply_voice

        async def held(event, *args):
            if event.sequence == 4:
                entered.set()
                await release.wait()
            return await original_apply(event, *args)

        def dispatch_voice(sequence, channel):
            bot.dispatch("socket_raw_receive", json.dumps(dict(op=0, t="VOICE_STATE_UPDATE",
                s=sequence, d=dict(guild_id="100", user_id="10", channel_id=channel,
                    member=dict(user=dict(id="10", bot=False))))))

        try:
            bot.dispatch("socket_raw_receive", json.dumps(dict(op=0, t="READY", s=1,
                d=dict(session_id="original"))))
            dispatch_voice(2, "101")
            await asyncio.gather(*tasks)
            clock.advance(70)
            dispatch_voice(3, "102")
            await asyncio.gather(*tasks)
            clock.advance(30)
            bot.dispatch("disconnect")
            await asyncio.gather(*tasks)
            clock.advance(600)
            monkeypatch.setattr(app.events, "apply_voice", held)
            dispatch_voice(4, "103")
            await asyncio.wait_for(entered.wait(), 2)
            bot.dispatch("socket_raw_receive", json.dumps(dict(op=0, t="RESUMED", s=5, d={})))
            await tasks[-1]
            clock.advance(61)
            # Shutdown captures 161 connected seconds even though replay SQL is pending.
            stop = asyncio.create_task(app.stop())
            tasks.append(stop)
            await asyncio.sleep(0)
            assert not app._accepting and not stop.done()
            clock.advance(600)
            # Already-scheduled late lifecycle callbacks must not change stop ownership.
            bot.dispatch("disconnect")
            release.set()
            await asyncio.gather(*tasks)
            await settled(resource, 161)
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await resource.stop()
            assert not any(bot.extra_events.values())
            assert not resource.supervisor.snapshot().active
