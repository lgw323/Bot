import os
from pathlib import Path

import pytest

from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore, atomic_json, digest
from discordbot.platform.errors import ConflictError, DataIntegrityError


@pytest.fixture(autouse=True)
def symlinks_on_windows(tmp_path, monkeypatch):
    """Windows lacks symlink privilege here. Model links, retaining real os.replace.

    Linux staging runs the same cases against actual symlinks without this shim.
    This fixture is intentionally test-only, never a production fallback.
    """
    if os.name != "nt":
        return
    original_link, original_resolve = Path.is_symlink, Path.resolve
    def link(path):
        return original_link(path) or (path.is_file() and path.name.startswith(("current", ".current-", "escape"))
                                      and path.read_bytes().startswith(b"TEST_LINK:"))
    def resolve(path, strict=False):
        if link(path):
            return Path(path.read_text()[10:]).resolve(strict=strict)
        return original_resolve(path, strict=strict)
    def create(path, target, target_is_directory=False):
        assert path.is_relative_to(tmp_path)
        path.write_text("TEST_LINK:" + str(target))
    monkeypatch.setattr(Path, "is_symlink", link)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(Path, "symlink_to", create)


def release(root: Path, identity: str) -> ReleaseStore:
    store = ReleaseStore(root)
    path = store.path(identity)
    (path / ".venv").mkdir(parents=True)
    (path / ".venv" / "pyvenv.cfg").write_text("synthetic venv")
    (path / "app").mkdir()
    (path / "app" / "code.py").write_text(identity)
    files = {p.relative_to(path).as_posix(): digest(p) for p in path.rglob("*") if p.is_file()}
    atomic_json(path / "manifest.json", dict(release=identity, commit="a" * 40, python="3.12.14",
        dependency_hash="b" * 64, schema_min=5, schema_max=5, built_at="2026-09-11T00:00:00+00:00",
        app_version="2", entrypoints=["discord-bot", "watch-web", "operations"], config_version=1, files=files))
    return store


def test_kernel_lock_excludes_manual_timer_backup_and_releases_on_error(tmp_path):
    path = tmp_path / "operation.lock"
    with pytest.raises(RuntimeError):
        with ExclusiveLock(path).acquire():
            with pytest.raises(ConflictError):
                with ExclusiveLock(path).acquire():
                    pytest.fail("overlap")
            raise RuntimeError("injected")
    with ExclusiveLock(path).acquire():
        assert path.exists()


def test_stale_pid_metadata_does_not_block_or_steal_kernel_lock(tmp_path):
    path = tmp_path / "operation.lock"
    path.write_text(' {"pid":1,"owner":"stale"}')
    with ExclusiveLock(path).acquire():
        with pytest.raises(ConflictError):
            with ExclusiveLock(path).acquire():
                pytest.fail("stolen")


def test_first_open_does_not_write_until_kernel_ownership(tmp_path, monkeypatch):
    owned = False
    if os.name == "nt":
        import msvcrt as locking
        attribute, unlock = "locking", locking.LK_UNLCK
    else:
        import fcntl as locking
        attribute, unlock = "flock", locking.LOCK_UN
    original_lock = getattr(locking, attribute)
    original_open = os.fdopen
    def kernel_lock(fd, operation, *args):
        nonlocal owned
        result = original_lock(fd, operation, *args)
        owned = operation != unlock
        return result
    class GuardedStream:
        def __init__(self, stream): self.stream = stream
        def __getattr__(self, name): return getattr(self.stream, name)
        def write(self, value):
            assert owned, "lock initialization must not write before kernel ownership"
            return self.stream.write(value)
    monkeypatch.setattr(locking, attribute, kernel_lock)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: GuardedStream(original_open(*args, **kwargs)))
    with ExclusiveLock(tmp_path / "new.lock").acquire():
        assert owned
    assert not owned


def test_atomic_pointer_and_protected_cleanup(tmp_path):
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    store.activate("new")
    assert store.current() == "new"
    with pytest.raises(ConflictError):
        store.remove("new", set())
    with pytest.raises(ConflictError):
        store.remove("old", {"old"})
    assert store.remove("old", set()) > 0


def test_symlink_switch_failure_keeps_old_pair(tmp_path, monkeypatch):
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    def fail(*args): raise OSError("injected")
    monkeypatch.setattr("discordbot.operations.adapters.filesystem.os.replace", fail)
    with pytest.raises(OSError): store.activate("new")
    assert store.current() == "old"
    assert not list(tmp_path.glob(".current-*"))


def test_incomplete_or_mutated_release_cannot_activate(tmp_path):
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    (store.path("new") / ".building").touch()
    with pytest.raises(DataIntegrityError): store.activate("new")
    (store.path("new") / ".building").unlink()
    (store.path("new") / "app" / "code.py").write_text("tampered")
    with pytest.raises(DataIntegrityError): store.activate("new")
    assert store.current() == "old"


@pytest.mark.parametrize("identity", ["../outside", "..", "/absolute", "a/b", "a\\b"])
def test_release_path_traversal_rejected(tmp_path, identity):
    with pytest.raises(DataIntegrityError): ReleaseStore(tmp_path).path(identity)


def test_cleanup_rejects_nested_link_escape(tmp_path):
    store = release(tmp_path, "old")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("protected")
    (store.path("old") / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(DataIntegrityError): store.remove("old", set())
    assert (outside / "keep").read_text() == "protected"
