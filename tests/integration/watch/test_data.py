from contextlib import closing
import hashlib
import sqlite3

import pytest
from cryptography.fernet import Fernet

import database_manager
from discordbot.platform.errors import DataIntegrityError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.migrations import MIGRATIONS, apply_pending, validate_ledger
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.adapters.schema import create_legacy_schema
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState
from discordbot.watch.adapters.sqlite_repository import SqliteWatchRepository


@pytest.mark.asyncio
async def test_additive_migration_checksum_and_legacy_watch_reader(tmp_path, monkeypatch):
    source, target = tmp_path / "synthetic-phase5.db", tmp_path / "synthetic-phase6.db"
    with closing(sqlite3.connect(source, isolation_level=None)) as conn:
        create_legacy_schema(conn)
        apply_pending(conn, lambda: None, MIGRATIONS[:3])
        conn.execute("INSERT INTO watch_sessions VALUES ('synthetic-legacy',100,42,'2027-01-01 00:00:00',1000,500)")
        conn.execute("INSERT INTO watch_playlists VALUES ('synthetic-legacy','https://youtu.be/aaaaaaaaaaa','title','A',1)")
        ledger = conn.execute("SELECT * FROM v2_migrations").fetchall()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        report = await DataRecovery(worker).migrated_copy(source, target, DatabaseRequest.within(5))
        assert report.migration_version == 4
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        with closing(sqlite3.connect(target)) as conn:
            assert conn.execute("SELECT * FROM v2_migrations WHERE version<=3").fetchall() == ledger
            conn.execute("UPDATE v2_migrations SET checksum='bad' WHERE version=4")
            with pytest.raises(DataIntegrityError):
                validate_ledger(conn)
            conn.rollback()
        monkeypatch.setattr(database_manager, "DB_PATH", target)
        assert (await database_manager.get_watch_session("synthetic-legacy"))["created_by"] == 42
        assert (await database_manager.get_watch_playlist("synthetic-legacy"))[0]["order_index"] == 1
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_live_data_old_reader_isolation_and_encrypted_backup(service, invite, database, tmp_path, monkeypatch):
    await service.add(invite.capability, "https://youtu.be/aaaaaaaaaaa", "A")
    actor = service.resolve(invite.capability)
    await actor.call("bind", 1000, 500, False)
    request = DatabaseRequest.within(5)
    repo = SqliteWatchRepository(database)
    assert (await repo.get_session(100, invite.session_id, request)).message_id == 500
    assert await repo.get_session(200, invite.session_id, request) is None
    assert not await repo.list_playlist(200, invite.session_id, request)
    key, backup = Fernet.generate_key(), tmp_path / "synthetic.sql"
    expected = await DataRecovery(database).backup(backup, key, request)
    assert invite.capability.encode() not in backup.read_bytes()
    stored = await database.read(request, lambda conn: conn.execute("SELECT session_id FROM v2_watch_intents").fetchone()[0])
    assert stored == invite.session_id and stored != invite.capability
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        result = await DataRecovery(worker).restore_copy(RecoveryCandidate(backup, key), tmp_path / "restored.db", DatabaseRequest.within(5))
        assert result.metadata_checksum == expected.metadata_checksum
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_watch_metadata_corruption_is_fail_closed(database):
    request = DatabaseRequest.within(5)
    await database.write(request, lambda conn: conn.execute("INSERT INTO v2_watch_intents VALUES ('bad',100,42,5,1,0,NULL,NULL,NULL,NULL,0)"))
    assert (await database.inspect(request)).state is DatabaseState.INVALID_DATA
