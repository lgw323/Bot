"""Transactional dedupe and voice ownership on the Phase 3 writer lane."""

from datetime import date
import sqlite3

from discordbot.engagement.domain.policy import Progress
from discordbot.engagement.ports.events import EngagementConfig, VoiceEvent
from discordbot.engagement.ports.repository import MemberData
from discordbot.platform.errors import CapacityError, ConflictError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.inputs import identifier, nonnegative, text_value
from discordbot.storage.adapters.migrations import validate_ledger
from discordbot.storage.adapters.schema import projection
from discordbot.storage.ports.contracts import DatabaseRequest


def _progress(conn: sqlite3.Connection, guild: int, user: int, xp: int = 0, seconds: int = 0) -> None:
    conn.execute("INSERT OR IGNORE INTO users(user_id,guild_id) VALUES (?,?)", (user, guild))
    conn.execute("UPDATE users SET xp=xp+?,total_vc_seconds=total_vc_seconds+? WHERE guild_id=? AND user_id=?", (xp, seconds, guild, user))
    stored = conn.execute("SELECT xp,total_vc_seconds,level FROM users WHERE guild_id=? AND user_id=?", (guild, user)).fetchone()
    nonnegative(stored[0], integer=True)
    nonnegative(stored[1])
    level = max(stored[2], Progress(stored[0], stored[1]).level)
    conn.execute("UPDATE users SET level=? WHERE guild_id=? AND user_id=?", (level, guild, user))


class SqliteEngagementEvents:
    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    async def begin_epoch(self, epoch: str, request: DatabaseRequest) -> None:
        text_value(epoch, nonempty=True)
        def work(conn: sqlite3.Connection) -> None:
            if validate_ledger(conn) < 3:
                raise ConflictError("engagement requires an explicitly migrated copy")
            previous = conn.execute("SELECT epoch FROM v2_engagement_runtime WHERE id=1").fetchone()
            if previous and previous[0] == epoch:
                return
            # Persist only already observed segments after crash; never invent offline time.
            for guild, user, duration in conn.execute("SELECT guild_id,user_id,duration FROM v2_engagement_voice"):
                if duration >= 60:
                    _progress(conn, guild, user, seconds=int(duration))
            conn.execute("DELETE FROM v2_engagement_voice")
            conn.execute("INSERT INTO v2_engagement_runtime VALUES (1,?) ON CONFLICT(id) DO UPDATE SET epoch=excluded.epoch", (epoch,))
        await self._db.write(request, work)

    async def apply_text(self, guild_id: int, user_id: int, event_id: str, xp: int,
                         created: float, now: float, config: EngagementConfig, request: DatabaseRequest) -> bool:
        identifier(guild_id)
        identifier(user_id)
        text_value(event_id, nonempty=True)
        nonnegative(xp, integer=True)
        nonnegative(created)
        nonnegative(now)
        retention = config.receipt_days * 86400
        if created <= now - retention or created > now + 300:
            return False
        def work(conn: sqlite3.Connection) -> bool:
            conn.execute("DELETE FROM v2_engagement_events WHERE expires<=?", (now,))
            if conn.execute("SELECT 1 FROM v2_engagement_events WHERE guild_id=? AND event_id=?", (guild_id, event_id)).fetchone():
                return False
            if conn.execute("SELECT count(*) FROM v2_engagement_events").fetchone()[0] >= config.receipt_capacity:
                raise CapacityError("engagement receipt capacity exhausted")
            conn.execute("INSERT INTO v2_engagement_events VALUES (?,?,?)", (guild_id, event_id, created + retention))
            if xp:
                _progress(conn, guild_id, user_id, xp=xp)
            return True
        return await self._db.write(request, work)

    async def apply_voice(self, event: VoiceEvent, capacity: int, request: DatabaseRequest) -> bool:
        identifier(event.guild_id)
        identifier(event.user_id)
        if event.channel_id is not None:
            identifier(event.channel_id)
        nonnegative(event.tick)
        nonnegative(event.sequence, integer=True)
        text_value(event.epoch, nonempty=True)
        text_value(event.stream, nonempty=True)
        def work(conn: sqlite3.Connection) -> bool:
            runtime = conn.execute("SELECT epoch FROM v2_engagement_runtime WHERE id=1").fetchone()
            if runtime != (event.epoch,):
                raise ConflictError("voice event belongs to an inactive process epoch")
            row = conn.execute("SELECT stream,sequence,channel_id,muted,tick,duration FROM v2_engagement_voice WHERE guild_id=? AND user_id=?", (event.guild_id, event.user_id)).fetchone()
            if row and row[0] == event.stream and event.sequence <= row[1]:
                return False
            if not row and conn.execute("SELECT count(*) FROM v2_engagement_voice").fetchone()[0] >= capacity:
                raise CapacityError("voice session capacity exhausted")
            duration = 0.0 if not row else row[5]
            if row and event.tick < row[4]:
                raise ConflictError("voice event time moved backwards")
            if row and row[2] is not None and not row[3]:
                duration += event.tick - row[4]
            if event.channel_id is None:
                if duration >= 60:
                    _progress(conn, event.guild_id, event.user_id, seconds=int(duration))
                duration = 0.0
            conn.execute("INSERT INTO v2_engagement_voice VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET epoch=excluded.epoch,stream=excluded.stream,sequence=excluded.sequence,channel_id=excluded.channel_id,muted=excluded.muted,tick=excluded.tick,duration=excluded.duration", (
                event.guild_id, event.user_id, event.epoch, event.stream, event.sequence,
                event.channel_id, int(event.muted), event.tick, duration))
            return True
        return await self._db.write(request, work)

    async def flush_voice(self, epoch: str, tick: float, request: DatabaseRequest, *, observed_only: bool = False) -> None:
        nonnegative(tick)
        def work(conn: sqlite3.Connection) -> None:
            if conn.execute("SELECT epoch FROM v2_engagement_runtime WHERE id=1").fetchone() != (epoch,):
                return
            for guild, user, channel, muted, previous, duration in conn.execute("SELECT guild_id,user_id,channel_id,muted,tick,duration FROM v2_engagement_voice"):
                if channel is not None and not muted and not observed_only:
                    duration += max(0, tick - previous)
                if duration >= 60:
                    _progress(conn, guild, user, seconds=int(duration))
            conn.execute("DELETE FROM v2_engagement_voice")
            conn.execute("DELETE FROM v2_engagement_runtime WHERE id=1")
        await self._db.write(request, work)

    async def ranking(self, guild_id: int, request: DatabaseRequest) -> tuple[MemberData, ...]:
        identifier(guild_id)
        def read(conn: sqlite3.Connection) -> tuple[MemberData, ...]:
            # Streaming top ten uses the very same policy as profile, with bounded memory.
            top: list[MemberData] = []
            for row in conn.execute(f'SELECT {projection(conn, "users")} FROM users WHERE guild_id=? ORDER BY user_id', (guild_id,)):
                top.append(MemberData(*row))
                top.sort(key=lambda member: (-Progress(member.xp, member.total_vc_seconds).total, member.user_id))
                del top[10:]
            return tuple(top)
        return await self._db.read(request, read)

    async def birthdays(self, guild_id: int, request: DatabaseRequest, *, offset: int = 0) -> tuple[MemberData, ...]:
        identifier(guild_id)
        nonnegative(offset, integer=True)
        return await self._db.read(request, lambda conn: tuple(MemberData(*row) for row in conn.execute(
            f'SELECT {projection(conn, "users")} FROM users WHERE guild_id=? AND birth_month IS NOT NULL ORDER BY birth_month,birth_day,user_id LIMIT 100 OFFSET ?', (guild_id, offset))))

    async def delete_birthday(self, guild_id: int, user_id: int, request: DatabaseRequest) -> bool:
        identifier(guild_id)
        identifier(user_id)
        # V1 rowcount semantics: an existing member without a birthday still returns success.
        return await self._db.write(request, lambda conn: conn.execute("UPDATE users SET birth_month=NULL,birth_day=NULL WHERE guild_id=? AND user_id=?", (guild_id, user_id)).rowcount > 0)

    async def claim_birthday(self, guild_id: int, today: date, request: DatabaseRequest) -> bool:
        identifier(guild_id)
        def work(conn: sqlite3.Connection) -> bool:
            previous = conn.execute("SELECT day FROM v2_engagement_birthday WHERE guild_id=?", (guild_id,)).fetchone()
            if previous and previous[0] >= today.isoformat():
                return False
            conn.execute("INSERT INTO v2_engagement_birthday VALUES (?,?,'claimed') ON CONFLICT(guild_id) DO UPDATE SET day=excluded.day,status='claimed'", (guild_id, today.isoformat()))
            return True
        return await self._db.write(request, work)

    async def finish_birthday(self, guild_id: int, today: date, status: str, request: DatabaseRequest) -> None:
        if status not in {"sent", "uncertain"}:
            raise ConflictError("invalid delivery outcome")
        await self._db.write(request, lambda conn: conn.execute("UPDATE v2_engagement_birthday SET status=? WHERE guild_id=? AND day=?", (status, guild_id, today.isoformat())).rowcount)
