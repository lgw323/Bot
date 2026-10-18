from pathlib import Path
from typing import Dict

from compatibility.v1 import database_manager


def test_database_paths_are_isolated(
    isolated_v1_reference: Dict[str, Path],
) -> None:
    """The shared test fixture must never point at repository data files."""
    production_data_dir = (database_manager.BASE_DIR / "data").resolve()

    assert database_manager.DATA_DIR == isolated_v1_reference["data_dir"]
    assert database_manager.DB_PATH == isolated_v1_reference["db_path"]
    assert database_manager.SQL_BACKUP_PATH == isolated_v1_reference["backup_path"]
    assert production_data_dir not in database_manager.DB_PATH.resolve().parents
    assert production_data_dir not in database_manager.SQL_BACKUP_PATH.resolve().parents


def test_runtime_state_files_are_ignored_by_git() -> None:
    """재시작·업데이트용 임시 파일은 커밋 후보가 되면 안 됩니다."""
    project_root = Path(__file__).resolve().parents[1]
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

    assert "data/music_state.json" in gitignore
    assert "data/update_pending" in gitignore
    assert "data/.requirements.*" in gitignore
