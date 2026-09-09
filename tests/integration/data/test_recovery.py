from contextlib import closing
import sqlite3

import pytest
from cryptography.fernet import Fernet

import database_manager
from discordbot.platform.errors import ConflictError, DataIntegrityError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


def request():
    return DatabaseRequest.within(5, "synthetic-recovery")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,state", [
    ("missing", DatabaseState.MISSING), ("empty", DatabaseState.EMPTY),
    ("corrupt", DatabaseState.CORRUPT), ("partial", DatabaseState.WRONG_SCHEMA),
])
async def test_startup_never_promotes_invalid_database(tmp_path, kind, state):
    path = tmp_path / "bad.db"
    if kind == "empty":
        path.touch()
    elif kind == "corrupt":
        path.write_bytes(b"not SQLite\0\xff")
    elif kind == "partial":
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE users(user_id INTEGER)")
    before = path.read_bytes() if path.exists() else None
    db = SqliteDatabase(DatabaseConfig(path))
    assert (await db.inspect(request())).state is state
    with pytest.raises(DataIntegrityError) as failure:
        await db.start()
    assert failure.value.context["state"] == state.value
    assert (path.read_bytes() if path.exists() else None) == before
    assert db.admitted == (0, 0)


@pytest.mark.asyncio
async def test_explicit_bootstrap_only_creates_absent_target(tmp_path):
    path = tmp_path / "new.db"
    db = SqliteDatabase(DatabaseConfig(path))
    try:
        report = await DataRecovery(db).bootstrap(request())
        assert report.state is DatabaseState.VALID and report.migration_version == 4
        assert all(count == 0 for _, count in report.counts)
        before = path.read_bytes()
        with pytest.raises(ConflictError):
            await DataRecovery(db).bootstrap(request())
        assert path.read_bytes() == before
        await db.start()
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_backup_v2_roundtrip_and_actual_v1_reader(database, tmp_path, monkeypatch):
    key = Fernet.generate_key()
    path = tmp_path / "backup.sql"
    source_report = await DataRecovery(database).backup(path, key, request())
    assert path.read_bytes().startswith(BACKUP_HEADER)
    assert b"CREATE TABLE" not in path.read_bytes()
    assert b"example.invalid" not in path.read_bytes()
    restored = tmp_path / "restored.db"
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        report = await DataRecovery(worker).restore_copy(RecoveryCandidate(path, key), restored, request())
        assert (report.counts, report.data_checksum) == (source_report.counts, source_report.data_checksum)
        last_good = restored.read_bytes()
        with pytest.raises(ConflictError):
            await DataRecovery(worker).restore_copy(RecoveryCandidate(path, key), restored, request())
        assert restored.read_bytes() == last_good
        with pytest.raises(DataIntegrityError):
            await DataRecovery(worker).restore_copy(RecoveryCandidate(path, Fernet.generate_key()), tmp_path / "wrong.db", request())
        assert not (tmp_path / "wrong.db").exists()
    finally:
        await worker.stop()
    # Exercise the unchanged V1 envelope reader on V2 output, not a duplicate decoder.
    old_restore = tmp_path / "v1-restore.db"
    monkeypatch.setattr(database_manager, "DB_PATH", old_restore)
    monkeypatch.setattr(database_manager, "SQL_BACKUP_PATH", path)
    monkeypatch.setattr(database_manager, "_cipher_suite", Fernet(key))
    database_manager._restore_database_from_sql()
    assert len((await database_manager.get_favorites())["10"]) == 27
    assert not list(tmp_path.glob(".discordbot-candidate-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("encrypted_fields", [False, True])
async def test_legacy_full_schema_dump_plaintext_and_field_encrypted(legacy_db, tmp_path, encrypted_fields):
    key = Fernet.generate_key()
    cipher = Fernet(key)
    with closing(sqlite3.connect(legacy_db)) as conn:
        if encrypted_fields:
            for table in ("favorites", "music_play_counts"):
                for rowid, url, title in conn.execute(f"SELECT rowid,url,title FROM {table}").fetchall():
                    conn.execute(f"UPDATE {table} SET url=?,title=? WHERE rowid=?", (cipher.encrypt(url.encode()).decode(), cipher.encrypt(title.encode()).decode(), rowid))
            conn.commit()
        sql = "\n".join(conn.iterdump())
    backup = tmp_path / "legacy.sql"
    backup.write_bytes(sql.encode("utf-8"))
    db = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        destination = tmp_path / "legacy-restored.db"
        report = await DataRecovery(db).restore_copy(RecoveryCandidate(backup, key), destination, request())
        assert report.state is DatabaseState.VALID
        with closing(sqlite3.connect(destination)) as conn:
            row = conn.execute("SELECT title FROM favorites WHERE url=?", ("https://example.invalid/track?raw=00",)).fetchone()
            assert row == ("친구's\n음악 0",)
    finally:
        await db.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", [
    "BEGIN TRANSACTION; COMMIT;", "CREATE TABLE favorites(user_id INTEGER,url TEXT,title TEXT);",
    "BEGIN TRANSACTION; ATTACH DATABASE ':memory:' AS other; COMMIT;",
    "BEGIN TRANSACTION; SELECT load_extension('bad'); COMMIT;",
    "BEGIN TRANSACTION; PRAGMA writable_schema=ON; COMMIT;",
    "BEGIN TRANSACTION; CREATE VIRTUAL TABLE users USING fts5(content); COMMIT;",
    "BEGIN TRANSACTION; CREATE TABLE users(user_id INTEGER);",
])
async def test_invalid_or_unsafe_restore_does_not_publish(tmp_path, sql):
    path = tmp_path / "bad.sql"
    path.write_text(sql, encoding="utf-8")
    destination = tmp_path / "untouched.db"
    db = SqliteDatabase(DatabaseConfig(destination))
    try:
        with pytest.raises(DataIntegrityError):
            await DataRecovery(db).restore_copy(RecoveryCandidate(path), destination, request())
        assert not destination.exists()
        assert path.read_text(encoding="utf-8") == sql
        assert not list(tmp_path.glob(".discordbot-candidate-*"))
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_invalid_local_then_good_downloaded_candidate(database, tmp_path):
    key = Fernet.generate_key()
    good = tmp_path / "good.sql"
    await DataRecovery(database).backup(good, key, request())
    bad = tmp_path / "bad.sql"
    bad.write_text("invalid local", encoding="utf-8")
    db = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        result = await DataRecovery(db).recover_first_valid((RecoveryCandidate(bad), RecoveryCandidate(good, key)), tmp_path / "recovered.db", request())
        assert result.selected_index == 1 and result.rejected_indices == (0,)
        assert bad.read_text() == "invalid local"
    finally:
        await db.stop()


@pytest.mark.asyncio
async def test_failed_backup_publish_keeps_last_good(database, tmp_path, monkeypatch):
    from discordbot.storage.adapters import recovery
    target = tmp_path / "backup.sql"
    target.write_bytes(b"last-good")
    def fail(*args):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(recovery.os, "replace", fail)
    from discordbot.platform.errors import DatabaseUnavailableError
    with pytest.raises(DatabaseUnavailableError):
        await DataRecovery(database).backup(target, Fernet.generate_key(), request())
    assert target.read_bytes() == b"last-good"
    assert not list(tmp_path.glob(".discordbot-candidate-*"))
