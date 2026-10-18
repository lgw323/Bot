"""Run unchanged M3 checks using exact pre-M3 filesystem/build modules in memory."""
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import conftest  # Install repository credential boundary before application imports.
import pytest

BASELINE = "5e846ae6a08e8fda210e6e4a06c457387012604f"
for name in ("filesystem", "build"):
    path = f"src/discordbot/operations/adapters/{name}.py"
    source = subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)
    module = importlib.import_module(f"discordbot.operations.adapters.{name}")
    exec(compile(source, f"{BASELINE}:{path}", "exec"), module.__dict__)
raise SystemExit(pytest.main(sys.argv[1:]))
