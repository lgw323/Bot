"""Legacy users adapter with explicit guild predicates and unrounded seconds."""

import sqlite3

from discordbot.engagement.ports.repository import MemberData
from discordbot.platform.errors import ConflictError, ValidationError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.inputs import identifier, nonnegative
from discordbot.storage.adapters.schema import columns, projection
from discordbot.storage.ports.contracts import DatabaseRequest, require_page


class SqliteEngagementRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    async def get_member(self, guild_id: int, user_id: int, request: DatabaseRequest) -> MemberData | None:
        identifier(guild_id)
        identifier(user_id)

        def query(conn: sqlite3.Connection) -> MemberData | None:
            row = conn.execute(f'SELECT {projection(conn, "users")} FROM users WHERE guild_id=? AND user_id=?', (guild_id, user_id)).fetchone()
            return MemberData(*row) if row else None

        return await self._db.read(request, query)

    async def list_members(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[MemberData, ...]:
        identifier(guild_id)
        require_page(limit, offset, self._db.config.page_limit)

        def query(conn: sqlite3.Connection) -> tuple[MemberData, ...]:
            rows = conn.execute(f'SELECT {projection(conn, "users")} FROM users WHERE guild_id=? ORDER BY user_id LIMIT ? OFFSET ?', (guild_id, limit, offset))
            return tuple(MemberData(*row) for row in rows)

        return await self._db.read(request, query)

    async def add_progress(self, guild_id: int, user_id: int, xp: int, seconds: int | float, request: DatabaseRequest, *, level: int | None = None) -> None:
        identifier(guild_id)
        identifier(user_id)
        nonnegative(xp, integer=True)
        nonnegative(seconds)
        if level is not None:
            identifier(level)

        def mutation(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT OR IGNORE INTO users (user_id,guild_id) VALUES (?,?)", (user_id, guild_id))
            conn.execute("UPDATE users SET xp=xp+?,total_vc_seconds=total_vc_seconds+?,level=COALESCE(?,level) WHERE guild_id=? AND user_id=?", (xp, seconds, level, guild_id, user_id))
            updated = conn.execute("SELECT xp,total_vc_seconds FROM users WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
            nonnegative(updated[0], integer=True)
            nonnegative(updated[1])

        await self._db.write(request, mutation)

    async def set_birthday(self, guild_id: int, user_id: int, month: int | None, day: int | None, request: DatabaseRequest) -> None:
        identifier(guild_id)
        identifier(user_id)
        if not ((month is None and day is None) or (type(month) is int and type(day) is int)):
            raise ValidationError("birthday storage pair must be complete")

        def mutation(conn: sqlite3.Connection) -> None:
            if "birth_day" not in columns(conn, "users"):
                raise ConflictError("explicit schema expansion required for birthday writes")
            if month is not None:
                conn.execute("INSERT OR IGNORE INTO users (user_id,guild_id) VALUES (?,?)", (user_id, guild_id))
            conn.execute("UPDATE users SET birth_month=?,birth_day=? WHERE guild_id=? AND user_id=?", (month, day, guild_id, user_id))

        await self._db.write(request, mutation)
