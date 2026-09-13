"""Private local artifacts and atomic pointers. No I/O occurs during import."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from discordbot.platform.errors import ConflictError, DataIntegrityError


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", value):
        raise DataIntegrityError("invalid artifact identity")
    return value


def contained(root: Path, path: Path) -> Path:
    root = root.absolute()
    path = path.absolute()
    if root == path or not path.is_relative_to(root):
        raise DataIntegrityError("artifact path escaped root")
    for node in (root, *root.parents, path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise DataIntegrityError("artifact path contains a link")
    if not path.resolve().is_relative_to(root.resolve()):
        raise DataIntegrityError("artifact path escaped root")
    return path


def sync_dir(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_bytes(path: Path, value: bytes) -> None:
    contained(path.parent, path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())


def read_json(path: Path, maximum: int = 1024 * 1024) -> dict:
    contained(path.parent, path)
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise DataIntegrityError("metadata size exceeded")
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise DataIntegrityError("invalid artifact metadata") from None


def digest(path: Path, maximum: int = 512 * 1024 * 1024) -> str:
    contained(path.parent, path)
    result = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            count += len(block)
            if count > maximum:
                raise DataIntegrityError("artifact size exceeded")
            result.update(block)
    return result.hexdigest()


class ExclusiveLock:
    """Kernel-owned flock/byte lock. Never unlink: stale metadata cannot steal ownership.

    Kernel releases ownership on crash/reboot; PID is diagnostic only. The same
    file coordinates backup, deployment, restore promotion and timer/manual work.
    """
    def __init__(self, path: Path, timeout: float = 0.0) -> None:
        if not 0 <= timeout <= 60:
            raise ValueError("invalid lock deadline")
        self.path, self.timeout = path, timeout

    @contextmanager
    def acquire(self) -> Iterator[None]:
        contained(self.path.parent, self.path)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        stream = os.fdopen(fd, "r+b", buffering=0)
        acquired = False
        end = time.monotonic() + self.timeout
        try:
            # Both flock and Windows byte locks cover an empty file. Never
            # initialize before ownership: two first-open contenders can race
            # a write against the winner's mandatory Windows byte lock.
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= end:
                        raise ConflictError("another operation owns the lock") from None
                    time.sleep(min(0.05, max(0, end - time.monotonic())))
            stream.seek(0)
            stream.write(b" ")
            stream.write(json.dumps({"owner": uuid.uuid4().hex, "pid": os.getpid()}).encode())
            stream.truncate()
            os.fsync(fd)
            yield
        finally:
            if acquired:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            stream.close()


class ReleaseStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        self.releases = self.root / "releases"

    def path(self, identity: str) -> Path:
        return contained(self.root, self.releases / identifier(identity))

    def current(self) -> str | None:
        pointer = self.root / "current"
        if not pointer.is_symlink():
            if pointer.exists():
                raise DataIntegrityError("current must be a release symlink")
            return None
        target = pointer.resolve(strict=True)
        if target.parent != self.releases.resolve() or target != self.path(target.name):
            raise DataIntegrityError("current release escaped layout")
        self.validate(target.name)
        return target.name

    def validate(self, identity: str) -> dict:
        path = self.path(identity)
        value = read_json(path / "manifest.json", 4 * 1024 * 1024)
        required = {"release", "commit", "python", "dependency_hash", "schema_min", "schema_max",
                    "built_at", "app_version", "entrypoints", "config_version", "files"}
        if set(value) != required or value["release"] != identity or value["config_version"] != 1:
            raise DataIntegrityError("release manifest mismatch")
        if any(not isinstance(value[key], str) for key in ("commit", "python", "dependency_hash", "built_at", "app_version")):
            raise DataIntegrityError("release manifest field type invalid")
        if not re.fullmatch(r"[0-9a-f]{40}", value["commit"]) or not value["python"].startswith("3.12."):
            raise DataIntegrityError("unsupported release identity")
        if value["entrypoints"] != ["discord-bot", "watch-web", "operations"]:
            raise DataIntegrityError("release entrypoints mismatch")
        if (any(type(value[key]) is not int for key in ("schema_min", "schema_max"))
                or not 0 <= value["schema_min"] <= value["schema_max"] <= 5
                or not re.fullmatch(r"[0-9a-f]{64}", value["dependency_hash"])):
            raise DataIntegrityError("release compatibility metadata invalid")
        if not isinstance(value["files"], dict) or len(value["files"]) > 50000:
            raise DataIntegrityError("release inventory invalid")
        for relative, checksum in value["files"].items():
            if not isinstance(relative, str) or not isinstance(checksum, str):
                raise DataIntegrityError("release inventory field type invalid")
            file = contained(path, path / relative)
            if digest(file) != checksum:
                raise DataIntegrityError("release content checksum mismatch")
        inventory = set()
        for node in path.rglob("*"):
            contained(path, node)
            if node.is_file() and node.name != "manifest.json":
                inventory.add(node.relative_to(path).as_posix())
        if inventory != set(value["files"]):
            raise DataIntegrityError("release contains unmanifested files")
        if (path / ".building").exists() or not (path / ".venv" / "pyvenv.cfg").is_file():
            raise DataIntegrityError("incomplete release")
        return value

    def activate(self, identity: str) -> None:
        self.validate(identity)
        target = self.path(identity)
        pointer = self.root / "current"
        if pointer.exists() and not pointer.is_symlink():
            raise DataIntegrityError("activation refuses non-symlink current")
        temporary = self.root / (".current-" + uuid.uuid4().hex)
        try:
            temporary.symlink_to(target, target_is_directory=True)
            os.replace(temporary, pointer)
            sync_dir(self.root)
        finally:
            temporary.unlink(missing_ok=True)

    def remove(self, identity: str, protected: set[str]) -> int:
        current = self.current()
        if identity in protected or identity == current:
            raise ConflictError("refusing to delete protected release")
        path = self.path(identity)
        size = 0
        for node in path.rglob("*"):
            contained(path, node)
            if node.is_file():
                size += node.stat().st_size
        # File modes can be immutable to service users while the deploy owner
        # retains directory ownership. Restore owner write only for safe cleanup.
        for node in path.rglob("*"):
            node.chmod(stat.S_IMODE(node.stat().st_mode) | stat.S_IWUSR)
        path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
        shutil.rmtree(path)
        return size
