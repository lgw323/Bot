"""Provenance and isolation of the actual V1 DB compatibility oracle."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from compatibility.v1 import database_manager as reference


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_reference_provenance_and_isolation(isolated_v1_reference):
    manifest = json.loads((ROOT / "compatibility/v1/manifest.json").read_text())
    source = ROOT / "compatibility/v1/database_manager.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["reference_sha256"]
    assert manifest["source_commit"] == "6ce25d2dfd894ae340b64ebd59823d87463bbed8"
    assert manifest["source_path"] == "database_manager.py"
    assert Path(reference.__file__).resolve() == source.resolve()
    assert reference is not sys.modules.get("database_manager")
    assert reference.DB_PATH == isolated_v1_reference["db_path"]
    assert reference.SQL_BACKUP_PATH == isolated_v1_reference["backup_path"]
    assert reference.DATA_DIR.resolve().is_relative_to(isolated_v1_reference["data_dir"].resolve())
    assert reference.DATA_DIR.resolve() != (ROOT / "data").resolve()


def test_changed_reference_is_rejected_before_execution(tmp_path):
    for relative in ("compatibility/__init__.py", "compatibility/v1/__init__.py"):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    # The replacement is synthetic; the original reference is never modified.
    (tmp_path / "compatibility/v1/database_manager.py").write_text(
        "from pathlib import Path\nPath('executed').write_text('unexpected')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         "import sys; sys.path.insert(0, '.'); from compatibility.v1 import database_manager"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Frozen V1 database reference changed" in result.stderr
    assert not (tmp_path / "executed").exists()
