"""Read-only legacy validation and explicit synthetic/empty schema creation."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date

from discordbot.storage.ports.contracts import DatabaseState, ValidationReport

# Fixed, reviewed identifiers only. No identifier is taken from user input.
SCHEMA = {
    "users": (("user_id", "INTEGER", 1), ("guild_id", "INTEGER", 2),
              ("xp", "INTEGER", 0), ("level", "INTEGER", 0), ("total_vc_seconds", "INTEGER", 0),
              ("birth_month", "INTEGER", 0), ("birth_day", "INTEGER", 0)),
    "music_settings": (("guild_id", "INTEGER", 1), ("volume", "REAL", 0)),
    "music_play_counts": (("guild_id", "INTEGER", 1), ("url", "TEXT", 2),
                          ("title", "TEXT", 0), ("play_count", "INTEGER", 0)),
    "favorites": (("user_id", "INTEGER", 1), ("url", "TEXT", 2), ("title", "TEXT", 0)),
    "watch_sessions": (("session_id", "TEXT", 1), ("guild_id", "INTEGER", 0),
                       ("created_by", "INTEGER", 0), ("created_at", "TIMESTAMP", 0),
                       ("channel_id", "INTEGER", 0), ("message_id", "INTEGER", 0)),
    "watch_playlists": (("session_id", "TEXT", 1), ("video_url", "TEXT", 2),
                        ("video_title", "TEXT", 0), ("added_by", "TEXT", 0), ("order_index", "INTEGER", 0)),
}
OPTIONAL_PAIRS = {"users": ("birth_month", "birth_day"), "watch_sessions": ("channel_id", "message_id")}
LEGACY_DDL = (
    "CREATE TABLE users (user_id INTEGER, guild_id INTEGER, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, total_vc_seconds INTEGER DEFAULT 0, birth_month INTEGER, birth_day INTEGER, PRIMARY KEY(user_id,guild_id))",
    "CREATE TABLE music_settings (guild_id INTEGER PRIMARY KEY, volume REAL DEFAULT 1.0)",
    "CREATE TABLE music_play_counts (guild_id INTEGER, url TEXT, title TEXT, play_count INTEGER DEFAULT 1, PRIMARY KEY(guild_id,url))",
    "CREATE TABLE favorites (user_id INTEGER, url TEXT, title TEXT, PRIMARY KEY(user_id,url))",
    "CREATE TABLE watch_sessions (session_id TEXT PRIMARY KEY, guild_id INTEGER, created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, channel_id INTEGER, message_id INTEGER)",
    "CREATE TABLE watch_playlists (session_id TEXT, video_url TEXT, video_title TEXT, added_by TEXT, order_index INTEGER, PRIMARY KEY(session_id,video_url))",
)
DEFAULTS = {
    ("users", "xp"): "0", ("users", "level"): "1", ("users", "total_vc_seconds"): "0",
    ("music_settings", "volume"): "1.0", ("music_play_counts", "play_count"): "1",
    ("watch_sessions", "created_at"): "CURRENT_TIMESTAMP",
}


def create_legacy_schema(conn: sqlite3.Connection) -> None:
    """Only bootstrap/candidate builders call this; startup never calls it."""
    for statement in LEGACY_DDL:
        conn.execute(statement)


def columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    if table not in SCHEMA:
        raise ValueError("unknown legacy table")
    return tuple(row[1] for row in conn.execute(f'PRAGMA table_info("{table}")'))


def projection(conn: sqlite3.Connection, table: str) -> str:
    present = columns(conn, table)
    return ",".join(f'"{name}"' if name in present else f'NULL AS "{name}"' for name, _, _ in SCHEMA[table])


def _integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _number(value: object, minimum: float = 0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


def _text(value: object, nonempty: bool = False) -> bool:
    return isinstance(value, str) and (bool(value) or not nonempty)


def _valid_row(table: str, row: tuple) -> bool:
    if table == "users":
        uid, gid, xp, level, seconds, month, day = row
        return (_integer(uid, 1) and _integer(gid) and _integer(xp) and _integer(level, 1)
                and _number(seconds) and ((month is None and day is None)
                or (type(month) is int and type(day) is int)))
    if table == "favorites":
        return _integer(row[0], 1) and _text(row[1], True) and _text(row[2])
    if table == "music_settings":
        return _integer(row[0], 1) and _number(row[1])
    if table == "music_play_counts":
        return _integer(row[0], 1) and _text(row[1], True) and _text(row[2]) and _integer(row[3])
    if table == "watch_sessions":
        return (_text(row[0], True) and _integer(row[1], 1) and _integer(row[2], 1)
                and _text(row[3], True) and all(v is None or _integer(v, 1) for v in row[4:]))
    return all(_text(v, i < 2) for i, v in enumerate(row[:4])) and _integer(row[4])


def validate(conn: sqlite3.Connection) -> ValidationReport:
    """No repair, rounding, URL normalization, trimming, or raw row diagnostics."""
    if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        return ValidationReport(DatabaseState.CORRUPT)
    objects = conn.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    tables = {name for kind, name in objects if kind == "table"}
    if (tables - {"v2_migrations"} != set(SCHEMA)
            or any(kind not in {"table", "index"} for kind, _ in objects)
            or conn.execute("PRAGMA user_version").fetchone()[0] != 0):
        return ValidationReport(DatabaseState.WRONG_SCHEMA)
    old_pairs = []
    for table, expected in SCHEMA.items():
        info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        actual = tuple((r[1], r[2].upper(), r[5]) for r in info)
        if any(r[3] != 0 or (r[4].upper() if r[4] is not None else None) != DEFAULTS.get((table, r[1])) for r in info):
            return ValidationReport(DatabaseState.WRONG_SCHEMA)
        if actual == expected:
            continue
        if table in OPTIONAL_PAIRS and actual == expected[:-2]:
            old_pairs.append(table)
        else:
            return ValidationReport(DatabaseState.WRONG_SCHEMA)
    digest = hashlib.sha256()
    counts = []
    globals_count = invalid_dates = 0
    for table in sorted(SCHEMA):
        key = ",".join(f'"{name}"' for name, _, pk in SCHEMA[table] if pk)
        rows = conn.execute(f'SELECT {projection(conn, table)} FROM "{table}" ORDER BY {key}')
        count = 0
        digest.update(table.encode("ascii"))
        for row in rows:
            if not _valid_row(table, row):
                return ValidationReport(DatabaseState.INVALID_DATA)
            count += 1
            digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
            digest.update(b"\n")
            if table == "users":
                globals_count += row[1] == 0
                if row[5] is not None:
                    try:
                        date(2000, row[5], row[6])
                    except ValueError:
                        invalid_dates += 1
        counts.append((table, count))
    orphans = conn.execute("SELECT count(*) FROM watch_playlists p LEFT JOIN watch_sessions s ON s.session_id=p.session_id WHERE s.session_id IS NULL").fetchone()[0]
    if orphans:
        return ValidationReport(DatabaseState.INVALID_DATA)
    return ValidationReport(
        DatabaseState.VALID, "legacy-pairs-absent:" + ",".join(old_pairs) if old_pairs else "legacy-current",
        counts=tuple(counts), data_checksum=digest.hexdigest(),
        warnings=(("legacy_global_users", globals_count), ("invalid_calendar_birthdays", invalid_dates)),
    )
