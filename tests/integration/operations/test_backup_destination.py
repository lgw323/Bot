"""A9-BT1: explicit destination policy, with no real remote or credentials."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters.configuration import load_settings
from discordbot.operations.adapters import backup_destination as policy
from discordbot.operations.adapters.git_backup import GitBackupStore, GitRemoteBackup, GitTransport
from discordbot.platform.errors import ConfigurationError, DataIntegrityError, ExternalTemporaryError

from .test_runtime import config_files


ISOLATED = "git@github.com:lgw323/A9-BT1-Synthetic.git"
ISOLATED_CONFIG = {"kind": "git-ssh", "target": "isolated", "repository": ISOLATED,
                   "ref": "refs/heads/db-backup"}


def test_explicit_isolated_destination_survives_configuration(config_files, monkeypatch):
    # RED on the original implementation: rejection, not accidental production I/O.
    # The released allowlist stays empty; only this fixture approves synthetic data.
    from discordbot.operations.adapters import configuration
    policy = getattr(configuration, "backup_destination", None)
    if policy is not None:
        monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({ISOLATED}))
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = ISOLATED_CONFIG
    file.write_text(json.dumps(value))
    calls = []
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport",
                        lambda *args: calls.append(args))
    settings = load_settings(file, credentials, "operations")
    assert settings.backup_remote.destination.repository == ISOLATED
    assert settings.backup_remote.destination.ref == "refs/heads/db-backup"
    assert calls == [(credentials / "backup_ssh_key", credentials / "known_hosts")]


@pytest.fixture
def approved(monkeypatch):
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({ISOLATED}))
    return policy.BackupDestination("staging", "isolated", ISOLATED)


def test_no_real_isolated_recipient_is_enabled():
    assert policy.ISOLATED_REPOSITORIES == frozenset()


@pytest.mark.parametrize("repository", [policy.REMOTE, "git@github.com:lgw323/Bot.git",
    "git@github.com:another/Backup.git", "git@elsewhere.invalid:lgw323/Backup.git",
    "https://github.com/lgw323/Backup.git", "file:///tmp/backup.git", "--upload-pack=command"])
def test_allowlist_cannot_override_transport_owner_or_production_boundary(repository, monkeypatch):
    monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({repository}))
    with pytest.raises(ConfigurationError):
        policy.validate(policy.BackupDestination("staging", "isolated", repository))


def test_missing_adapter_destination_does_not_fall_back(tmp_path):
    with pytest.raises(ConfigurationError):
        GitBackupStore(None, tmp_path, None)


@pytest.mark.parametrize("remote", [
    {}, [], "isolated", False,
    {k: v for k, v in ISOLATED_CONFIG.items() if k != "repository"},
    {k: v for k, v in ISOLATED_CONFIG.items() if k != "ref"},
    {k: v for k, v in ISOLATED_CONFIG.items() if k != "target"},
    dict(ISOLATED_CONFIG, target="production"),
    dict(ISOLATED_CONFIG, target=None),
    dict(ISOLATED_CONFIG, kind="https"),
    dict(ISOLATED_CONFIG, extra="unexpected"),
    dict(ISOLATED_CONFIG, repository=None),
    dict(ISOLATED_CONFIG, repository=[]),
    dict(ISOLATED_CONFIG, repository=policy.REMOTE),
    dict(ISOLATED_CONFIG, repository="git@github.com:lgw323/Bot.git"),
    dict(ISOLATED_CONFIG, repository="git@github.com:lgw323/Unapproved.git"),
    dict(ISOLATED_CONFIG, repository="git@github.com:another/A9-BT1-Synthetic.git"),
    dict(ISOLATED_CONFIG, repository="git@evil.invalid:lgw323/A9-BT1-Synthetic.git"),
    dict(ISOLATED_CONFIG, repository="ssh://git@github.com/lgw323/A9-BT1-Synthetic.git"),
    dict(ISOLATED_CONFIG, repository="https://github.com/lgw323/A9-BT1-Synthetic.git"),
    dict(ISOLATED_CONFIG, repository="file:///tmp/remote.git"),
    dict(ISOLATED_CONFIG, repository="ext::command"),
    dict(ISOLATED_CONFIG, repository="--upload-pack=command"),
    dict(ISOLATED_CONFIG, repository=ISOLATED + "\n"),
    dict(ISOLATED_CONFIG, repository="git@github.com:lgw323/../Bot-Data.git"),
    dict(ISOLATED_CONFIG, ref="refs/heads/main"),
    dict(ISOLATED_CONFIG, ref="--all"),
    dict(ISOLATED_CONFIG, ref="refs/heads/db-backup:refs/heads/main"),
    dict(ISOLATED_CONFIG, ref=None),
])
def test_rejected_configuration_precedes_credentials_and_transport(config_files, approved, monkeypatch, remote):
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = remote
    file.write_text(json.dumps(value))
    def forbidden(*args, **kwargs):
        pytest.fail("rejected configuration reached an external boundary")
    monkeypatch.setattr("discordbot.operations.adapters.configuration.read_secret", forbidden)
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "operations")


@pytest.mark.parametrize("environment,remote", [
    ("staging", {k: v for k, v in ISOLATED_CONFIG.items() if k != "target"} | {"repository": policy.REMOTE}),
    ("production", ISOLATED_CONFIG),
])
def test_environment_target_conflicts(config_files, approved, monkeypatch, environment, remote):
    file, credentials = config_files
    value = json.loads(file.read_text())
    value.update(environment=environment, backup_remote=remote)
    file.write_text(json.dumps(value))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("subprocess"))
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "operations")


@pytest.mark.parametrize("field", ["environment", "backup_remote", "repository", "target"])
def test_duplicate_target_information_is_rejected(config_files, approved, field):
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = ISOLATED_CONFIG
    raw = json.dumps(value)
    original = json.dumps(value.get(field, ISOLATED_CONFIG.get(field)))
    raw = raw.replace(f'"{field}": {original}', f'"{field}": {original}, "{field}": {original}')
    file.write_text(raw)
    with pytest.raises(DataIntegrityError, match="invalid artifact metadata"):
        load_settings(file, credentials, "operations")


def test_missing_remote_is_not_local_only(config_files):
    file, credentials = config_files
    value = json.loads(file.read_text())
    del value["backup_remote"]
    file.write_text(json.dumps(value))
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "operations")


def test_explicit_null_does_not_construct_transport(config_files, monkeypatch):
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport",
                        lambda *args: pytest.fail("local-only transport"))
    file, credentials = config_files
    assert load_settings(file, credentials, "operations").backup_remote is None


@pytest.mark.parametrize("change", [{"repository": policy.REMOTE}, {"ref": "refs/heads/main"},
                                  {"environment": "production"}, {"target": "production"}])
def test_adapter_revalidates_before_effects(tmp_path, approved, change):
    destination = replace(approved, **change)
    class Forbidden:
        def run(self, *args, **kwargs):
            pytest.fail("executor/transport ran")
    with pytest.raises(ConfigurationError):
        GitBackupStore(Forbidden(), tmp_path / "absent", destination)
    with pytest.raises(ConfigurationError):
        GitRemoteBackup(SimpleNamespace(destination=destination), Forbidden())
    assert not (tmp_path / "absent").exists()


@pytest.mark.asyncio
async def test_async_adapter_passes_selected_destination(config_files, approved, monkeypatch):
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = ISOLATED_CONFIG
    file.write_text(json.dumps(value))
    calls = []
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport", lambda *args: object())
    settings = load_settings(file, credentials, "operations")
    settings.backups.mkdir()
    class Executor:
        async def run(self, function):
            return function()
    def publish(store, *args):
        calls.append(store.destination)
        raise ExternalTemporaryError("synthetic outage")
    monkeypatch.setattr(GitBackupStore, "publish", publish)
    with pytest.raises(ExternalTemporaryError):
        await GitRemoteBackup(settings.backup_remote, Executor()).publish(file, "synthetic", "synthetic")
    assert calls == [approved]  # No retry or production fallback.


@pytest.mark.parametrize("fault", ["timeout", "oserror", "nonzero"])
def test_transport_failure_has_one_bounded_attempt(tmp_path, monkeypatch, fault):
    import subprocess
    import time
    transport = object.__new__(GitTransport)
    transport.deadline = time.monotonic() + 90
    transport.environment = {}
    calls = []
    def fail(argv, **kwargs):
        calls.append((argv, kwargs))
        if fault == "timeout":
            raise subprocess.TimeoutExpired("synthetic", 1)
        if fault == "oserror":
            raise OSError("synthetic")
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ExternalTemporaryError):
        transport.run(tmp_path, ["fetch", ISOLATED, policy.REF])
    assert len(calls) == 1
    assert policy.REMOTE not in calls[0][0]
    assert calls[0][1]["timeout"] <= 30
    assert "protocol.allow=never" in calls[0][0]
    assert "protocol.ssh.allow=always" in calls[0][0]
