from contextlib import closing
import hashlib
import sqlite3

import pytest
from cryptography.fernet import Fernet

import database_manager
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.migrations import MIGRATIONS, apply_pending
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.adapters.schema import create_legacy_schema
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


@pytest.mark.asyncio
async def test_phase3_copy_expands_without_touching_source_and_v1_reads_new_facts(tmp_path, monkeypatch):
    source = tmp_path / "phase3.db"
    with closing(sqlite3.connect(source, isolation_level=None)) as conn:
        create_legacy_schema(conn)
        conn.execute("INSERT INTO users VALUES (10,100,7,1,119.5,2,29)")
        apply_pending(conn, lambda: None, MIGRATIONS[:2])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    target = tmp_path / "phase4.db"
    try:
        report = await DataRecovery(worker).migrated_copy(source, target, DatabaseRequest.within(5))
        assert report.migration_version == 4
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        monkeypatch.setattr(database_manager, "DB_PATH", target)
        assert (await database_manager.get_user_data(10, 100))["total_vc_seconds"] == 119.5
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_full_backup_restores_dedupe_voice_and_daily_claim_metadata(service, database, tmp_path, clock):
    await service.message(100, 10, "sensitive-message-id", "각", clock.now())
    await service.voice(100, 10, "gateway", 1, 1001, False)
    await service.events.claim_birthday(100, clock.now().date(), service.request())
    key = Fernet.generate_key()
    backup = tmp_path / "synthetic.sql"
    expected = await DataRecovery(database).backup(backup, key, service.request())
    assert expected.metadata_checksum
    assert b"sensitive-message-id" not in backup.read_bytes()
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        restored = tmp_path / "restored.db"
        result = await DataRecovery(worker).restore_copy(RecoveryCandidate(backup, key), restored, service.request())
        assert result.metadata_checksum == expected.metadata_checksum
        expanded = await DataRecovery(worker).migrated_copy(restored, tmp_path / "again.db", service.request())
        assert expanded.metadata_checksum == expected.metadata_checksum
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_metadata_corruption_is_fail_closed(database, service):
    await database.write(service.request(), lambda conn: conn.execute("INSERT INTO v2_engagement_events VALUES (100,'bad',-1)"))
    assert (await database.inspect(service.request())).state is DatabaseState.INVALID_DATA
