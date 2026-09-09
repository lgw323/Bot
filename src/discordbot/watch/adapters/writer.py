"""Watch-web-only transactional writer on the Phase 3 database lane."""

from datetime import datetime, timezone
import hashlib
import sqlite3
from collections.abc import Callable
from typing import TypeVar

from discordbot.platform.context import current_correlation
from discordbot.platform.errors import CapacityError, ConflictError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.migrations import validate_ledger
from discordbot.storage.ports.contracts import DatabaseRequest
from discordbot.watch.domain.policy import Cleanup, ClosedSession, Intent
from discordbot.watch.ports.repository import WatchPlaylistData

T = TypeVar("T")


class SqliteWatchWriter:
    def __init__(self, database: SqliteDatabase) -> None:
        self.database = database

    def request(self) -> DatabaseRequest:
        context = current_correlation()
        return DatabaseRequest.within(3, context.correlation_id if context else "watch-storage")

    def own(self, conn: sqlite3.Connection, epoch: str, now: float) -> None:
        row = conn.execute("SELECT epoch,lease FROM v2_watch_owner WHERE id=1").fetchone()
        if row is None or row[0] != epoch or row[1] <= now:
            raise ConflictError("Watch writer lease unavailable")

    async def work(self, epoch: str, now: float, operation: Callable[[sqlite3.Connection], T]) -> T:
        def transaction(conn: sqlite3.Connection) -> T:
            self.own(conn, epoch, now)
            return operation(conn)
        return await self.database.write(self.request(), transaction)

    async def start(self, epoch: str, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            if validate_ledger(conn) < 4:
                raise ConflictError("Watch requires an explicitly migrated candidate")
            owner = conn.execute("SELECT epoch,lease FROM v2_watch_owner WHERE id=1").fetchone()
            if owner and owner[0] == epoch and owner[1] > now:
                return
            if owner and owner[1] > now:
                raise ConflictError("another Watch writer is live")
            if conn.execute("SELECT count(*) FROM watch_sessions").fetchone()[0] > 10000:
                raise CapacityError("Watch stale cleanup capacity")
            # An exclusive live-owner lease prevents a second process deleting
            # valid active sessions. A replaced/dead owner has no resumable sockets.
            for sid, guild, user, channel, message in conn.execute(
                    "SELECT session_id,guild_id,created_by,channel_id,message_id FROM watch_sessions"):
                if not conn.execute("SELECT 1 FROM v2_watch_intents WHERE session_id=?", (sid,)).fetchone():
                    opaque = hashlib.sha256(("legacy:" + sid).encode()).hexdigest()
                    conn.execute("INSERT OR IGNORE INTO v2_watch_intents VALUES (?,?,?,?,?,1,?,?,NULL,NULL,0)",
                                 (opaque, guild, user, now, now, channel, message))
            conn.execute("UPDATE v2_watch_intents SET closed=1")
            if conn.execute("SELECT count(*) FROM v2_watch_intents").fetchone()[0] > 10000:
                raise CapacityError("Watch stale receipt capacity")
            conn.execute("DELETE FROM watch_playlists")
            conn.execute("DELETE FROM watch_sessions")
            conn.execute("INSERT INTO v2_watch_owner VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET epoch=excluded.epoch,lease=excluded.lease", (epoch, now+10))
        await self.database.write(self.request(), transaction)

    async def heartbeat(self, epoch: str, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            conn.execute("UPDATE v2_watch_owner SET lease=? WHERE id=1", (now+10,))
            conn.execute("DELETE FROM v2_watch_intents WHERE closed=1 AND cleaned=1 AND expires<?", (now,))
        await self.work(epoch, now, transaction)

    async def release(self, epoch: str) -> None:
        await self.database.write(self.request(), lambda conn: conn.execute(
            "UPDATE v2_watch_owner SET lease=0 WHERE id=1 AND epoch=?", (epoch,)).rowcount)

    async def create(self, epoch: str, intent: Intent, now: float) -> Intent:
        def transaction(conn: sqlite3.Connection) -> Intent:
            row = conn.execute("SELECT session_id,guild_id,created_by,created,expires,closed FROM v2_watch_intents WHERE session_id=?", (intent.session_id,)).fetchone()
            if row:
                result = Intent(*row)
                if result.closed or result.expires <= now:
                    raise ClosedSession("Watch create operation already terminal")
                return result
            if conn.execute("SELECT count(*) FROM v2_watch_intents").fetchone()[0] >= 10000:
                raise CapacityError("Watch durable receipt capacity")
            conn.execute("INSERT INTO v2_watch_intents VALUES (?,?,?,?,?,0,NULL,NULL,NULL,NULL,0)",
                         (intent.session_id, intent.guild, intent.user, intent.created, intent.expires))
            stamp = datetime.fromtimestamp(intent.created, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO watch_sessions(session_id,guild_id,created_by,created_at) VALUES (?,?,?,?)",
                         (intent.session_id, intent.guild, intent.user, stamp))
            return intent
        return await self.work(epoch, now, transaction)

    def live(self, conn: sqlite3.Connection, sid: str, now: float) -> None:
        row = conn.execute("SELECT closed,expires FROM v2_watch_intents WHERE session_id=?", (sid,)).fetchone()
        if row is None or row[0] or row[1] <= now:
            raise ClosedSession("Watch session not live")

    async def bind(self, epoch: str, session_id: str, channel: int, message: int, admin: bool, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            self.live(conn, session_id, now)
            columns = ("admin_channel", "admin_message") if admin else ("channel_id", "message_id")
            row = conn.execute(f"SELECT {columns[0]},{columns[1]} FROM v2_watch_intents WHERE session_id=?", (session_id,)).fetchone()
            if row[0] is not None and row != (channel, message):
                raise ConflictError("Watch message already bound")
            conn.execute(f"UPDATE v2_watch_intents SET {columns[0]}=?,{columns[1]}=? WHERE session_id=?", (channel, message, session_id))
            if not admin:
                conn.execute("UPDATE watch_sessions SET channel_id=?,message_id=? WHERE session_id=?", (channel, message, session_id))
        await self.work(epoch, now, transaction)

    async def close(self, epoch: str, session_id: str, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            conn.execute("UPDATE v2_watch_intents SET closed=1 WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM watch_playlists WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM watch_sessions WHERE session_id=?", (session_id,))
        await self.work(epoch, now, transaction)

    async def abort(self, epoch: str, intent: Intent, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            exists = conn.execute("SELECT 1 FROM v2_watch_intents WHERE session_id=?", (intent.session_id,)).fetchone()
            if not exists:
                if conn.execute("SELECT count(*) FROM v2_watch_intents").fetchone()[0] >= 10000:
                    raise CapacityError("Watch durable receipt capacity")
                conn.execute("INSERT INTO v2_watch_intents VALUES (?,?,?,?,?,1,NULL,NULL,NULL,NULL,0)",
                    (intent.session_id, intent.guild, intent.user, intent.created, intent.expires))
            else:
                conn.execute("UPDATE v2_watch_intents SET closed=1 WHERE session_id=?", (intent.session_id,))
            conn.execute("DELETE FROM watch_playlists WHERE session_id=?", (intent.session_id,))
            conn.execute("DELETE FROM watch_sessions WHERE session_id=?", (intent.session_id,))
        await self.work(epoch, now, transaction)

    async def playlist(self, epoch: str, session_id: str, now: float) -> tuple[WatchPlaylistData, ...]:
        def query(conn: sqlite3.Connection) -> tuple[WatchPlaylistData, ...]:
            self.own(conn, epoch, now)
            self.live(conn, session_id, now)
            return tuple(WatchPlaylistData(*row) for row in conn.execute(
                "SELECT video_url,video_title,added_by,order_index FROM watch_playlists WHERE session_id=? ORDER BY order_index,video_url LIMIT 100", (session_id,)))
        return await self.database.read(self.request(), query)

    async def add(self, epoch: str, session_id: str, url: str, title: str, by: str, now: float, maximum: int) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            self.live(conn, session_id, now)
            duplicate = conn.execute("SELECT 1 FROM watch_playlists WHERE session_id=? AND video_url=?", (session_id,url)).fetchone()
            if not duplicate and conn.execute("SELECT count(*) FROM watch_playlists WHERE session_id=?", (session_id,)).fetchone()[0] >= maximum:
                raise CapacityError("Watch playlist full")
            order = conn.execute("SELECT COALESCE(MAX(order_index),0)+1 FROM watch_playlists WHERE session_id=?", (session_id,)).fetchone()[0]
            # Preserve V1 URL-keyed duplicate replacement: move duplicate to tail.
            conn.execute("INSERT OR REPLACE INTO watch_playlists VALUES (?,?,?,?,?)", (session_id,url,title,by,order))
        await self.work(epoch, now, transaction)

    async def remove(self, epoch: str, session_id: str, url: str, now: float) -> None:
        def transaction(conn: sqlite3.Connection) -> None:
            self.live(conn, session_id, now)
            conn.execute("DELETE FROM watch_playlists WHERE session_id=? AND video_url=?", (session_id,url))
        await self.work(epoch, now, transaction)

    async def cleanup(self, epoch: str, now: float) -> tuple[Cleanup, ...]:
        def query(conn: sqlite3.Connection) -> tuple[Cleanup, ...]:
            self.own(conn, epoch, now)
            return tuple(Cleanup(*row) for row in conn.execute("SELECT session_id,channel_id,message_id,admin_channel,admin_message FROM v2_watch_intents WHERE closed=1 AND cleaned=0 ORDER BY created,session_id LIMIT 100"))
        return await self.database.read(self.request(), query)

    async def acknowledge(self, epoch: str, session_id: str, now: float) -> None:
        await self.work(epoch, now, lambda conn: conn.execute("UPDATE v2_watch_intents SET cleaned=1 WHERE session_id=? AND closed=1", (session_id,)).rowcount)
