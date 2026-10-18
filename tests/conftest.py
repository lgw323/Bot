from collections.abc import Iterator
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_available_legacy_database(request: pytest.FixtureRequest) -> None:
    """Isolate the optional comparison reference without requiring it in V2 exports."""
    if find_spec("compatibility") is not None:
        request.getfixturevalue("isolated_v1_reference")


@pytest.fixture(scope="session")
def isolated_v1_reference(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path]]:
    """Keep the frozen comparison oracle separate from both V1 and production."""
    from compatibility.v1 import database_manager

    yield from _isolate_database(database_manager, tmp_path_factory, "discordbot-v1-reference")


def _isolate_database(
    database_manager: ModuleType, tmp_path_factory: pytest.TempPathFactory, prefix: str,
) -> Iterator[dict[str, Path]]:
    test_data_dir = tmp_path_factory.mktemp(prefix)
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
