"""Run code-only snapshot with existing WSL Python; no installation/systemd changes."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

source, destination = map(Path, sys.argv[1:3])
base = Path("/home/dlrjsdn/discordbot-a2-linux-verify")
assert base.is_dir() and os.name == "posix"
tests = [
    "docs/rebuild/final-audit/a8v2-release-probe.py",
    "docs/rebuild/final-audit/a8v3-contract-probe.py",
    "docs/rebuild/final-audit/a8v3-linux-probe.py",
    "tests/integration/operations/test_release_inventory_contract.py",
    "tests/integration/operations/test_filesystem.py",
    "tests/integration/operations/test_build.py",
]
with tempfile.TemporaryDirectory(prefix="a8v3-", dir=base) as temporary:
    root = Path(temporary)
    try:
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                target = root / item.filename
                assert target.resolve().is_relative_to(root)
                assert target.suffix not in {".db", ".sql", ".log", ".pyc"}
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
        code = "import conftest,pytest,sys;raise SystemExit(pytest.main(sys.argv[1:]))"
        environment = dict(os.environ, PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")
        environment.pop("PYTHONPATH", None)
        command = [str(base / ".venv/bin/python"), "-B", "-c", code, *tests,
                   "--confcutdir=tests/integration/operations", "--basetemp=" + str(root / "pytest-temp"),
                   "-q", "-x", "-W", "error::RuntimeWarning", "-W", "error::pytest.PytestUnraisableExceptionWarning",
                   "-p", "no:cacheprovider", "--tb=short", "-o", "junit_family=xunit1",
                   "--junitxml=" + str(root / "results.xml")]
        result = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=180)
        print(result.stdout.decode())
        print(result.stderr.decode())
        shutil.copyfile(root / "results.xml", destination / "a8v3-linux-results.xml")
        receipt = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                   "python": str(base / ".venv/bin/python"), "platform": sys.platform,
                   "returncode": result.returncode, "tests": tests,
                   "systemd_executed": False, "package_installation": False}
    finally:
        # Only this newly created, checked audit root; immutable synthetic releases
        # need owner write restored before TemporaryDirectory can remove them.
        assert root.parent == base and root.name.startswith("a8v3-")
        for directory, directories, files in os.walk(root, followlinks=False):
            path = Path(directory)
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
            for name in files:
                node = path / name
                if not node.is_symlink():
                    node.chmod(node.stat().st_mode | stat.S_IWUSR)
receipt["temporary_workspace_removed"] = not root.exists()
(destination / "a8v3-linux-evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
raise SystemExit(result.returncode)
