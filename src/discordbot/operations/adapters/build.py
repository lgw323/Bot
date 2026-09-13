"""Offline immutable builds. Command vectors never pass through a shell."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from discordbot.operations.adapters.filesystem import ReleaseStore, atomic_json, contained, digest, read_json
from discordbot.platform.errors import DataIntegrityError, ExternalTemporaryError


class Runner(Protocol):
    def run(self, args: list[str], cwd: Path, timeout: float) -> None: ...
    def read(self, args: list[str], cwd: Path, timeout: float) -> str: ...


class CommandRunner:
    def read(self, args: list[str], cwd: Path, timeout: float) -> str:
        # Only fixed small local Git/systemd queries use this API. Never keys,
        # raw logs, package output or remote/user content.
        if args[0] not in {"git", "systemctl"} or not 0 < timeout <= 30:
            raise ValueError("unsupported command query")
        try:
            result = subprocess.run(args, cwd=cwd, timeout=timeout, check=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"PATH": os.defpath, "GIT_TERMINAL_PROMPT": "0"})
            if len(result.stdout) > 4096:
                raise ValueError
            return result.stdout.decode().strip()
        except (OSError, ValueError, subprocess.SubprocessError):
            raise ExternalTemporaryError("operational query failed") from None

    def run(self, args: list[str], cwd: Path, timeout: float) -> None:
        if not 0 < timeout <= 1800:
            raise ValueError("invalid process deadline")
        # Subprocess diagnostics can contain paths, credentials and raw data.
        # Failures expose a fixed code; detailed diagnostics require an operator.
        environment = {"PATH": os.defpath, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
                       "PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "GIT_TERMINAL_PROMPT": "0"}
        if os.name == "nt":
            environment["SystemRoot"] = os.environ.get("SystemRoot", "C:\\Windows")
        try:
            subprocess.run(args, cwd=cwd, env=environment, timeout=timeout, check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            raise ExternalTemporaryError("operational command failed") from None


def seal_wheels(root: Path, pins: Path) -> dict:
    """Materialize hash lock from reviewed local wheels; no download or resolver.

    Platform-specific ARM64 artifacts must be provided at the staging gate.
    All dependencies (including deploy tests) must have an exact reviewed pin.
    """
    expected = {}
    for line in pins.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.+_-]+)", line)
        if not match:
            raise DataIntegrityError("dependency policy requires exact pins")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        expected[name] = match[2]
    wheels = {}
    for path in root.glob("*.whl"):
        contained(root, path)
        with zipfile.ZipFile(path) as archive:
            metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or archive.getinfo(metadata[0]).file_size > 1024 * 1024:
                raise DataIntegrityError("wheel metadata invalid")
            content = archive.read(metadata[0]).decode()
        name = re.search(r"^Name: (.+)$", content, re.M)
        version = re.search(r"^Version: (.+)$", content, re.M)
        if not name or not version:
            raise DataIntegrityError("wheel identity absent")
        normalized = re.sub(r"[-_.]+", "-", name[1].strip()).lower()
        if normalized in wheels or expected.get(normalized) != version[1].strip():
            raise DataIntegrityError("wheel differs from reviewed pin policy")
        wheels[normalized] = {"version": version[1].strip(), "file": path.name, "sha256": digest(path)}
    if set(wheels) != set(expected) or not wheels:
        raise DataIntegrityError("wheelhouse must contain every pinned dependency exactly once")
    value = {"version": 1, "pins_sha256": digest(pins), "wheels": wheels}
    atomic_json(root / "wheel-lock.json", value)
    return value


def verify_wheels(root: Path, pins: Path) -> tuple[str, str]:
    value = read_json(root / "wheel-lock.json")
    if value.get("version") != 1 or value.get("pins_sha256") != digest(pins):
        raise DataIntegrityError("wheel lock policy mismatch")
    rows = []
    for name, item in sorted(value["wheels"].items()):
        if not re.fullmatch(r"[a-z0-9-]+", name) or not re.fullmatch(r"[A-Za-z0-9.+_-]+", item["version"]):
            raise DataIntegrityError("wheel lock identity invalid")
        path = contained(root, root / item["file"])
        if path.parent != root or digest(path) != item["sha256"]:
            raise DataIntegrityError("wheel checksum mismatch")
        rows.append(f'{name}=={item["version"]} --hash=sha256:{item["sha256"]}')
    expected = {re.sub(r"[-_.]+", "-", line.split("==")[0]).lower(): line.split("==")[1]
                for line in pins.read_text().splitlines() if line.strip() and not line.startswith("#")}
    if expected != {name: item["version"] for name, item in value["wheels"].items()}:
        raise DataIntegrityError("incomplete wheel lock")
    return "\n".join(rows) + "\n", digest(root / "wheel-lock.json")


class Builder:
    def __init__(self, store: ReleaseStore, runner: Runner, source: Path, wheels: Path, *, python: str = sys.executable) -> None:
        self.store, self.runner, self.source, self.wheels, self.python = store, runner, source, wheels, python
        self.provider_only = False

    def build(self, commit: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise DataIntegrityError("candidate requires an explicit full commit")
        # Source must be an independently exported, reviewed tree. Never copy a
        # working tree wholesale: it can contain .env, databases and caches.
        pins = self.source / "deploy" / "dependencies.pins"
        if self.provider_only:
            current = self.store.current()
            if current is None:
                raise DataIntegrityError("provider-only update requires previous release")
            previous_pins = self.store.path(current) / "app" / "deploy" / "dependencies.pins"
            def versions(path):
                return dict(line.strip().split("==", 1) for line in path.read_text().splitlines() if line.strip() and not line.startswith("#"))
            old, new = versions(previous_pins), versions(pins)
            changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
            if changed != {"yt-dlp"}:
                raise DataIntegrityError("emergency update must change only the yt-dlp pin")
        lock_text, lock_hash = verify_wheels(self.wheels, pins)
        identity = "r-" + commit[:16] + "-" + lock_hash[:16]
        path = self.store.path(identity)
        if path.exists():
            existing = self.store.validate(identity)
            if existing["commit"] != commit or existing["dependency_hash"] != lock_hash:
                raise DataIntegrityError("release identity collision")
            return identity
        if sum(1 for p in self.store.releases.iterdir() if p.is_dir()) >= 16:
            raise DataIntegrityError("release capacity reached; retain rollback evidence before cleanup")
        path.mkdir()
        (path / ".building").write_text("incomplete", encoding="ascii")
        try:
            app = path / "app"
            app.mkdir()
            for name in ("src", "tests", "deploy"):
                source = contained(self.source, self.source / name)
                for node in source.rglob("*"):
                    contained(self.source, node)
                    if node.is_file() and (node.suffix.lower() in {".db", ".sql", ".log", ".pyc"} or node.name == ".env"):
                        raise DataIntegrityError("source export contains forbidden artifacts")
                shutil.copytree(source, app / name)
            for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
                source = self.source / name
                if source.is_file():
                    contained(self.source, source)
                    shutil.copyfile(source, app / name)
            (path / "dependencies.lock").write_text(lock_text, encoding="ascii")
            self.runner.run([self.python, "-m", "venv", "--copies", str(path / ".venv")], path, 120)
            python = path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self.runner.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", "--require-hashes", "--only-binary=:all:",
                             "--find-links", str(self.wheels), "-r", str(path / "dependencies.lock")], path, 600)
            self.runner.run([str(python), "-m", "pip", "check"], path, 30)
            # CPython's Linux venv may create lib64 -> lib even with --copies.
            # Materialize only that known internal alias; all other links fail
            # the subsequent inventory validation. No external target is copied.
            alias = path / ".venv" / "lib64"
            library = path / ".venv" / "lib"
            if alias.is_symlink():
                if alias.resolve() != library.resolve() or library.is_symlink():
                    raise DataIntegrityError("unexpected virtual environment alias")
                alias.unlink()
                shutil.copytree(library, alias)
            # Manifest is published only after deployment preflight/test/backup.
            files = {}
            for node in path.rglob("*"):
                contained(path, node)
                if node.is_file() and node.name != ".building":
                    files[node.relative_to(path).as_posix()] = digest(node)
            value = dict(release=identity, commit=commit, python=".".join(map(str, sys.version_info[:3])),
                         dependency_hash=lock_hash, schema_min=5, schema_max=5,
                         built_at=datetime.now(timezone.utc).isoformat(), app_version="0.1.0",
                         entrypoints=["discord-bot", "watch-web", "operations"], config_version=1, files=files)
            atomic_json(path / "candidate.json", value)
            return identity
        except BaseException:
            self.store.remove(identity, set())
            raise

    def publish(self, identity: str) -> None:
        path = self.store.path(identity)
        if (path / "manifest.json").exists():
            self.store.validate(identity)
            return
        value = read_json(path / "candidate.json", 4 * 1024 * 1024)
        for relative, checksum in value["files"].items():
            if digest(contained(path, path / relative)) != checksum:
                raise DataIntegrityError("candidate mutated after validation")
        (path / "candidate.json").unlink()
        atomic_json(path / "manifest.json", value)
        (path / ".building").unlink()
        self.store.validate(identity)
        if os.name != "nt":
            for node in path.rglob("*"):
                node.chmod(node.stat().st_mode & ~0o222)
            path.chmod(0o555)
