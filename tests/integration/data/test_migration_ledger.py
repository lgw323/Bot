import sqlite3
from contextlib import closing

import pytest

from discordbot.platform.errors import DataIntegrityError
from discordbot.storage.adapters.migrations import MIGRATIONS, Migration, apply_pending, validate_ledger
from discordbot.storage.adapters.schema import validate


def test_step_failure_rolls_back_ddl_and_ledger_then_resumes(legacy_db):
    faulty = (MIGRATIONS[0], Migration(2, "legacy-guild-query-indexes", (
        "CREATE INDEX v2_users_guild ON users(guild_id,user_id)",
        "CREATE INDEX v2_missing ON users(missing_column)",
    )))
    with closing(sqlite3.connect(legacy_db, isolation_level=None)) as conn:
        before = validate(conn)
        with pytest.raises(sqlite3.OperationalError):
            apply_pending(conn, lambda: None, faulty)
        assert validate_ledger(conn) == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='v2_users_guild'").fetchone() is None
    # Fresh connection represents retry/restart, not an in-memory resume flag.
    with closing(sqlite3.connect(legacy_db, isolation_level=None)) as conn:
        assert apply_pending(conn, lambda: None) == 2
        rows = conn.execute("SELECT * FROM v2_migrations").fetchall()
        assert apply_pending(conn, lambda: None, tuple(reversed(MIGRATIONS))) == 2
        assert conn.execute("SELECT * FROM v2_migrations").fetchall() == rows
        after = validate(conn)
        assert (after.counts, after.data_checksum) == (before.counts, before.data_checksum)


@pytest.mark.parametrize("change", [
    "UPDATE v2_migrations SET checksum='changed' WHERE version=1",
    "UPDATE v2_migrations SET identity='changed' WHERE version=1",
    "UPDATE v2_migrations SET applied_at='invalid' WHERE version=1",
    "DELETE FROM v2_migrations WHERE version=1",
    "DROP INDEX v2_users_guild",
])
def test_ledger_or_applied_schema_tampering_is_fail_closed(legacy_db, change):
    with closing(sqlite3.connect(legacy_db, isolation_level=None)) as conn:
        apply_pending(conn, lambda: None)
        conn.execute(change)
        with pytest.raises(DataIntegrityError):
            apply_pending(conn, lambda: None)


@pytest.mark.parametrize("registry", [
    (MIGRATIONS[0], MIGRATIONS[0]),
    (Migration(2, "gap", ()),),
    (Migration(1, "drop", ("DROP TABLE users",)),),
    (Migration(1, "change", ("UPDATE users SET xp=0",)),),
])
def test_invalid_or_destructive_registry_is_rejected_before_any_change(legacy_db, registry):
    with closing(sqlite3.connect(legacy_db, isolation_level=None)) as conn:
        before = conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
        with pytest.raises(DataIntegrityError):
            apply_pending(conn, lambda: None, registry)
        assert conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall() == before
