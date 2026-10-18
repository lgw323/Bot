"""Synthetic A4-M1 regressions through the real Gateway/service/SQLite path."""

import asyncio
import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from discordbot.engagement.adapters.discord_runtime import VoiceGateway
from discordbot.engagement.ports.events import VoicePresence
from discordbot.platform.errors import ConflictError


def gateway_for(service, occupants=()):
    guilds = []
    for guild_id in (100, 200):
        members = [SimpleNamespace(id=user, bot=False, voice=SimpleNamespace(
            self_mute=False, mute=False, self_deaf=False, deaf=False))
            for guild, user in occupants if guild == guild_id]
        guilds.append(SimpleNamespace(id=guild_id,
            voice_channels=[SimpleNamespace(id=guild_id + 1, members=members)],
            get_member=lambda user: SimpleNamespace(bot=False)))
    bot = SimpleNamespace(guilds=guilds,
        get_guild=lambda guild_id: next(g for g in guilds if g.id == guild_id))
    return VoiceGateway(bot, service)


async def ready(gateway, session, *, seed=True):
    await gateway.receive(json.dumps({"op": 0, "t": "READY", "s": 1,
        "d": {"session_id": session}}))
    if seed:
        await gateway.ready()


async def voice(gateway, sequence, channel, *, guild=100, user=10, **flags):
    await gateway.receive(json.dumps({"op": 0, "t": "VOICE_STATE_UPDATE", "s": sequence,
        "d": {"guild_id": str(guild), "user_id": str(user), "channel_id": channel,
            "member": {"user": {"id": str(user), "bot": False}}, **flags}}))


@pytest.mark.asyncio
@pytest.mark.parametrize("finish,expected", [("shutdown", 70), ("rejoin", 131)])
async def test_new_ready_absent_member_cannot_accrue_voice_time(service, clock, finish, expected):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    await voice(gateway, 2, "1001")
    clock.advance(70)
    await voice(gateway, 3, "1002")
    await ready(gateway, "new")
    clock.advance(600)
    if finish == "rejoin":
        await voice(gateway, 2, "1001")
        clock.advance(61)
        await voice(gateway, 3, None)
    await service.stop()
    row = await service.repository.get_member(100, 10, service.request())
    assert row.total_vc_seconds == expected
    assert int(row.total_vc_seconds // 60) * 5 == (5 if finish == "shutdown" else 10)


@pytest.mark.asyncio
async def test_pending_ready_shutdown_keeps_observations_and_current_stream_only(service, clock):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    for user in (10, 11):
        await voice(gateway, 2, "1001", user=user)
    clock.advance(70)
    for user in (10, 11):
        await voice(gateway, 3, "1002", user=user)
    clock.advance(600)
    await ready(gateway, "new", seed=False)
    # A current-stream event before on_ready confirms only user 11.
    await voice(gateway, 2, "1001", user=11)
    clock.advance(61)
    await service.stop()
    await gateway.ready()  # Late callback cannot resurrect a flushed epoch.
    await service.stop()
    for user, expected in ((10, 70), (11, 131)):
        row = await service.repository.get_member(100, user, service.request())
        assert row.total_vc_seconds == expected


@pytest.mark.asyncio
async def test_continuous_and_departed_same_user_are_isolated_across_guilds(service, clock):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    for guild in (100, 200):
        await voice(gateway, 2, "1001", guild=guild)
    clock.advance(59.9)
    for guild in (100, 200):
        await voice(gateway, 3, "1002", guild=guild)
    clock.advance(600)
    # Only guild 100 still sees the same user. Keep its sub-minute duration.
    gateway.bot = gateway_for(service, ((100, 10),)).bot
    await ready(gateway, "new")
    clock.advance(2)
    await gateway.ready()  # Must not rebase again or settle twice.
    await voice(gateway, 2, None)
    assert (await service.profile(100, 10)).seconds == 61
    assert (await service.profile(200, 10)).seconds == 0
    await voice(gateway, 2, "2001", guild=200)
    clock.advance(59.9)
    await voice(gateway, 3, None, guild=200)
    # Two departed short stays cannot be combined across replacement READY.
    assert (await service.profile(200, 10)).seconds == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["self_mute", "mute", "self_deaf", "deaf"])
async def test_replacement_snapshot_rebases_muted_continuous_member(service, clock, flag):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    await voice(gateway, 2, "1001")
    clock.advance(70)
    await voice(gateway, 3, "1002")
    clock.advance(600)
    gateway.bot = gateway_for(service, ((100, 10),)).bot
    setattr(gateway.bot.guilds[0].voice_channels[0].members[0].voice, flag, True)
    await ready(gateway, "new")
    clock.advance(100)
    await voice(gateway, 2, "1001")
    clock.advance(61)
    await voice(gateway, 3, None)
    assert (await service.profile(100, 10)).seconds == 131
    assert (await service.profile(100, 10)).voice == 10


@pytest.mark.asyncio
async def test_sequenced_event_and_leave_before_snapshot_win_over_cache(service, clock):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    for user in (10, 11):
        await voice(gateway, 2, "1001", user=user)
    clock.advance(70)
    for user in (10, 11):
        await voice(gateway, 3, "1002", user=user)
    clock.advance(600)
    await ready(gateway, "new", seed=False)
    await voice(gateway, 2, None)
    await voice(gateway, 3, "1001", user=11)
    # Stale cache shows departed 10 and misses newly confirmed 11.
    gateway.bot = gateway_for(service, ((100, 10),)).bot
    await gateway.ready()
    clock.advance(61)
    await gateway.ready()
    await voice(gateway, 3, "1001", user=11)  # Duplicate must not change time.
    await service.stop()
    for user, expected in ((10, 70), (11, 131)):
        assert (await service.repository.get_member(100, user, service.request())).total_vc_seconds == expected


@pytest.mark.asyncio
async def test_repeated_replacements_and_old_callbacks_do_not_duplicate_settlement(service, clock):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    old_stream = gateway.stream
    await voice(gateway, 2, "1001")
    clock.advance(70)
    await voice(gateway, 3, "1002")
    for session in ("new", "new", "third", "third"):
        clock.advance(600)
        await ready(gateway, session)
        assert (await service.profile(100, 10)).seconds == 70
    with pytest.raises(ConflictError):
        await service.voice_ready(old_stream, (VoicePresence(100, 10, 1001, False),))
    with pytest.raises(ConflictError):
        await service.voice(100, 10, old_stream, 4, 1001, False)
    await voice(gateway, 2, "1001")
    clock.advance(61)
    await voice(gateway, 3, None)
    assert (await service.profile(100, 10)).seconds == 131


@pytest.mark.asyncio
async def test_snapshot_capacity_failure_rolls_back_settlement_and_fails_closed(service, clock):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    await voice(gateway, 2, "1001")
    clock.advance(70)
    await voice(gateway, 3, "1002")
    clock.advance(600)
    service.config = replace(service.config, voice_capacity=1)
    gateway.bot = gateway_for(service, ((100, 11), (200, 12))).bot
    await ready(gateway, "new")  # Second seed exceeds capacity after absent settlement.
    assert (await service.profile(100, 10)).seconds == 0  # Whole transaction rolled back.
    with pytest.raises(ConflictError):
        await service.voice(100, 11, gateway.stream, 2, None, False)
    clock.advance(600)
    await service.stop()
    assert (await service.repository.get_member(100, 10, service.request())).total_vc_seconds == 70
    assert await service.repository.get_member(100, 11, service.request()) is None


@pytest.mark.asyncio
async def test_queued_reconciliation_precedes_shutdown_flush_once(service, database, clock, monkeypatch):
    gateway = gateway_for(service)
    await ready(gateway, "old")
    for user in (10, 11):
        await voice(gateway, 2, "1001", user=user)
    clock.advance(70)
    for user in (10, 11):
        await voice(gateway, 3, "1002", user=user)
    clock.advance(600)
    gateway.bot = gateway_for(service, ((100, 11),)).bot
    await ready(gateway, "new", seed=False)

    started, queued = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def hold(conn):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    blocker = asyncio.create_task(database.write(service.request(), hold))
    tasks = [blocker]
    original_write = database.write
    async def observed_write(request, work):
        queued.set()
        return await original_write(request, work)
    try:
        await asyncio.wait_for(started.wait(), 2)
        monkeypatch.setattr(database, "write", observed_write)
        tasks.append(asyncio.create_task(gateway.ready()))
        await asyncio.wait_for(queued.wait(), 2)
        queued.clear()
        clock.advance(61)
        tasks.append(asyncio.create_task(service.stop()))
        await asyncio.sleep(0)  # Stop closes admission and waits for reconciliation.
        assert not service._accepting
        assert not tasks[-1].done()
        assert not queued.is_set()  # Flush cannot choose policy before the outcome.
    finally:
        release.set()
        await asyncio.gather(*tasks)
    await service.stop()
    for user, expected in ((10, 70), (11, 131)):
        assert (await service.repository.get_member(100, user, service.request())).total_vc_seconds == expected


@pytest.mark.asyncio
async def test_cancelled_reconciliation_rolls_back_and_flushes_observed_only(service, database, clock, monkeypatch):
    from discordbot.engagement.adapters import event_repository

    gateway = gateway_for(service)
    await ready(gateway, "old")
    await voice(gateway, 2, "1001")
    clock.advance(70)
    await voice(gateway, 3, "1002")
    clock.advance(600)
    await ready(gateway, "new", seed=False)
    original_progress = event_repository._progress
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    def hold(conn, *args, **kwargs):
        original_progress(conn, *args, **kwargs)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    monkeypatch.setattr(event_repository, "_progress", hold)
    task = asyncio.create_task(gateway.ready())
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    await database.write(service.request(), lambda conn: None)
    monkeypatch.setattr(event_repository, "_progress", original_progress)
    assert (await service.profile(100, 10)).seconds == 0
    with pytest.raises(ConflictError):
        await service.voice_ready(gateway.stream, ())
    clock.advance(600)
    await service.stop()
    await service.stop()
    assert (await service.repository.get_member(100, 10, service.request())).total_vc_seconds == 70
