import asyncio
import sqlite3
from contextlib import closing

import pytest

import database_manager
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.music.ports.repository import Favorite
from discordbot.platform.errors import ValidationError
from discordbot.storage.ports.contracts import DatabaseRequest
from discordbot.watch.adapters.sqlite_repository import SqliteWatchRepository


def request():
    return DatabaseRequest.within(3, "synthetic-repository")


@pytest.mark.asyncio
async def test_same_user_two_guild_progress_birthday_and_global_favorites(database):
    engagement = SqliteEngagementRepository(database)
    music = SqliteMusicRepository(database)
    await asyncio.gather(
        engagement.add_progress(100, 10, 9, 1.25, request(), level=3),
        engagement.add_progress(200, 10, 2, 60, request()),
    )
    one = await engagement.get_member(100, 10, request())
    two = await engagement.get_member(200, 10, request())
    assert (one.xp, one.level, one.total_vc_seconds) == (40, 3, 120.75)
    assert (two.xp, two.level, two.total_vc_seconds) == (9, 1, 120)
    await engagement.set_birthday(100, 10, None, None, request())
    assert (await engagement.get_member(100, 10, request())).birth_day is None
    assert (await engagement.get_member(200, 10, request())).birth_day == 31
    assert len(await engagement.list_members(100, request())) == 1
    assert await engagement.get_member(300, 10, request()) is None
    with pytest.raises(ValidationError):
        await engagement.list_members(0, request())
    favorite = Favorite("url?preserve=1&alias=2", "friend's\n음악")
    await music.put_favorite(10, favorite, request())
    assert favorite in await music.list_favorites(10, request())
    assert favorite not in await music.list_favorites(11, request())
    assert not await music.remove_favorite(11, favorite.url, request())
    assert await music.remove_favorite(10, favorite.url, request())
    with closing(sqlite3.connect(database.config.path)) as conn:
        assert conn.execute("SELECT * FROM users WHERE guild_id=0").fetchall() == [(10, 0, 0, 1, 0, None, None)]


@pytest.mark.asyncio
async def test_music_pagination_history_and_persisted_volume(database):
    repo = SqliteMusicRepository(database)
    first = await repo.list_favorites(10, request(), limit=25)
    second = await repo.list_favorites(10, request(), limit=25, offset=25)
    assert len(first) == 25 and len(second) == 2
    assert len({item.url for item in first + second}) == 27
    assert len(await repo.list_play_counts(100, request())) == 60  # No top-50 trimming.
    assert (await repo.list_play_counts(100, request()))[0].count == 60
    assert (await repo.list_play_counts(200, request()))[0].count == 1000
    assert await repo.get_volume(100, request()) == 0.75
    assert await repo.get_volume(300, request()) is None  # Application selects defaults in Phase 7.
    await repo.set_volume(100, 0.5, request())
    assert await repo.get_volume(200, request()) == 1.0
    with pytest.raises(ValidationError):
        await repo.list_favorites(10, request(), limit=1001)


@pytest.mark.asyncio
async def test_watch_queries_require_correct_guild_including_playlist_join(database):
    repo = SqliteWatchRepository(database)
    session = await repo.get_session(100, "session-one", request())
    assert (session.created_at, session.channel_id, session.message_id) == ("2020-01-01 00:00:00", 1001, 1002)
    assert await repo.get_session(200, "session-one", request()) is None
    assert await repo.list_playlist(200, "session-one", request()) == ()
    assert len(await repo.list_sessions(100, request())) == 1
    item = (await repo.list_playlist(100, "session-one", request()))[0]
    assert (item.video_url, item.video_title, item.added_by, item.order_index) == ("same-url", "Title", "<friend>", 4)


@pytest.mark.asyncio
async def test_v1_reader_observes_v2_writes_unchanged(database):
    repo = SqliteEngagementRepository(database)
    await repo.add_progress(100, 10, 100, 120, request())
    old = await database_manager.get_user_data(10, 100)
    new = await repo.get_member(100, 10, request())
    assert (old["xp"], old["level"], old["total_vc_seconds"]) == (new.xp, new.level, new.total_vc_seconds)
    music = SqliteMusicRepository(database)
    await music.put_favorite(11, Favorite("quote'url", "title\n한글"), request())
    assert {"url": "quote'url", "title": "title\n한글"} in (await database_manager.get_favorites())["11"]
