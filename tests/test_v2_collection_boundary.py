"""V2-only source exports must collect without importing a V1 runtime."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("legacy_kind", ["none", "reference"])
@pytest.mark.parametrize("collect_only", [True, False], ids=["collection", "execution"])
def test_v2_collection_and_optional_legacy_isolation(
    tmp_path: Path, legacy_kind: str, collect_only: bool,
) -> None:
    # Copy only these source files into a new project, never config or user data.
    sources = [
        "conftest.py", "tests/conftest.py", "src/discordbot/__init__.py",
        "src/discordbot/platform/__init__.py", "src/discordbot/platform/clock.py",
    ]
    if legacy_kind == "reference":
        sources.extend([
            "compatibility/__init__.py", "compatibility/v1/__init__.py",
            "compatibility/v1/database_manager.py", "compatibility/v1/manifest.json",
        ])
    for relative in sources:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = src .\n", encoding="utf-8")
    probe = '''
from pathlib import Path
import sys
from discordbot.platform.clock import SystemClock

# Even a present V1 reference must not be imported merely to collect V2 tests.
assert "database_manager" not in sys.modules
assert "compatibility.v1.database_manager" not in sys.modules

def test_v2_probe():
    assert SystemClock().now().tzinfo is not None
    root = Path(__file__).resolve().parents[1]
    assert "database_manager" not in sys.modules
    if (root / "compatibility").exists():
        from compatibility.v1 import database_manager as reference
        assert reference.DATA_DIR != root / "compatibility/v1/data"
        assert reference.DB_PATH.parent == reference.DATA_DIR
        assert reference.SQL_BACKUP_PATH.parent == reference.DATA_DIR
        assert reference.SQL_BACKUP_PATH.read_text() == "BEGIN TRANSACTION;\\nCOMMIT;\\n"
        assert not reference.DB_PATH.exists()
        assert not (root / "compatibility/v1/data").exists()
    assert not (root / "data").exists()
'''
    (tmp_path / "tests/test_v2_probe.py").write_text(probe, encoding="utf-8")
    args = [
        sys.executable, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--basetemp", str(tmp_path / "pytest-work"),
    ]
    if collect_only:
        args.append("--collect-only")
    environment = dict(os.environ)
    environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        args, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "data").exists()
