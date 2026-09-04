import sqlite3

import pytest

import database_manager


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 silently promotes an existing zero-byte DB",
)
def test_f001_fr001_fr046_correct_existing_zero_byte_db_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature F001; FR-001/FR-046; CORRECT; temp data only."""
    db_path = tmp_path / "zero-byte.db"
    backup_path = tmp_path / "missing-backup.sql"
    db_path.touch()
    monkeypatch.setattr(database_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database_manager, "DB_PATH", db_path)
    monkeypatch.setattr(database_manager, "SQL_BACKUP_PATH", backup_path)

    with pytest.raises((RuntimeError, sqlite3.DatabaseError)):
        database_manager.init_db()


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
