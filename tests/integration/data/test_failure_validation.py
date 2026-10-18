import asyncio
import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from discordbot.platform.errors import ConfigurationError, ConflictError, DataIntegrityError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.migrations import apply_pending
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


def request():
    return DatabaseRequest.within(5, "failure-validation")


@pytest.mark.parametrize("options", [
    {"queue_capacity": -1}, {"queue_capacity": 65}, {"page_limit": 1001},
    {"busy_timeout_seconds": float("nan")}, {"busy_timeout_seconds": 2},
    {"shutdown_grace_seconds": 11}, {"max_backup_bytes": 512},
])
def test_database_config_rejects_unbounded_or_invalid_policy(tmp_path, options):
    with pytest.raises(ConfigurationError):
        DatabaseConfig(tmp_path / "unused.db", **options)


@pytest.mark.asyncio
@pytest.mark.parametrize("change,state", [
    ("UPDATE users SET xp=-1 WHERE guild_id=100", DatabaseState.INVALID_DATA),
    ("UPDATE users SET birth_day=NULL WHERE guild_id=100", DatabaseState.INVALID_DATA),
    ("UPDATE watch_playlists SET session_id='orphan' WHERE session_id='session-one'", DatabaseState.INVALID_DATA),
    ("CREATE TRIGGER unexpected AFTER INSERT ON favorites BEGIN DELETE FROM users; END", DatabaseState.WRONG_SCHEMA),
    ("ALTER TABLE users ADD COLUMN unexpected TEXT", DatabaseState.WRONG_SCHEMA),
    ("CREATE TABLE unknown(value TEXT)", DatabaseState.WRONG_SCHEMA),
    ("PRAGMA user_version=9", DatabaseState.WRONG_SCHEMA),
])
async def test_semantic_and_schema_failure_never_repairs_or_publishes(legacy_db, tmp_path, change, state):
    with closing(sqlite3.connect(legacy_db)) as conn:
        conn.execute(change)
        conn.commit()
    before = legacy_db.read_bytes()
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    try:
        assert (await db.inspect(request())).state is state
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).migrated_copy(legacy_db, tmp_path / "rejected.db", request())
        assert legacy_db.read_bytes() == before
        assert not (tmp_path / "rejected.db").exists()
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_checksum_failure_blocks_startup_and_backup(legacy_db, tmp_path):
    with closing(sqlite3.connect(legacy_db, isolation_level=None)) as conn:
        apply_pending(conn, lambda: None)
        conn.execute("UPDATE v2_migrations SET checksum='invalid'")
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    assert (await db.inspect(request())).state is DatabaseState.INVALID_LEDGER
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).backup(tmp_path / "rejected.sql", Fernet.generate_key(), request())
        assert not (tmp_path / "rejected.sql").exists()
        with pytest.raises(DataIntegrityError):
            await db.start()
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_backup_missing_key_size_and_tampering_keep_last_good(database, tmp_path):
    backup = tmp_path / "backup.sql"
    backup.write_bytes(b"last-good")
    with pytest.raises(ConfigurationError):
        await DataRecovery(database).backup(backup, b"bad", request())
    assert backup.read_bytes() == b"last-good"
    key = Fernet.generate_key()
    await DataRecovery(database).backup(backup, key, request())
    tampered = backup.read_bytes()
    backup.write_bytes(tampered[:-10] + b"xxxxxxxxxx")
    db = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).restore_copy(RecoveryCandidate(backup, key), tmp_path / "tampered.db", request())
        assert not (tmp_path / "tampered.db").exists()
    finally:
        await db.stop()
    small = SqliteDatabase(DatabaseConfig(database.config.path, max_backup_bytes=1024))
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(small).backup(backup, key, request())
        assert backup.read_bytes() == tampered[:-10] + b"xxxxxxxxxx"
    finally:
        await small.stop()


@pytest.mark.asyncio
async def test_restore_failure_preserves_corrupt_canonical_and_plaintext_source(tmp_path):
    canonical = tmp_path / "corrupt.db"
    canonical.write_bytes(b"corrupt-but-valuable")
    invalid = tmp_path / "invalid.sql"
    invalid.write_bytes(b"BEGIN TRANSACTION; COMMIT;")
    db = SqliteDatabase(DatabaseConfig(canonical))
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).restore_copy(RecoveryCandidate(invalid), canonical, request())
        assert canonical.read_bytes() == b"corrupt-but-valuable"
        with pytest.raises(ConflictError):
            await DataRecovery(db).bootstrap(request())
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_typed_errors_and_bounded_observations_never_include_raw_row(database):
    def fail(conn):
        raise ValueError("user-999999999999999999 secret-capability raw-title")
    for _ in range(50):
        with pytest.raises(DataIntegrityError) as failure:
            await database.read(request(), fail)
        assert "999999" not in str(failure.value)
        assert failure.value.__suppress_context__
    assert len(database.observations) <= 4 * (database.config.queue_capacity + 2)
    assert "secret-capability" not in repr(database.observations)
    assert database.admitted == (0, 0)


@pytest.mark.asyncio
async def test_normal_read_cannot_mutate_database(database):
    from discordbot.platform.errors import DatabaseUnavailableError
    with pytest.raises(DatabaseUnavailableError):
        await database.read(request(), lambda conn: conn.execute("DELETE FROM users"))
    assert await database.read(request(), lambda conn: conn.execute("SELECT count(*) FROM users").fetchone()[0]) == 3
