from pathlib import Path
from typing import Dict

import pytest

import database_manager


@pytest.fixture(scope="session", autouse=True)
def isolated_database(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, Path]:
    """Route every test away from the repository's operational database."""
    test_data_dir = tmp_path_factory.mktemp("discordbot-test-data")
    test_db_path = test_data_dir / "bot_database.db"
    test_backup_path = test_data_dir / "database_backup.sql"

    # init_db() fetches the remote backup when both files are absent.  A valid,
    # empty local dump keeps tests offline while still exercising schema setup.
    test_backup_path.write_text(
        "BEGIN TRANSACTION;\nCOMMIT;\n",
        encoding="utf-8",
    )

    production_data_dir = (database_manager.BASE_DIR / "data").resolve()
    assert test_data_dir.resolve() != production_data_dir

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(database_manager, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(database_manager, "DB_PATH", test_db_path)
    monkeypatch.setattr(database_manager, "SQL_BACKUP_PATH", test_backup_path)

    try:
        yield {
            "data_dir": test_data_dir,
            "db_path": test_db_path,
            "backup_path": test_backup_path,
        }
    finally:
        monkeypatch.undo()
