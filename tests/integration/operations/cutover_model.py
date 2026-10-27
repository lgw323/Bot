"""Executable synthetic model. Host/install/old-code adapters are explicitly fake.

DB bootstrap, encrypted backup/restore, journal helper, kernel operation lock,
service command vectors and atomic intent/pointer evidence use repository code.
"""
import asyncio
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

from cryptography.fernet import Fernet
from discordbot.operations.adapters.filesystem import atomic_json, read_json
from discordbot.operations.adapters.deployment import Services
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("cutover_local_prototype", ROOT / "deploy/tools/cutover_controller.py")
cc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cc
spec.loader.exec_module(cc)
PREVIOUS = "r-8e9018d4b8061cde-3dac82a792fad576"
CANDIDATE = "r-" + "a" * 16 + "-" + "b" * 16  # synthetic, never a candidate freeze


def sql(path, statement):
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        return conn.execute(statement).fetchall()


async def seed(path):
    db = SqliteDatabase(DatabaseConfig(path))
    try:
        await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    finally:
        await db.stop()
    sql(path, "PRAGMA journal_mode=DELETE")
    sql(path, "INSERT INTO users(user_id,guild_id,xp,level) VALUES(1,1,21,1)")


async def encrypted_backup(path, dest, key):
    db = SqliteDatabase(DatabaseConfig(path))
    try:
        await db.start()
        return await DataRecovery(db).backup(dest, key, DatabaseRequest.within(10))
    finally:
        await db.stop()


async def restored(path, enc, key):
    db = SqliteDatabase(DatabaseConfig(path))
    try:
        return await DataRecovery(db).restore_copy(RecoveryCandidate(enc, key), path, DatabaseRequest.within(10))
    finally:
        await db.stop()


class FakeRunner:
    def __init__(self, model):
        self.model, self.commands = model, []
        self.units = {}
        for index, name in enumerate((*cc.PAIR, *cc.OTHER, *cc.OPERATIONS)):
            running = name in (*cc.PAIR, *cc.OTHER)
            self.units[name] = {"ActiveState": "active" if running else "inactive", "Result": "success",
                                "MainPID": str(index+10) if running else "0",
                                "InvocationID": str(index), "NRestarts": "0"}

    def read(self, args, cwd, timeout):
        assert args[:2] == ["systemctl", "show"] and args[-1] == "--value"
        unit = args[2]
        prop = args[3].removeprefix("--property=")
        assert unit in self.units and prop in cc.PROPERTIES and 0 < timeout <= 10
        self.commands.append(tuple(args))
        return self.units[unit][prop]

    def run(self, args, cwd, timeout):
        assert tuple(args) in (("systemctl", "stop", *cc.PAIR), ("systemctl", "start", *cc.PAIR))
        assert 0 < timeout <= 90
        self.commands.append(tuple(args))
        self.model.log.append(args[1])
        for unit in cc.PAIR:
            self.units[unit].update(ActiveState="inactive" if args[1] == "stop" else "active",
                                    MainPID="0" if args[1] == "stop" else "123")


class ModelExclusion:
    """Synthetic state-machine exclusion, NOT a host isolation implementation."""
    epoch = "synthetic-only-epoch"
    def __init__(self, model):
        self.model, self.fenced, self.external_consumers = model, False, 0
    def acquire(self):
        self.model.log.append("exclude")
        if self.external_consumers:
            raise cc.Blocked("consumer_not_stopped")
        self.fenced = True
    def check(self, target, deadline):
        if not self.fenced or self.external_consumers or target != self.model.database or time.monotonic() >= deadline:
            raise cc.Blocked("consumer_not_stopped")
    def handoff_pair(self):
        assert self.fenced
        self.model.log.append("handoff_pair")
    def retain_stopped(self):
        assert self.fenced
        self.model.log.append("retain_fence_model")


class ModelStore:
    def __init__(self, model):
        self.model = model
        self.path = model.root / "pointer.json"
        atomic_json(self.path, {"current": PREVIOUS})
    def current(self):
        return read_json(self.path)["current"]
    def activate(self, identity):
        assert identity == CANDIDATE
        self.model.log.append("pointer")
        atomic_json(self.path, {"current": identity})


class ModelWorkers:
    def __init__(self, model):
        self.model = model
        self.admission_override = {}
    def admission(self, plan):
        self.model.log.append("admit")
        return dict(candidate=plan.candidate, previous=plan.previous, source_sha256=plan.source_sha256,
                    manifest_sha256=plan.manifest_sha256, wheel_lock_sha256=plan.wheel_lock_sha256,
                    reviewed_promotion_included=True, partial_present=False, release_count=15,
                    **self.admission_override)
    def install(self, release): self.model.log.append("install_fake")
    def native(self, release): self.model.log.append("native_fake")
    def latest_restore(self, release):
        self.model.log.append("latest_restore")
        asyncio.run(encrypted_backup(self.model.database, self.model.root/"online.enc", self.model.key))
        asyncio.run(restored(self.model.root/"isolated.db", self.model.root/"online.enc", self.model.key))
    def old_compatibility(self, release):
        self.model.log.append("old_adapter_fake")
        assert sql(self.model.root/"isolated.db", "SELECT xp FROM users") == [(21,)]
        sql(self.model.root/"isolated.db", "UPDATE users SET xp=22")
    def candidate_return(self, release):
        self.model.log.append("candidate_adapter_fake")
        assert sql(self.model.root/"isolated.db", "SELECT xp FROM users") == [(22,)]
        assert sql(self.model.database, "SELECT xp FROM users") == [(21,)]
    def final_restore(self, release):
        self.model.log.append("final_restore")
        destination = self.model.root/"final-restored.db"
        asyncio.run(restored(destination, self.model.root/"final.enc", self.model.key))
        return cc.wal.Request(self.model.database, self.model.lock, destination, cc.wal.checksum(destination),
                              self.model.root/"preserved", self.model.root/"wal.jsonl", seconds=10)


class Model:
    def __init__(self, root: Path, *, cutover=True):
        self.root = root.resolve()
        assert self.root.is_dir()
        self.database, self.lock = self.root/"synthetic.db", self.root/"operations.lock"
        self.log = []
        self.key = Fernet.generate_key()  # ephemeral synthetic key, never saved/emitted
        asyncio.run(seed(self.database))
        self.runner = FakeRunner(self)
        self.services = Services(self.runner, self.root, (1,2))
        self.reader = cc.FixedHostReader(self.runner, self.root)
        self.exclusion = ModelExclusion(self)
        self.store = ModelStore(self)
        state = self.root/"state"
        state.mkdir()
        def event(name):
            return lambda release: self.log.append(name)
        def backup(release):
            self.log.append("final_backup")
            assert all(self.runner.units[u]["ActiveState"] == "inactive" for u in cc.PAIR)
            asyncio.run(encrypted_backup(self.database, self.root/"final.enc", self.key))
        self.local = SimpleNamespace(settings=SimpleNamespace(database=self.database, operation_lock=self.lock, state=state),
            store=self.store, preflight=event("preflight_fake"), test=event("installed_tests_fake"),
            publish=event("publish_fake"), stop=self.services.stop, start=self.services.start, backup=backup,
            ready=event("ready_fake"), smoke=event("smoke_fake"))
        self.workers = ModelWorkers(self)
        self.bridge = cc.DeploymentBridge(self.local, self.workers)
        self.signals = cc.Signals()
        self.plan = cc.Plan("synthetic-run", CANDIDATE, PREVIOUS, "c"*64, "d"*64, "b"*64,
                            cutover=cutover, canonical_wal_approved=cutover)
        self.controller = cc.Controller(self.plan, self.bridge, self.reader, self.exclusion,
                                        self.signals, self.root/"controller.json")
