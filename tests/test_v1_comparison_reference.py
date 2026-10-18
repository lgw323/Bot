"""Keep retired implementations identifiable without importing a V1 bot."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from compatibility.v1 import cogs


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "compatibility/v1"


def test_selected_oracles_preserve_original_logic() -> None:
    manifest = json.loads((REFERENCE / "oracles-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["oracles"]) == 9
    assert Path(cogs.__file__).resolve() == REFERENCE / "cogs/__init__.py"
    for entry in manifest["oracles"]:
        source = (REFERENCE / entry["reference_path"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == entry["reference_sha256"]
        assert entry["source_commit"] == "6ce25d2dfd894ae340b64ebd59823d87463bbed8"
        if entry["adaptation"] == "absolute database import namespace only":
            source = source.replace(b"from compatibility.v1.database_manager import", b"from database_manager import")
        else:
            assert entry["adaptation"] == "none"
        assert hashlib.sha256(source).hexdigest() == entry["source_sha256"]


def test_tampered_oracle_cannot_execute(tmp_path: Path) -> None:
    # Copy only the enumerated source/manifest types; never configuration or data.
    for source in (ROOT / "compatibility").rglob("*"):
        if source.is_file() and source.suffix in {".py", ".json"}:
            destination = tmp_path / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    target = tmp_path / "compatibility/v1/cogs/music/music_utils.py"
    target.write_text("from pathlib import Path\nPath('executed').touch()\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", "import sys; sys.path.insert(0, '.'); import compatibility.v1.cogs.music.music_utils"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Frozen V1 comparison reference changed" in result.stderr
    assert not (tmp_path / "executed").exists()
