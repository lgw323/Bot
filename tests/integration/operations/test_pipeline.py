import asyncio
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.deployment import LocalDeployment
from discordbot.operations.application.deployment import Deployment
from discordbot.platform.errors import ExternalTemporaryError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from .test_build import builder
from .test_filesystem import release, symlinks_on_windows


@pytest.mark.parametrize("readiness_failure", [False, True])
def test_real_local_pipeline_with_synthetic_db_and_fake_services(builder, tmp_path, readiness_failure):
    store = builder.store
    release(store.root, "old")
    store.activate("old")
    for directory in ("state", "cache", "backups", "audit"):
        (tmp_path / directory).mkdir()
    database_path = tmp_path / "synthetic.db"
    async def bootstrap():
        database = SqliteDatabase(DatabaseConfig(database_path))
        try:
            await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
        finally:
            await database.stop()
    asyncio.run(bootstrap())
    settings = SimpleNamespace(database=database_path, state=tmp_path / "state", cache=tmp_path / "cache",
        backups=tmp_path / "backups", audit=tmp_path / "audit", operation_lock=tmp_path / "lock",
        secrets=SimpleNamespace(db_key=Fernet.generate_key()), key_id="synthetic", backup_remote=None)
    calls = []
    def ready(identity):
        calls.append("ready:" + identity)
        assert store.current() == identity
        if readiness_failure and identity != "old":
            raise ExternalTemporaryError("injected")
    services = SimpleNamespace(stop=lambda: calls.append("stop"), start=lambda: calls.append("start"),
                               ready=ready, smoke=lambda identity: calls.append("smoke:" + identity))
    port = LocalDeployment(settings, builder, services, Audit(settings.audit))
    result = Deployment(port).run("a" * 40)
    assert result.result == ("failed" if readiness_failure else "ok")
    assert store.current() == ("old" if readiness_failure else result.release)
    assert len(list(settings.backups.glob("*.enc"))) >= 2
    assert any("pytest" in command for command in builder.runner.calls)
    assert not list(store.path(result.release).glob(".building"))
    assert len(list(settings.audit.glob("*.json"))) >= 6
