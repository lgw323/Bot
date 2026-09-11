"""Expand-only ledger, transactional steps and deterministic resume."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from discordbot.platform.errors import DataIntegrityError
from discordbot.storage.adapters.engagement_schema import ENGAGEMENT_DDL, ENGAGEMENT_TABLES
from discordbot.storage.adapters.watch_schema import WATCH_DDL, WATCH_TABLES
from discordbot.storage.adapters.music_schema import MUSIC_DDL, MUSIC_TABLES


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    identity: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        value = json.dumps((self.version, self.identity, self.statements), separators=(",", ":"))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(1, "legacy-nullable-pairs", (
        "ALTER TABLE users ADD COLUMN birth_month INTEGER",
        "ALTER TABLE users ADD COLUMN birth_day INTEGER",
        "ALTER TABLE watch_sessions ADD COLUMN channel_id INTEGER",
        "ALTER TABLE watch_sessions ADD COLUMN message_id INTEGER",
    )),
    Migration(2, "legacy-guild-query-indexes", (
        "CREATE INDEX v2_users_guild ON users(guild_id,user_id)",
        "CREATE INDEX v2_users_birthday ON users(guild_id,birth_month,birth_day)",
        "CREATE INDEX v2_watch_guild ON watch_sessions(guild_id,created_at,session_id)",
    )),
    Migration(3, "engagement-event-ownership", ENGAGEMENT_DDL),
    Migration(4, "watch-process-ownership", WATCH_DDL),
    Migration(5, "music-logical-playback-start", MUSIC_DDL),
)
LEDGER_DDL = """CREATE TABLE IF NOT EXISTS v2_migrations (
    version INTEGER PRIMARY KEY,
    identity TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state='applied'),
    applied_at TEXT NOT NULL
)"""


def ordered(migrations: tuple[Migration, ...]) -> tuple[Migration, ...]:
    result = tuple(sorted(migrations, key=lambda m: m.version))
    if (tuple(m.version for m in result) != tuple(range(1, len(result) + 1))
            or len({m.identity for m in result}) != len(result)
            or any(not re.fullmatch(r"[a-z0-9-]{1,80}", m.identity) for m in result)):
        raise DataIntegrityError("invalid migration registry")
    # Only reviewed nullable/metadata expansions and legacy-table indexes.
    for migration in result:
        for statement in migration.statements:
            if statement in MIGRATIONS[0].statements or statement in ENGAGEMENT_DDL or statement in WATCH_DDL or statement in MUSIC_DDL:
                continue
            if not re.fullmatch(r"CREATE INDEX v2_[a-z_]+ ON (users|music_settings|music_play_counts|favorites|watch_sessions|watch_playlists)\([a-z_,]+\)", statement):
                raise DataIntegrityError("migration is not an approved expansion")
    return result


def validate_ledger(conn: sqlite3.Connection, migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    registry = ordered(migrations)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v2_migrations'").fetchone():
        if {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & (ENGAGEMENT_TABLES | WATCH_TABLES | MUSIC_TABLES):
            raise DataIntegrityError("engagement expansion has no migration ledger")
        return 0
    layout = tuple((r[1], r[2], r[5]) for r in conn.execute("PRAGMA table_info(v2_migrations)"))
    if layout != (("version", "INTEGER", 1), ("identity", "TEXT", 0), ("checksum", "TEXT", 0),
                  ("state", "TEXT", 0), ("applied_at", "TEXT", 0)):
        raise DataIntegrityError("invalid migration ledger layout")
    rows = conn.execute("SELECT version,identity,checksum,state,applied_at FROM v2_migrations ORDER BY version").fetchall()
    extensions = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & ENGAGEMENT_TABLES
    if extensions and not any(row[0] == 3 for row in rows):
        raise DataIntegrityError("engagement expansion has no applied ledger step")
    watch = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & WATCH_TABLES
    if watch and not any(row[0] == 4 for row in rows):
        raise DataIntegrityError("Watch expansion has no applied ledger step")
    music = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & MUSIC_TABLES
    if music and not any(row[0] == 5 for row in rows):
        raise DataIntegrityError("Music expansion has no applied ledger step")
    if len(rows) > len(registry):
        raise DataIntegrityError("unknown migration ledger version")
    for row, migration in zip(rows, registry):
        if row[:4] != (migration.version, migration.identity, migration.checksum, "applied"):
            raise DataIntegrityError("migration ledger identity or checksum mismatch")
        try:
            stamp = datetime.fromisoformat(row[4])
            if stamp.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError):
            raise DataIntegrityError("invalid migration applied time") from None
        for statement in migration.statements:
            if statement.startswith("ALTER TABLE"):
                _, _, table, _, _, column, _ = statement.split()
                if column not in {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}:
                    raise DataIntegrityError("applied expansion is missing")
            else:
                name = statement.split()[2]
                kind = "table" if statement.startswith("CREATE TABLE") else "index"
                actual = conn.execute("SELECT sql FROM sqlite_master WHERE type=? AND name=?", (kind, name)).fetchone()
                if actual is None or actual[0] != statement:
                    raise DataIntegrityError("applied schema object definition mismatch")
    return len(rows)


def apply_pending(conn: sqlite3.Connection, checkpoint: Callable[[], None], migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    """Internal candidate-only operation; each DDL step and ledger row commit together.

    A failed step has no durable applied marker. Previously committed expansions stay
    readable and rerunning the same registry resumes at the first unapplied step.
    """
    registry = ordered(migrations)
    validate_ledger(conn, registry)
    for migration in registry:
        checkpoint()
        conn.execute("BEGIN IMMEDIATE")
        try:
            version = validate_ledger(conn, registry)
            if migration.version <= version:
                conn.rollback()
                continue
            conn.execute(LEDGER_DDL)
            for statement in migration.statements:
                checkpoint()
                if statement.startswith("ALTER TABLE"):
                    _, _, table, _, _, column, _ = statement.split()
                    if column in {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}:
                        continue
                conn.execute(statement)
            conn.execute("INSERT INTO v2_migrations VALUES (?,?,?,?,?)", (
                migration.version, migration.identity, migration.checksum, "applied",
                datetime.now(timezone.utc).isoformat(),
            ))
            checkpoint()
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return validate_ledger(conn, registry)
