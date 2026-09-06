import sqlite3

import pytest

import database_manager
from discordbot.platform.errors import DataIntegrityError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseConfig


@pytest.mark.asyncio
async def test_f001_fr001_fr046_correct_existing_zero_byte_db_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature F001; FR-001/FR-046; CORRECT; temp data only."""
    db_path = tmp_path / "zero-byte.db"
    backup_path = tmp_path / "missing-backup.sql"
    db_path.touch()
    # Phase 3 transfers this owned CORRECT spec to the implemented V2 startup gate.
    # V1 runtime remains untouched; simply unmarking its old call would still fail.
    database = SqliteDatabase(DatabaseConfig(db_path))
    with pytest.raises(DataIntegrityError) as failure:
        await database.start()
    assert failure.value.context["state"] == "zero_byte"
    assert db_path.read_bytes() == b""
    assert not backup_path.exists()
    assert database.admitted == (0, 0)


def test_f001_fr001_fr046_correct_corrupt_db_fails_without_overwrite(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature F001; FR-001/FR-046; CORRECT; temp data only."""
    db_path = tmp_path / "corrupt.db"
    backup_path = tmp_path / "missing-backup.sql"
    corrupt_bytes = b"this is not a sqlite database\x00\xff"
    db_path.write_bytes(corrupt_bytes)
    monkeypatch.setattr(database_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database_manager, "DB_PATH", db_path)
    monkeypatch.setattr(database_manager, "SQL_BACKUP_PATH", backup_path)

    with pytest.raises(sqlite3.DatabaseError):
        database_manager.init_db()

    assert db_path.read_bytes() == corrupt_bytes
    assert not backup_path.exists()
