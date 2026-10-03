"""Actual local child exits between snapshot fsync and replace; synthetic files only."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from discordbot.music.adapters.snapshots import SnapshotStore
from discordbot.platform.executors import BoundedExecutor
from tests.integration.music.conftest import rig, song  # noqa: F401


@pytest.mark.asyncio
async def test_abrupt_writer_exit_preserves_last_good_snapshot_and_restore(rig, tmp_path):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="a7v2-crash")
    path = tmp_path / "synthetic.json"
    store = SnapshotStore(path, executor)
    actor = rig[0]()
    await actor.ask("enqueue", tracks=(song(), song(2)))
    try:
        await store.save(actor.projection())
        old = path.read_bytes()
        root = Path(__file__).resolve().parents[3]
        script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / 'src'))
import conftest
from discordbot.music.adapters.snapshots import SnapshotStore
path = Path(sys.argv[2])
def crash(source, destination):
    assert Path(source).parent == path.parent
    assert Path(destination) == path
    os._exit(73)
os.replace = crash
SnapshotStore(path, None)._write({'100': {'synthetic_partial_replacement': True}})
"""
        child = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(root), str(path)],
            cwd=tmp_path, capture_output=True, timeout=10,
            env=dict(os.environ, PYTHON_DOTENV_DISABLED="1"),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert child.returncode == 73, child.stderr.decode("utf-8", errors="replace")
        assert path.read_bytes() == old
        # Abrupt exit leaves the uncommitted temp; it must never be read as state.
        assert len(list(tmp_path.glob("*.tmp"))) == 1
        records, failed = await store.records()
        assert not failed and len(records) == 1
        restored = rig[0](200)
        record = records[0]
        await restored.ask("restore", identity=record.identity, data=record.data,
                           session_id=record.session_id, paused=record.paused)
        assert restored.projection().legacy() == actor.projection().legacy()
        assert path.read_bytes() == old
    finally:
        await executor.close(grace_seconds=2)
