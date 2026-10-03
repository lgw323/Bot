"""Run the unchanged A7 probe with the original actor loaded only in this process.

Usage: .venv/Scripts/python.exe docs/rebuild/final-audit/a7v1-baseline-probe.py
No checkout mutation; all non-actor runtime sources are identical at these targets.
"""
from pathlib import Path
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import conftest  # noqa: E402,F401 -- install the repository credential guard first
import discordbot.music.application.actor as actor_module  # noqa: E402
import pytest  # noqa: E402

BASELINE = "3092f49ce82ac44232535b39b779718a5bd0f414"
source = subprocess.check_output(
    ["git", "show", BASELINE + ":src/discordbot/music/application/actor.py"], cwd=ROOT
)
print("Original actor SHA-256:", hashlib.sha256(source).hexdigest())
exec(compile(source, str(actor_module.__file__), "exec"), actor_module.__dict__)
raise SystemExit(pytest.main([
    "-c", str(ROOT / "pyproject.toml"),
    str(ROOT / "docs/rebuild/final-audit/a7-paused-disconnect-probe.py"),
    "-q", "--tb=short", "-W", "error::RuntimeWarning",
    "-W", "error::pytest.PytestUnraisableExceptionWarning",
    "--junitxml=" + str(ROOT / "docs/rebuild/final-audit/a7v1-baseline-results.xml"),
]))
