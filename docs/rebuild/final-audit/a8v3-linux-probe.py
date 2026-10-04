"""Real Linux filesystem boundaries; run only in the disposable Linux snapshot."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

import pytest

from discordbot.operations.adapters.filesystem import ExclusiveLock, digest
from discordbot.platform.errors import ConflictError, DataIntegrityError
from tests.integration.operations.test_build import Runner, builder
from tests.integration.operations.test_filesystem import release


def test_real_lib64_materialization_includes_nested_control_names(builder):
    assert os.name == "posix"
    class AliasRunner(Runner):
        def run(self, args, cwd, timeout):
            super().run(args, cwd, timeout)
            if "check" in args:
                library = cwd / ".venv" / "lib"
                payload = library / "python3.12" / "site-packages" / "package"
                payload.mkdir(parents=True)
                for name in ("manifest.json", ".building", "candidate.json"):
                    (payload / name).write_text("synthetic nested payload")
                (cwd / ".venv" / "lib64").symlink_to("lib", target_is_directory=True)
    builder.runner = AliasRunner()
    identity = builder.build("a" * 40)
    builder.publish(identity)
    path = builder.store.path(identity)
    value = builder.store.validate(identity)
    assert not (path / ".venv" / "lib64").is_symlink()
    for layout in ("lib", "lib64"):
        for name in ("manifest.json", ".building", "candidate.json"):
            relative = f".venv/{layout}/python3.12/site-packages/package/{name}"
            assert value["files"][relative] == digest(path / relative)
            assert stat.S_IMODE((path / relative).stat().st_mode) == 0o440
    assert stat.S_IMODE(path.stat().st_mode) == 0o550
    builder.store.activate(identity)
    assert (builder.store.root / "current").is_symlink()
    assert builder.store.current() == identity


@pytest.mark.parametrize("link_kind", ["file", "directory"])
def test_nested_manifest_link_rejected_before_pointer_switch(tmp_path, link_kind):
    assert os.name == "posix"
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    outside = tmp_path / "outside"
    if link_kind == "directory":
        outside.mkdir()
        (outside / "payload").write_text("protected synthetic content")
    else:
        outside.write_text("protected synthetic content")
    (store.path("new") / "app" / "manifest.json").symlink_to(outside, target_is_directory=link_kind == "directory")
    with pytest.raises(DataIntegrityError, match="link"):
        store.activate("new")
    assert store.current() == "old"
    assert outside.exists() and not list(tmp_path.glob(".current-*"))


def test_real_flock_is_released_after_abrupt_owner_exit(tmp_path):
    assert os.name == "posix"
    lock = tmp_path / "operations.lock"
    ready = tmp_path / "ready"
    child_code = (
        "import sys,time;from pathlib import Path;"
        "from discordbot.operations.adapters.filesystem import ExclusiveLock;"
        "\nwith ExclusiveLock(Path(sys.argv[1])).acquire():"
        "\n Path(sys.argv[2]).write_text('ready')\n time.sleep(30)"
    )
    child = subprocess.Popen([sys.executable, "-B", "-c", child_code, str(lock), str(ready)],
                             env=dict(os.environ, PYTHONPATH=str(Path.cwd() / "src")),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        inode = lock.stat().st_ino
        with pytest.raises(ConflictError):
            with ExclusiveLock(lock).acquire():
                pytest.fail("stole live kernel ownership")
        child.kill()
        child.wait(timeout=5)
        with ExclusiveLock(lock).acquire():
            assert lock.stat().st_ino == inode
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
