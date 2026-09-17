from dataclasses import replace
import json

import pytest

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.configuration import BackupRemoteSettings, load_settings
from discordbot.operations.adapters.deployment import backup_once
from discordbot.operations.adapters.filesystem import read_json
from discordbot.operations.adapters.git_backup import GitRemoteBackup, GitTransport
from discordbot.platform.errors import ConfigurationError, ExternalTemporaryError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

from .test_runtime import config_files

REMOTE_CONFIG = {"kind": "git-ssh", "repository": "git@github.com:lgw323/Bot-Data.git", "ref": "refs/heads/db-backup"}


def test_remote_config_requires_explicit_repository_and_scope(config_files, monkeypatch):
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = REMOTE_CONFIG
    file.write_text(json.dumps(value))
    calls = []
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport", lambda *args: calls.append(args))
    assert load_settings(file, credentials, "watch-web").backup_remote is None
    assert load_settings(file, credentials, "discord-bot").backup_remote is None
    assert calls == []
    loaded = load_settings(file, credentials, "operations")
    assert loaded.backup_remote.workspace == loaded.backups / "remote-work"
    assert calls == [(credentials / "backup_ssh_key", credentials / "known_hosts")]
    assert "backup_ssh_key" not in repr(loaded)
    value["backup_remote"] = dict(REMOTE_CONFIG, repository="git@github.com:lgw323/Bot.git")
    file.write_text(json.dumps(value))
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "operations")


@pytest.mark.asyncio
async def test_failed_remote_in_real_backup_path_preserves_latest(config_files, monkeypatch):
    file, credentials = config_files
    settings = load_settings(file, credentials, "operations")
    for path in (settings.backups, settings.audit):
        path.mkdir()
    database = SqliteDatabase(DatabaseConfig(settings.database))
    try:
        await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    finally:
        await database.stop()
    audit = Audit(settings.audit)
    first = await backup_once(settings, audit, "r-0123456789abcdef-0123456789abcdef")
    remote = BackupRemoteSettings(settings.backups / "remote-work", credentials / "ssh", credentials / "hosts")
    configured = replace(settings, backup_remote=remote)
    calls = []
    async def fail(self, artifact, checksum, identity):
        calls.append(identity)
        assert artifact.suffix == ".enc"
        raise ExternalTemporaryError("synthetic transport outage")
    monkeypatch.setattr(GitRemoteBackup, "publish", fail)
    with pytest.raises(ExternalTemporaryError):
        await backup_once(configured, audit, "r-0123456789abcdef-0123456789abcdef")
    assert len(calls) == 1
    assert read_json(settings.backups / "latest.json")["identity"] == first
    assert len(list(settings.backups.glob("*.enc"))) == 2


def test_transport_deadline_stops_before_subprocess(tmp_path, monkeypatch):
    transport = object.__new__(GitTransport)
    transport.deadline = 0
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.subprocess.run", lambda *a, **k: pytest.fail("process started"))
    with pytest.raises(ExternalTemporaryError, match="deadline"):
        transport.run(tmp_path, ["fetch"])
