"""Unchanged M2 probe with only its pre-remediation recovery adapter in memory."""
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import conftest  # Credential guard before application imports.
import pytest

BASELINE = "01d848555cfbf35115523752982a7ddb711ce09f"
PATH = "src/discordbot/operations/adapters/recovery.py"
source = subprocess.check_output(["git", "show", f"{BASELINE}:{PATH}"], cwd=ROOT)
module = importlib.import_module("discordbot.operations.adapters.recovery")
exec(compile(source, f"{BASELINE}:{PATH}", "exec"), module.__dict__)
raise SystemExit(pytest.main(sys.argv[1:]))
