"""Linux operational adapters. Constructing them never runs commands."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener
from urllib.error import URLError

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.build import Builder, Runner
from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore, atomic_json, read_json
from discordbot.operations.adapters.recovery import Backups
from discordbot.operations.application.deployment import Deployment
from discordbot.operations.ports.deployment import Release
from discordbot.platform.errors import DataIntegrityError, ExternalTemporaryError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseRequest, DatabaseState


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExternalTemporaryError("health redirects are forbidden")


class Services:
    names = ("discord-bot", "watch-web")

    def __init__(self, runner: Runner, cwd: Path, ports: tuple[int, int]) -> None:
        self.runner, self.cwd, self.ports = runner, cwd, ports

    def stop(self) -> None:
        # Both units in one bounded systemd transaction. No Requires/PartOf
        # relation joins their ordinary restart/failure lifetimes.
        self.runner.run(["systemctl", "stop", *self.names], self.cwd, 90)
        for name in self.names:
            state = self.runner.read(["systemctl", "show", name, "--property=ActiveState", "--value"], self.cwd, 10)
            result = self.runner.read(["systemctl", "show", name, "--property=Result", "--value"], self.cwd, 10)
            if state != "inactive" or result != "success":
                raise ExternalTemporaryError("service stop/checkpoint is not confirmed")

    def start(self) -> None:
        self.runner.run(["systemctl", "start", *self.names], self.cwd, 90)

    def probe(self, index: int, path: str) -> dict:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            with opener.open(f"http://127.0.0.1:{self.ports[index]}{path}", timeout=2) as response:
                if response.geturl() != f"http://127.0.0.1:{self.ports[index]}{path}":
                    raise ValueError
                raw = response.read(8193)
                if len(raw) > 8192:
                    raise ValueError
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError
                return value
        except (OSError, URLError, ValueError):
            raise ExternalTemporaryError("local readiness probe failed") from None

    def coherent(self, release: str) -> None:
        for index, name in enumerate(self.names):
            value = self.probe(index, "/health/ready")
            if value.get("ready") is not True or value.get("service") != name or value.get("release") != release:
                raise ExternalTemporaryError("service pair is not ready on expected release")

    def ready(self, release: str, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.coherent(release)
                return
            except ExternalTemporaryError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def smoke(self, release: str) -> None:
        self.coherent(release)
        for index, name in enumerate(self.names):
            value = self.probe(index, "/health/live")
            if value != {"live": True, "release": release, "service": name}:
                raise ExternalTemporaryError("local liveness smoke failed")


class LocalDeployment:
    def __init__(self, settings, builder: Builder, services: Services, audit: Audit) -> None:
        self.settings, self.builder, self.services, self.journal = settings, builder, services, audit
        self.store = builder.store
        self.previous = None

    def lock(self):
        return ExclusiveLock(self.settings.operation_lock).acquire()

    def current(self):
        value = self.store.current()
        self.previous = value
        return self.release(value) if value else None

    def release(self, identity):
        path = self.store.path(identity)
        value = read_json(path / ("manifest.json" if (path / "manifest.json").exists() else "candidate.json"), 4*1024*1024)
        return Release(identity, value["schema_min"], value["schema_max"])

    def build(self, revision):
        return self.release(self.builder.build(revision))

    def preflight(self, release):
        path = self.store.path(release.identity)
        if (path / "manifest.json").exists():
            self.store.validate(release.identity)
        elif not (path / "candidate.json").is_file() or not (path / ".venv" / "pyvenv.cfg").is_file():
            raise DataIntegrityError("candidate is incomplete")
        for directory in (self.settings.database.parent, self.settings.state, self.settings.cache,
                          self.settings.backups, self.settings.audit):
            if not directory.is_dir() or not os.access(directory, os.W_OK):
                raise DataIntegrityError("persistent directory preflight failed")

    def test(self, release):
        path = self.store.path(release.identity)
        python = path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # Explicit offline deploy subset. Full regression remains a source review
        # gate; no legacy conftest/DB/network is imported by this deploy subset.
        self.builder.runner.run([str(python), "-m", "pytest", "-p", "no:cacheprovider", "tests/integration/operations", "--confcutdir=tests/integration/operations",
                                 "-q", "-W", "error::RuntimeWarning", "-W", "error::pytest.PytestUnraisableExceptionWarning"], path / "app", 300)

    def compatible(self, release):
        async def check():
            database = SqliteDatabase(DatabaseConfig(self.settings.database))
            try:
                report = await database.inspect(DatabaseRequest.within(10))
                if report.state is not DatabaseState.VALID or not release.schema_min <= report.migration_version <= release.schema_max:
                    raise DataIntegrityError("live database is incompatible; explicit verified data candidate required")
            finally:
                await database.stop()
        asyncio.run(check())

    def backup(self, release):
        asyncio.run(backup_once(self.settings, self.journal, release.identity))

    def publish(self, release): self.builder.publish(release.identity)

    def stop(self):
        self.services.stop()

    def activate(self, release):
        # Graceful service stop checkpoints Music and drains DB writers. Capture
        # that final quiescent state as well as the earlier online predeploy point.
        self.backup(release)
        atomic_json(self.settings.state / "activation.json", {"previous": self.previous, "target": release.identity})
        self.store.activate(release.identity)

    def start(self): self.services.start()
    def ready(self, release): self.services.ready(release.identity)
    def smoke(self, release): self.services.smoke(release.identity)
    def audit(self, operation, release, result, reason): self.journal.write(operation, release, result, reason)

    def retain(self, release, previous):
        protected = {release.identity}
        if previous:
            protected.add(previous.identity)
        atomic_json(self.settings.state / "rollback.json", {"previous": previous.identity if previous else None,
                    "current": release.identity, "protected_until": time.time() + 7 * 86400})
        candidates = sorted((p for p in self.store.releases.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        keep = protected | {p.name for p in candidates[:4]}
        for path in candidates:
            if path.name not in keep and time.time() - path.stat().st_mtime >= 7 * 86400:
                self.store.remove(path.name, keep)

    def discard(self, release):
        protected = {self.previous} if self.previous else set()
        if (self.store.path(release.identity) / "manifest.json").exists():
            return  # A previously validated reusable release is not a failed build.
        self.store.remove(release.identity, protected)


async def backup_once(settings, audit, release):
    database = SqliteDatabase(DatabaseConfig(settings.database))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="operations-files")
    try:
        await database.start()
        remote = None
        if settings.backup_remote is not None:
            from discordbot.operations.adapters.git_backup import GitRemoteBackup
            remote = GitRemoteBackup(settings.backup_remote, executor)
        return await Backups(database, settings.backups, settings.secrets.db_key, settings.key_id,
                             executor, audit, remote=remote).create(release)
    finally:
        await database.stop()
        await executor.close(grace_seconds=95 if settings.backup_remote is not None else 5)
