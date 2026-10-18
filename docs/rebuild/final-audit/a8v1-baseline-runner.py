"""Run unchanged A8 probe with only the two pre-remediation adapters in memory."""
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import conftest  # Install credential boundary before application imports.
import pytest

BASELINE = "f34ef43e8edee503ead5aa5d2e9f8e297450adec"
for name in ("retention", "deployment"):
    path = f"src/discordbot/operations/adapters/{name}.py"
    source = subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)
    module = importlib.import_module(f"discordbot.operations.adapters.{name}")
    exec(compile(source, f"{BASELINE}:{path}", "exec"), module.__dict__)

raise SystemExit(pytest.main(sys.argv[1:]))
