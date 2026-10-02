"""Terminal media ownership through the shipped client, with isolated fake media."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("scenario", [
    "active", "protocol", "revoked", "before-api", "before-ready", "pending-load",
    "session-event", "http-403", "http-404", "destroy-throws", "destroy-reentrant",
    "pending-add", "late-add-response", "retired-terminal",
])
def test_terminal_media_lifecycle(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js synthetic browser harness requires the development host")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([
        node, str(Path(__file__).with_name("terminal_browser_harness.cjs")),
        str(root / "src/discordbot/watch/adapters/templates/player.html"), scenario,
    ], capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
