"""Actual shipped JS with asynchronous fake iframes and independent peer VMs."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('scenario', [
    'playing-refresh', 'paused-refresh', 'hydrate-before-ready', 'ready-before-hydrate',
    'same-invite-return', 'latest-before-ready', 'late-iframe-ack',
    'peer-cannot-overwrite-authority', 'multi-client-timing', 'autoplay-recovery',
    'unacknowledged-playback', 'reconnect-hydration',
    'video-change-before-ack', 'seek-ack-is-asynchronous', 'reconnect-paused', 'paused-cue-reports-zero',
    'terminal-4001', 'terminal-4002', 'terminal-4003', 'stale-revision', 'empty-session',
])
def test_shipped_watch_playback_reconciliation(scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js browser harness runs on the development host; no runtime dependency')
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([node, str(Path(__file__).with_name('playback_browser_harness.cjs')),
        str(root/'src/discordbot/watch/adapters/templates/player.html'), scenario],
        capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stderr
