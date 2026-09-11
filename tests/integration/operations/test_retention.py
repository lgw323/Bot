import os
import time

from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.operations.adapters.retention import cleanup_releases
from .test_filesystem import release, symlinks_on_windows


def test_cleanup_preserves_current_rollback_window_and_counts_venv(tmp_path):
    now = time.time()
    store = release(tmp_path, "old-but-protected")
    for index in range(6):
        release(tmp_path, "r" + str(index))
        os.utime(store.path("r" + str(index)), (now - 10 * 86400 - index, now - 10 * 86400 - index))
    release(tmp_path, "current")
    release(tmp_path, "recent")
    store.activate("current")
    state = tmp_path / "state"
    state.mkdir()
    atomic_json(state / "rollback.json", {"previous": "old-but-protected"})
    size = cleanup_releases(store, state, now=now)
    assert size > 0
    for identity in ("current", "recent", "old-but-protected"):
        assert store.path(identity).exists()
    assert not store.path("r5").exists()


def test_reboot_incomplete_release_is_never_current_and_can_be_cleaned(tmp_path):
    store = release(tmp_path, "current")
    store.activate("current")
    incomplete = store.path("incomplete")
    incomplete.mkdir()
    (incomplete / ".building").write_text("interrupted")
    now = time.time()
    os.utime(incomplete, (now - 2 * 86400, now - 2 * 86400))
    assert store.current() == "current"
    assert cleanup_releases(store, tmp_path, now=now) > 0
    assert not incomplete.exists()
