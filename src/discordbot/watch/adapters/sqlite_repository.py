"""Guild-scoped queries, including a guild/session join for playlist reads."""

import sqlite3

from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.inputs import identifier, text_value
from discordbot.storage.adapters.schema import projection
from discordbot.storage.ports.contracts import DatabaseRequest, require_page
from discordbot.watch.ports.repository import WatchPlaylistData, WatchSessionData


class SqliteWatchRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    async def get_session(self, guild_id: int, session_id: str, request: DatabaseRequest) -> WatchSessionData | None:
        identifier(guild_id)
        text_value(session_id, nonempty=True)

        def query(conn: sqlite3.Connection) -> WatchSessionData | None:
            row = conn.execute(f'SELECT {projection(conn, "watch_sessions")} FROM watch_sessions WHERE guild_id=? AND session_id=?', (guild_id, session_id)).fetchone()
            return WatchSessionData(*row) if row else None

        return await self._db.read(request, query)

    async def list_sessions(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[WatchSessionData, ...]:
        identifier(guild_id)
        require_page(limit, offset, self._db.config.page_limit)

        def query(conn: sqlite3.Connection) -> tuple[WatchSessionData, ...]:
            return tuple(WatchSessionData(*row) for row in conn.execute(
                f'SELECT {projection(conn, "watch_sessions")} FROM watch_sessions WHERE guild_id=? ORDER BY created_at,session_id LIMIT ? OFFSET ?', (guild_id, limit, offset)))

        return await self._db.read(request, query)

    async def list_playlist(self, guild_id: int, session_id: str, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[WatchPlaylistData, ...]:
        identifier(guild_id)
        text_value(session_id, nonempty=True)
        require_page(limit, offset, self._db.config.page_limit)
        return await self._db.read(request, lambda conn: tuple(WatchPlaylistData(*row) for row in conn.execute(
            "SELECT p.video_url,p.video_title,p.added_by,p.order_index FROM watch_playlists p JOIN watch_sessions s ON s.session_id=p.session_id WHERE s.guild_id=? AND s.session_id=? ORDER BY p.order_index,p.video_url LIMIT ? OFFSET ?",
            (guild_id, session_id, limit, offset))))
