"""Synthetic compatibility fixtures; never access an operational DB."""

import sqlite3
from contextlib import closing

import pytest

from discordbot.storage.adapters.schema import create_legacy_schema, validate
from discordbot.storage.ports.contracts import DatabaseState


def test_legacy_schema_preserves_global_and_fractional_values(tmp_path):
    with closing(sqlite3.connect(tmp_path / "synthetic.db")) as conn:
        create_legacy_schema(conn)
        conn.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?)", [
            (10, 0, 0, 1, 0, None, None),
            (10, 100, 31, 2, 119.5, 2, 29),
            (10, 200, 7, 1, 60, 2, 31),
        ])
        conn.execute("INSERT INTO favorites VALUES (?,?,?)", (10, "unchanged?x=1", "친구's\n음악"))
        before = validate(conn)
        assert before.state is DatabaseState.VALID
        assert ("legacy_global_users", 1) in before.warnings
        assert ("invalid_calendar_birthdays", 1) in before.warnings
        assert conn.execute("SELECT total_vc_seconds FROM users WHERE guild_id=100").fetchone() == (119.5,)


@pytest.mark.parametrize("ddl", [
    "CREATE TABLE users (user_id INTEGER)",
    "CREATE TABLE users (user_id INTEGER, guild_id INTEGER, xp INTEGER, level INTEGER, total_vc_seconds INTEGER, birth_month INTEGER, PRIMARY KEY(user_id,guild_id))",
])
def test_partial_schema_is_rejected_without_repair(tmp_path, ddl):
    with closing(sqlite3.connect(tmp_path / "partial.db")) as conn:
        conn.execute(ddl)
        before = conn.execute("SELECT sql FROM sqlite_master").fetchall()
        assert validate(conn).state is DatabaseState.WRONG_SCHEMA
        assert conn.execute("SELECT sql FROM sqlite_master").fetchall() == before
