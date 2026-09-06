"""Current whole-file Fernet envelope and constrained legacy SQL decoding."""

from __future__ import annotations

import base64
import sqlite3

from cryptography.fernet import Fernet, InvalidToken

from discordbot.platform.errors import ConfigurationError, DataIntegrityError
from discordbot.storage.adapters.execution import WorkControl
from discordbot.storage.adapters.schema import SCHEMA
from discordbot.storage.adapters.engagement_schema import ENGAGEMENT_TABLES

BACKUP_HEADER = b"DISCORDBOT_BACKUP_V2\n"


def cipher_from(key: bytes | None) -> Fernet:
    if key is None:
        raise ConfigurationError("backup encryption key required")
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise ConfigurationError("invalid backup encryption key") from None


def decode(payload: bytes, key: bytes | None, maximum: int) -> tuple[str, bool]:
    if not payload or len(payload) > maximum:
        raise DataIntegrityError("backup size is invalid")
    legacy = not payload.startswith(BACKUP_HEADER)
    try:
        plaintext = payload if legacy else cipher_from(key).decrypt(payload[len(BACKUP_HEADER):])
        return plaintext.decode("utf-8"), legacy
    except (InvalidToken, UnicodeError):
        raise DataIntegrityError("backup authentication or encoding failed") from None


def _authorizer(action: int, arg1: str | None, arg2: str | None, database: str | None, source: str | None) -> int:
    tables = set(SCHEMA) | ENGAGEMENT_TABLES | {"v2_migrations", "sqlite_master"}
    allowed = False
    if source is not None or database not in {None, "main"}:
        return sqlite3.SQLITE_DENY
    if action in {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SELECT}:
        allowed = True
    elif action in {sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT}:
        allowed = arg1 in tables
    elif action == sqlite3.SQLITE_UPDATE:
        allowed = arg1 == "sqlite_master"  # SQLite's own CREATE bookkeeping only.
    elif action == sqlite3.SQLITE_CREATE_TABLE:
        allowed = arg1 in tables - {"sqlite_master"}
    elif action == sqlite3.SQLITE_CREATE_INDEX:
        allowed = arg2 in tables and bool(arg1) and arg1.startswith(("sqlite_autoindex_", "v2_"))
    elif action == sqlite3.SQLITE_REINDEX:
        # SQLite requests this action when restoring an index on populated rows.
        # Limit it to the four reviewed migration indexes, never arbitrary objects.
        allowed = arg1 in {"v2_users_guild", "v2_users_birthday", "v2_watch_guild", "v2_engagement_expiry"}
    return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY


def _protected_value(value: str, key: bytes | None) -> str:
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeError):
        return value
    if len(raw) < 73 or raw[0] != 0x80:
        return value
    try:
        return cipher_from(key).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError):
        raise DataIntegrityError("legacy backup value authentication failed") from None


def restore_script(conn: sqlite3.Connection, sql: str, *, legacy: bool, key: bytes | None, control: WorkControl) -> None:
    """Execute only a dump grammar's SQLite actions in a disposable candidate.

    ATTACH/PRAGMA/functions/triggers/views/virtual tables/deletes are denied. SQLite
    parses multiline strings and quoting itself; no SQL-line interpolation or eval.
    """
    if not sql.strip().startswith("BEGIN TRANSACTION;") or not sql.rstrip().endswith("COMMIT;"):
        raise DataIntegrityError("backup transaction boundaries are missing")
    conn.set_authorizer(_authorizer)
    conn.set_progress_handler(control.progress, 1000)
    try:
        conn.executescript(sql)
        if conn.in_transaction:
            raise DataIntegrityError("backup transaction is incomplete")
    except sqlite3.Error:
        control.checkpoint()
        raise DataIntegrityError("backup SQL is invalid or disallowed") from None
    finally:
        conn.set_authorizer(None)
    if legacy:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in ("favorites", "music_play_counts"):
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    continue  # Full schema validation rejects partial dumps later.
                for rowid, url, title in conn.execute(f'SELECT rowid,url,title FROM "{table}"'):
                    control.checkpoint()
                    if not isinstance(url, str) or not isinstance(title, str):
                        raise DataIntegrityError("legacy backup field shape is invalid")
                    decoded = (_protected_value(url, key), _protected_value(title, key))
                    if decoded != (url, title):
                        conn.execute(f'UPDATE "{table}" SET url=?,title=? WHERE rowid=?', (*decoded, rowid))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
