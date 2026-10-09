"""A9-BT1-V1 reviewer probes. Synthetic files and denied/fake transport only."""

import asyncio
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters import backup_destination as policy
from discordbot.operations.adapters import configuration, git_backup
from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.deployment import backup_once
from discordbot.operations.adapters.recovery import Backups
from discordbot.platform.errors import ConfigurationError, ConflictError, DataIntegrityError, ExternalTemporaryError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

from .test_git_backup import LocalTransport


ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "git@github.com:lgw323/A9-V1-Reviewer-Synthetic.git"
ISOLATED = {"kind": "git-ssh", "target": "isolated", "repository": REPOSITORY,
            "ref": "refs/heads/db-backup"}
PRODUCTION = {k: v for k, v in ISOLATED.items() if k != "target"} | {"repository": policy.REMOTE}
RELEASE = "r-0123456789abcdef-0123456789abcdef"


def forbidden(*args, **kwargs):
    pytest.fail("review boundary reached credentials, executor or real transport")


@pytest.fixture
def config(tmp_path, monkeypatch):
    value = json.loads((ROOT / "deploy/config.example.json").read_text())
    value["paths"] = {name: str(tmp_path / name) for name in value["paths"]}
    value.update(master=101, admin_channel=102, main_channels=[[103, 104]],
                 music_channels=[[103, 105]], public_origin="https://review.synthetic.test",
                 key_id="review-key")
    path = tmp_path / "config.json"
    monkeypatch.setattr(configuration, "read_secret", forbidden)
    monkeypatch.setattr(git_backup, "GitTransport", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    return path, value


def load(config, monkeypatch, *, environment="staging", remote=None, service="operations"):
    path, value = config
    value.update(environment=environment, backup_remote=remote)
    path.write_text(json.dumps(value))
    return configuration.load_settings(path, path.parent / "absent-credentials", service)


@pytest.mark.parametrize("environment,remote,expected", [
    ("production", PRODUCTION, policy.PRODUCTION), ("production", None, None),
    ("staging", None, None),
    ("staging", ISOLATED, policy.BackupDestination("staging", "isolated", REPOSITORY)),
])
@pytest.mark.parametrize("service", ["operations", "discord-bot", "watch-web"])
def test_config_service_compatibility(config, monkeypatch, environment, remote, expected, service):
    calls = []
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    monkeypatch.setattr(configuration, "read_secret", lambda *a: "A" * 43 + "=")
    monkeypatch.setattr(git_backup, "GitTransport", lambda *a: calls.append(a))
    settings = load(config, monkeypatch, environment=environment, remote=remote, service=service)
    if expected is not None and service == "operations":
        assert settings.backup_remote.destination == expected
        assert len(calls) == 1
    else:
        assert settings.backup_remote is None and calls == []


INVALID = [None, [], "isolated", True, {},
           *({k: v for k, v in ISOLATED.items() if k != missing} for missing in ISOLATED),
           *(dict(ISOLATED, **change) for change in [
               {"kind": "git-https"}, {"target": "production"}, {"environment": "staging"},
               {"repository": policy.REMOTE}, {"repository": "git@github.com:lgw323/DiscordBot.git"},
               {"repository": "git@github.com:other/A9-V1.git"},
               {"repository": "git@other.invalid:lgw323/A9-V1.git"},
               {"repository": "ssh://git@github.com/lgw323/A9-V1.git"},
               {"repository": "https://github.com/lgw323/A9-V1.git"},
               {"repository": "file:///tmp/A9-V1.git"}, {"repository": "ext::command"},
               {"repository": "-x"}, {"repository": REPOSITORY + "\n"},
               {"repository": "git@github.com:lgw323/../Bot-Data.git"},
               {"repository": []}, {"ref": "refs/heads/main"}, {"ref": "--all"},
               {"ref": ["refs/heads/db-backup"]}, {"ref": None}])]


@pytest.mark.parametrize("remote", INVALID[1:])
def test_invalid_config_rejects_before_secret_transport_or_process(config, monkeypatch, remote):
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    with pytest.raises(ConfigurationError):
        load(config, monkeypatch, remote=remote)


@pytest.mark.parametrize("environment,remote", [("production", ISOLATED), ("staging", PRODUCTION),
                                                ("staging", ISOLATED)])
def test_conflict_or_empty_allowlist_has_no_fallback(config, monkeypatch, environment, remote):
    assert policy.ISOLATED_REPOSITORIES == frozenset()
    with pytest.raises(ConfigurationError):
        load(config, monkeypatch, environment=environment, remote=remote)


@pytest.mark.parametrize("field", ["backup_remote", "environment", "kind", "target", "repository", "ref", "ports"])
def test_duplicate_keys_reject_before_boundaries(config, monkeypatch, field):
    path, value = config
    value["backup_remote"] = ISOLATED
    raw = json.dumps(value)
    # Deliberately conflicting duplicates; last-key-wins must never grant access.
    raw = raw.replace('"' + field + '":', '"' + field + '": null, "' + field + '":', 1)
    path.write_text(raw)
    with pytest.raises(DataIntegrityError):
        configuration.load_settings(path, path.parent / "absent-credentials", "operations")


def test_absent_remote_is_not_null(config, monkeypatch):
    path, value = config
    del value["backup_remote"]
    path.write_text(json.dumps(value))
    with pytest.raises(ConfigurationError):
        configuration.load_settings(path, path.parent / "absent-credentials", "operations")


@pytest.mark.parametrize("destination", [None, {}, "production",
    policy.BackupDestination("staging", "production", policy.REMOTE),
    policy.BackupDestination("production", "isolated", REPOSITORY),
    policy.BackupDestination("staging", "isolated", REPOSITORY, "refs/heads/main"),
    policy.BackupDestination("staging", "isolated", "git@github.com:other/Backup.git"),
])
def test_direct_adapter_paths_revalidate(tmp_path, monkeypatch, destination):
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    monkeypatch.setattr(git_backup, "GitTransport", forbidden)
    settings = configuration.BackupRemoteSettings(tmp_path / "absent", tmp_path / "key", tmp_path / "hosts", destination)
    with pytest.raises(ConfigurationError):
        git_backup.GitRemoteBackup(settings, SimpleNamespace(run=forbidden))
    with pytest.raises(ConfigurationError):
        git_backup.GitBackupStore(SimpleNamespace(run=forbidden), tmp_path / "absent", destination)
    assert not settings.workspace.exists()


def test_fixture_approval_restores_defaults_and_cannot_allow_production(tmp_path, monkeypatch):
    assert policy.ISOLATED_REPOSITORIES == frozenset()
    original = policy.PRODUCTION
    with monkeypatch.context() as patch:
        patch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY, policy.REMOTE}))
        with pytest.raises(ConfigurationError):
            policy.validate(policy.BackupDestination("staging", "isolated", policy.REMOTE))
        destination = policy.parse(ISOLATED, "staging")
        with pytest.raises(FrozenInstanceError):
            destination.repository = policy.REMOTE
    assert policy.ISOLATED_REPOSITORIES == frozenset() and policy.PRODUCTION is original
    assert git_backup.GitBackupStore(None, tmp_path).destination is original
    with pytest.raises(ConfigurationError):
        policy.parse(ISOLATED, "staging")


def test_current_isolated_configuration_and_fetch_routing(tmp_path, monkeypatch):
    """Current destination routing remains mandatory in the extracted app."""
    value = json.loads((ROOT / "deploy/config.example.json").read_text())
    value["paths"] = {key: str(tmp_path / key) for key in value["paths"]}
    value["backup_remote"] = ISOLATED
    file = tmp_path / "config.json"
    file.write_text(json.dumps(value))
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    monkeypatch.setattr(configuration, "read_secret", lambda *a: "A" * 43 + "=")
    monkeypatch.setattr(git_backup, "GitTransport", lambda *a: None)
    loaded = configuration.load_settings(file, tmp_path, "operations")
    calls = []
    def record(root, arguments, data=None):
        calls.append(arguments)
        return b"a" * 40 if arguments[0] == "rev-parse" else b""
    store = git_backup.GitBackupStore(SimpleNamespace(run=record), tmp_path, loaded.backup_remote.destination)
    store.fetch(tmp_path)
    assert calls[1] == ["fetch", "--depth=1", "--no-tags", REPOSITORY, policy.REF]


@pytest.mark.asyncio
async def test_revoked_approval_is_checked_before_workspace_or_transport(tmp_path, monkeypatch):
    destination = policy.BackupDestination("staging", "isolated", REPOSITORY)
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    class Inline:
        async def run(self, function):
            return function()
    settings = configuration.BackupRemoteSettings(tmp_path / "absent", tmp_path / "key", tmp_path / "hosts", destination)
    adapter = git_backup.GitRemoteBackup(settings, Inline())
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset())
    monkeypatch.setattr(git_backup, "GitTransport", forbidden)
    with pytest.raises(ConfigurationError):
        await adapter.publish(tmp_path / "unused", "unused", "unused")
    assert not settings.workspace.exists()


@pytest.mark.parametrize("remaining", [-1, 0, 0.25, 90])
def test_deadline_admission_and_command_bound(tmp_path, monkeypatch, remaining):
    transport = object.__new__(git_backup.GitTransport)
    transport.environment = {}
    transport.deadline = 100 + remaining
    monkeypatch.setattr(git_backup.time, "monotonic", lambda: 100)
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired("synthetic", kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ExternalTemporaryError):
        transport.run(tmp_path, ["fetch", REPOSITORY, policy.REF])
    assert calls == ([] if remaining <= 0 else [min(30, remaining)])


@pytest.mark.asyncio
async def test_real_synthetic_backup_download_restore_and_cancellation(tmp_path, monkeypatch):
    """One target from parsed config through real encrypted SQLite recovery."""
    from cryptography.fernet import Fernet
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({REPOSITORY}))
    remote = tmp_path / "remote.git"
    remote.mkdir()
    transport = LocalTransport(remote, REPOSITORY)
    transport.run(remote, ["init", "--bare", "--template=", "."])
    tree = transport.run(remote, ["mktree"], b"").strip().decode()
    commit = transport.run(remote, ["commit-tree", tree], b"review synthetic\n").strip().decode()
    transport.run(remote, ["update-ref", policy.REF, commit])
    monkeypatch.setattr(git_backup, "GitTransport", lambda *a: transport)
    key = Fernet.generate_key()
    monkeypatch.setattr(configuration, "read_secret", lambda *a: key.decode())
    value = json.loads((ROOT / "deploy/config.example.json").read_text())
    value["paths"] = {name: str(tmp_path / name) for name in value["paths"]}
    value["backup_remote"] = ISOLATED
    file = tmp_path / "config.json"
    file.write_text(json.dumps(value))
    settings = configuration.load_settings(file, tmp_path / "absent-credentials", "operations")
    settings.backups.mkdir()
    settings.audit.mkdir()
    database = SqliteDatabase(DatabaseConfig(settings.database))
    try:
        before = await DataRecovery(database).bootstrap(DatabaseRequest.within(10))
    finally:
        await database.stop()
    audit = Audit(settings.audit)
    identity = await backup_once(settings, audit, RELEASE)
    downloaded = tmp_path / "downloaded"
    store = git_backup.GitBackupStore(transport, settings.backup_remote.workspace, settings.backup_remote.destination)
    store.download(identity, downloaded)
    network_calls = [c for c in transport.calls if c[0] in {"fetch", "push"}]
    assert [c[0] for c in network_calls] == ["fetch", "push", "fetch", "fetch"]
    assert all(c[-2] == REPOSITORY for c in network_calls)
    assert all(policy.REMOTE not in c for c in transport.calls)
    restored = SqliteDatabase(DatabaseConfig(tmp_path / "restored.db"))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="review-recovery")
    try:
        backups = Backups(restored, downloaded, key, settings.key_id, executor, audit)
        await backups.restore(restored.config.path, RELEASE, candidates=(identity,))
        await restored.start()
        after = await restored.inspect(DatabaseRequest.within(10))
        assert (before.data_checksum, before.metadata_checksum, before.counts) == (
            after.data_checksum, after.metadata_checksum, after.counts)
        with pytest.raises(ConflictError):
            await backups.restore(restored.config.path, RELEASE, candidates=(identity,))
    finally:
        await restored.stop()
        await executor.close(grace_seconds=5)
    latest = (settings.backups / "latest.json").read_bytes()
    async def cancelled(*args):
        raise asyncio.CancelledError
    monkeypatch.setattr(git_backup.GitRemoteBackup, "publish", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await backup_once(settings, audit, RELEASE)
    assert (settings.backups / "latest.json").read_bytes() == latest
    assert not list(downloaded.glob(".rehearsal-*"))
