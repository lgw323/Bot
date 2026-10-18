import asyncio
from dataclasses import replace
import sqlite3
from contextlib import closing

import pytest

from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.platform.errors import CapacityError, ConflictError, DatabaseUnavailableError


async def voice(service, seq, channel, muted=False, guild=100, stream="gateway-one"):
    return await service.voice(guild, 10, stream, seq, channel, muted)


@pytest.mark.asyncio
async def test_text_duplicates_parallel_updates_and_guild_isolation(service, clock):
    await service.repository.add_progress(100, 10, 7, 119.5, service.request())
    values = await asyncio.gather(*(service.message(100, 10, "same-id", "각", clock.now()) for _ in range(8)))
    assert sum(values) == 1
    await asyncio.gather(*(service.message(100, 10, f"message-{i}", "가", clock.now()) for i in range(8)))
    assert (await service.profile(100, 10)).text == 26
    assert (await service.profile(100, 10)).seconds == 119.5
    await service.message(200, 10, "same-id", "hi", clock.now())
    assert (await service.profile(200, 10)).total == 2
    assert not await service.message(None, 10, "dm", "ignored", clock.now())
    assert not await service.message(100, 10, "bot", "ignored", clock.now(), bot=True)
    await service.message(100, 11, "empty", "   ", clock.now())
    assert await service.repository.get_member(100, 11, service.request()) is None


@pytest.mark.asyncio
async def test_text_receipt_survives_application_restart(service, database, clock):
    await service.message(100, 10, "replayed", "abc", clock.now())
    await service.stop()
    fresh = EngagementService(SqliteEngagementRepository(database), SqliteEngagementEvents(database),
        MasterAuthorization(42), service.config, clock, "new-process")
    await fresh.start()
    try:
        assert not await fresh.message(100, 10, "replayed", "abc", clock.now())
        assert (await fresh.profile(100, 10)).text == 3
    finally:
        await fresh.stop()


@pytest.mark.asyncio
async def test_receipt_capacity_never_evicts_live_dedupe_or_gives_partial_xp(service, clock):
    service.config = replace(service.config, receipt_capacity=1)
    old = clock.now()
    await service.message(100, 10, "first", "a", old)
    with pytest.raises(CapacityError):
        await service.message(100, 10, "second", "a", old)
    assert (await service.profile(100, 10)).text == 1
    clock.advance(8 * 86400)
    assert not await service.message(100, 10, "first", "a", old)
    await service.message(100, 10, "third", "a", clock.now())
    assert (await service.profile(100, 10)).text == 2


@pytest.mark.asyncio
async def test_voice_move_mute_deaf_short_stays_and_duplicate_leave(service, clock):
    await voice(service, 1, 1001)
    clock.advance(30)
    await voice(service, 2, 1002)  # Move stays in the same session.
    clock.advance(40)
    await voice(service, 3, 1002, True)
    clock.advance(300)
    await voice(service, 4, 1002, False)
    clock.advance(55.9)
    assert await voice(service, 5, None)
    assert not await voice(service, 5, None)
    assert not await voice(service, 4, 1002, False)  # Older replay cannot resurrect session.
    assert (await service.profile(100, 10)).seconds == 125
    assert (await service.profile(100, 10)).voice == 10
    for join, leave in ((6, 7), (8, 9)):
        await voice(service, join, 1001)
        clock.advance(59.9)
        await voice(service, leave, None)
    assert (await service.profile(100, 10)).seconds == 125


@pytest.mark.asyncio
async def test_voice_concurrent_guilds_shutdown_and_late_event(service, clock):
    await asyncio.gather(voice(service, 1, 1001), voice(service, 1, 2001, guild=200))
    clock.advance(61)
    await asyncio.gather(voice(service, 2, None), service.stop())
    first = await service.repository.get_member(100, 10, service.request())
    second = await service.repository.get_member(200, 10, service.request())
    assert first.total_vc_seconds == second.total_vc_seconds == 61
    with pytest.raises(ConflictError):
        await voice(service, 3, None)
    await service.stop()
    assert (await service.repository.get_member(100, 10, service.request())).total_vc_seconds == 61


@pytest.mark.asyncio
async def test_voice_reconnect_new_stream_and_restart_do_not_invent_offline_time(service, clock, database):
    await voice(service, 1, 1001)
    clock.advance(70)
    await voice(service, 2, 1001, True)
    clock.advance(600)
    # A new process can recover only the persisted observed 70-second segment.
    fresh = EngagementService(SqliteEngagementRepository(database), SqliteEngagementEvents(database),
        MasterAuthorization(42), service.config, clock, "crash-restart")
    await fresh.start()
    try:
        assert (await fresh.profile(100, 10)).seconds == 70
        await voice(fresh, 0, 1001, stream="new-ready")
        clock.advance(60)
        await voice(fresh, 1, None, stream="new-ready")
        assert (await fresh.profile(100, 10)).seconds == 130
        with pytest.raises(ConflictError):
            await voice(service, 3, None)
    finally:
        await fresh.stop()


@pytest.mark.asyncio
async def test_busy_failure_does_not_consume_event_and_retry_is_safe(service, database, clock):
    with closing(sqlite3.connect(database.config.path, isolation_level=None)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseUnavailableError):
            await service.message(100, 10, "retry-me", "a", clock.now())
        lock.rollback()
    assert await service.message(100, 10, "retry-me", "a", clock.now())
    assert (await service.profile(100, 10)).total == 1


@pytest.mark.asyncio
async def test_ranking_completed_minutes_top_ten_ties_and_scope(service):
    for user in range(1, 14):
        await service.repository.add_progress(100, user, 0, 119.99, service.request())
    await service.repository.add_progress(200, 1, 10000, 0, service.request())
    rows = await service.ranking(100)
    assert [row.user_id for row in rows] == list(range(1, 11))
    for row in rows:
        assert (await service.profile(100, row.user_id)).total == 5
    assert await service.ranking(300) == ()
