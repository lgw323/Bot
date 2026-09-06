"""No canonical URL conversion, history trimming or playback accounting here."""

import sqlite3

from discordbot.music.ports.repository import Favorite, PlayCount
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.inputs import identifier, nonnegative, text_value
from discordbot.storage.ports.contracts import DatabaseRequest, require_page


class SqliteMusicRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    async def list_favorites(self, user_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[Favorite, ...]:
        identifier(user_id)
        require_page(limit, offset, self._db.config.page_limit)
        return await self._db.read(request, lambda conn: tuple(Favorite(*row) for row in conn.execute(
            "SELECT url,title FROM favorites WHERE user_id=? ORDER BY url LIMIT ? OFFSET ?", (user_id, limit, offset))))

    async def put_favorite(self, user_id: int, favorite: Favorite, request: DatabaseRequest) -> None:
        identifier(user_id)
        text_value(favorite.url, nonempty=True)
        text_value(favorite.title)

        def mutation(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO favorites VALUES (?,?,?) ON CONFLICT(user_id,url) DO UPDATE SET title=excluded.title", (user_id, favorite.url, favorite.title))

        await self._db.write(request, mutation)

    async def remove_favorite(self, user_id: int, url: str, request: DatabaseRequest) -> bool:
        identifier(user_id)
        text_value(url, nonempty=True)
        return await self._db.write(request, lambda conn: conn.execute("DELETE FROM favorites WHERE user_id=? AND url=?", (user_id, url)).rowcount > 0)

    async def get_volume(self, guild_id: int, request: DatabaseRequest) -> float | None:
        identifier(guild_id)

        def query(conn: sqlite3.Connection) -> float | None:
            row = conn.execute("SELECT volume FROM music_settings WHERE guild_id=?", (guild_id,)).fetchone()
            return row[0] if row else None

        return await self._db.read(request, query)

    async def set_volume(self, guild_id: int, volume: float, request: DatabaseRequest) -> None:
        identifier(guild_id)
        nonnegative(volume)

        def mutation(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO music_settings VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET volume=excluded.volume", (guild_id, volume))

        await self._db.write(request, mutation)

    async def list_play_counts(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[PlayCount, ...]:
        identifier(guild_id)
        require_page(limit, offset, self._db.config.page_limit)
        return await self._db.read(request, lambda conn: tuple(PlayCount(*row) for row in conn.execute(
            "SELECT url,title,play_count FROM music_play_counts WHERE guild_id=? ORDER BY play_count DESC,url LIMIT ? OFFSET ?", (guild_id, limit, offset))))
