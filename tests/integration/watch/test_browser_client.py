"""Executable shipped-client behavior; no browser network or production data."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('scenario', [
    'iframe-independent-presence', 'empty-player-protocol', 'hydrate-before-player',
    'recoverable-return', 'terminal-stays-closed', 'page-lifecycle',
    'bounded-reconnect', 'return-open-probe', 'select-before-player',
])
def test_shipped_watch_browser_client(scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js browser harness runs on the development host; no runtime dependency')
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([node, str(Path(__file__).with_name('browser_client_harness.cjs')),
        str(root/'src/discordbot/watch/adapters/templates/player.html'), scenario],
        capture_output=True, text=True, timeout=10, encoding='utf-8')
    assert result.returncode == 0, result.stderr
