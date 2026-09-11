import hashlib
import sqlite3
from contextlib import closing

import pytest

import database_manager
from discordbot.platform.errors import ConflictError, DataIntegrityError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.adapters.schema import LEGACY_DDL, validate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


def request():
    return DatabaseRequest.within(5, "synthetic-migration")


@pytest.mark.asyncio
async def test_migration_publishes_only_verified_new_copy_and_old_reader_still_works(legacy_db, tmp_path, monkeypatch):
    source_hash = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    destination = tmp_path / "expanded.db"
    db = SqliteDatabase(DatabaseConfig(destination))
    try:
        report = await DataRecovery(db).migrated_copy(legacy_db, destination, request())
        assert report.migration_version == 5
        assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == source_hash
        with pytest.raises(ConflictError):
            await DataRecovery(db).migrated_copy(legacy_db, legacy_db, request())
        with pytest.raises(ConflictError):
            await DataRecovery(db).migrated_copy(legacy_db, destination, request())
    finally:
        await db.stop()
    monkeypatch.setattr(database_manager, "DB_PATH", destination)
    assert (await database_manager.get_user_data(10, 100))["total_vc_seconds"] == 119.5
    assert len((await database_manager.get_favorites())["10"]) == 27
    assert len(await database_manager.get_top_played_songs_db(100, 100)) == 60
    assert (await database_manager.get_watch_playlist("session-one"))[0]["order_index"] == 4
    assert not list(tmp_path.glob(".discordbot-candidate-*"))


@pytest.mark.asyncio
async def test_known_old_nullable_pairs_expand_without_changing_legacy_facts(tmp_path):
    source = tmp_path / "older.db"
    with closing(sqlite3.connect(source)) as conn:
        for ddl in LEGACY_DDL:
            ddl = ddl.replace(", birth_month INTEGER, birth_day INTEGER", "").replace(", channel_id INTEGER, message_id INTEGER", "")
            conn.execute(ddl)
        conn.execute("INSERT INTO users VALUES (10,100,8,1,61.25)")
        conn.execute("INSERT INTO watch_sessions VALUES ('older',100,10,'2020-01-01')")
        conn.commit()
        before = validate(conn)
        assert before.state is DatabaseState.VALID
    destination = tmp_path / "expanded.db"
    db = SqliteDatabase(DatabaseConfig(destination))
    try:
        report = await DataRecovery(db).migrated_copy(source, destination, request())
        assert report.schema_variant == "legacy-current"
        assert report.data_checksum == before.data_checksum
        await db.start()
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_migration_failure_leaves_source_and_destination_untouched(legacy_db, tmp_path, monkeypatch):
    from discordbot.storage.adapters import recovery
    source_hash = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    destination = tmp_path / "failed.db"
    db = SqliteDatabase(DatabaseConfig(destination))
    def fail(conn, checkpoint):
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE INDEX v2_partial ON users(guild_id)")
        raise DataIntegrityError("injected migration failure")
    monkeypatch.setattr(recovery, "apply_pending", fail)
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).migrated_copy(legacy_db, destination, request())
        assert not destination.exists()
        assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == source_hash
        assert not list(tmp_path.glob(".discordbot-candidate-*"))
    finally:
        await db.stop()
