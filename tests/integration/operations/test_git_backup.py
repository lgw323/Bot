"""Offline Git transport drills against disposable bare repositories and fake data."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from cryptography.fernet import Fernet
import pytest

from discordbot.operations.adapters.git_backup import (
    GitBackupStore, PREFIX, REF, REMOTE, retained, validate_pair,
)
from discordbot.platform.errors import ConflictError, DataIntegrityError, ExternalTemporaryError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER


class LocalTransport:
    """Replace the external boundary with a new local bare repo, never a real remote."""
    def __init__(self, remote: Path):
        self.remote = remote
        self.calls = []
        self.reject_push = False
        self.failed_readback = False
        self.pushed = False

    def run(self, root, arguments, data=None):
        self.calls.append(arguments)
        if arguments[0] == "push":
            assert arguments[-2] == REMOTE and arguments[-1].endswith(":" + REF)
            assert not any(arg.startswith(("--force", "+")) for arg in arguments)
            if self.reject_push:
                raise ExternalTemporaryError("synthetic rejected push")
            self.pushed = True
        if arguments[0] == "fetch" and self.failed_readback and self.pushed:
            raise ExternalTemporaryError("synthetic readback failure")
        args = [str(self.remote) if arg == REMOTE else arg for arg in arguments]
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="Synthetic", GIT_AUTHOR_EMAIL="synthetic@localhost",
                   GIT_COMMITTER_NAME="Synthetic", GIT_COMMITTER_EMAIL="synthetic@localhost")
        result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                                 "-c", "protocol.file.allow=always", *args],
                                cwd=root, input=data, capture_output=True, env=env, timeout=10)
        if result.returncode:
            raise ExternalTemporaryError("synthetic Git failure")
        return result.stdout


@pytest.fixture
def store(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    transport = LocalTransport(remote)
    transport.run(remote, ["init", "--bare", "--template=", "."])
    blob = transport.run(remote, ["hash-object", "-w", "--stdin"], b"retained legacy evidence").strip().decode()
    transport.run(remote, ["update-index", "--add", "--cacheinfo", "100644", blob, "legacy-evidence.txt"])
    tree = transport.run(remote, ["write-tree"]).strip().decode()
    commit = transport.run(remote, ["commit-tree", tree], b"synthetic initial\n").strip().decode()
    transport.run(remote, ["update-ref", REF, commit])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return GitBackupStore(transport, workspace), commit


def pair(tmp_path, number=1):
    identity = f"20260917T0000{number:02d}000000-" + f"{number:032x}"
    payload = BACKUP_HEADER + Fernet(Fernet.generate_key()).encrypt(b"synthetic SQL only")
    checksum = hashlib.sha256(payload).hexdigest()
    metadata = dict(identity=identity, sha256=checksum, key_id="synthetic-key",
                    release="r-0123456789abcdef-0123456789abcdef", schema=5,
                    timestamp=datetime.now(timezone.utc).isoformat())
    artifact = tmp_path / (identity + ".enc")
    artifact.write_bytes(payload)
    artifact.with_suffix(".json").write_text(json.dumps(metadata))
    return artifact, checksum, identity


def test_publish_readback_download_keeps_legacy_and_ancestry(store, tmp_path):
    item, previous = store
    artifact, checksum, identity = pair(tmp_path)
    result = item.publish(artifact, checksum, identity)
    assert result["active_points"] == 1
    remote = item.transport.remote
    assert item.command(remote, "rev-parse", REF + "^").strip().decode() == previous
    assert item.command(remote, "show", REF + ":legacy-evidence.txt") == b"retained legacy evidence"
    downloaded = tmp_path / "downloaded"
    assert item.download(identity, downloaded)["sha256"] == checksum
    assert (downloaded / artifact.name).read_bytes() == artifact.read_bytes()
    # Retry reads the same immutable identity without producing another commit.
    assert item.publish(artifact, checksum, identity)["commit"] == result["commit"]
    with pytest.raises(ConflictError):
        item.download(identity, downloaded)


@pytest.mark.parametrize("fault", ["plaintext", "digest", "extra_metadata", "identity", "schema"])
def test_invalid_input_never_contacts_remote(store, tmp_path, fault):
    item, _ = store
    artifact, checksum, identity = pair(tmp_path)
    metadata = json.loads(artifact.with_suffix(".json").read_text())
    if fault == "plaintext":
        artifact.write_bytes(b"BEGIN TRANSACTION; synthetic SQL; COMMIT;")
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        metadata["sha256"] = checksum
    elif fault == "digest":
        checksum = "0" * 64
    elif fault == "extra_metadata":
        metadata["unexpected_content"] = "must not upload"
    elif fault == "identity":
        metadata["identity"] = "different"
    else:
        metadata["schema"] = 0
    artifact.with_suffix(".json").write_text(json.dumps(metadata))
    before = len(item.transport.calls)
    with pytest.raises(DataIntegrityError):
        item.publish(artifact, checksum, identity)
    assert len(item.transport.calls) == before


def test_non_fast_forward_or_permission_failure_does_not_retry(store, tmp_path):
    item, previous = store
    artifact, checksum, identity = pair(tmp_path)
    item.transport.reject_push = True
    with pytest.raises(ExternalTemporaryError):
        item.publish(artifact, checksum, identity)
    assert item.command(item.transport.remote, "rev-parse", REF).strip().decode() == previous
    assert sum(call[0] == "push" for call in item.transport.calls) == 1


def test_uncertain_readback_is_failure_even_if_remote_commit_exists(store, tmp_path):
    item, _ = store
    artifact, checksum, identity = pair(tmp_path)
    item.transport.failed_readback = True
    with pytest.raises(ExternalTemporaryError):
        item.publish(artifact, checksum, identity)
    item.transport.failed_readback = False
    assert item.publish(artifact, checksum, identity)["active_points"] == 1


def test_identity_collision_is_not_overwritten(store, tmp_path):
    item, _ = store
    artifact, checksum, identity = pair(tmp_path)
    item.publish(artifact, checksum, identity)
    artifact, checksum, identity = pair(tmp_path)
    with pytest.raises(ConflictError):
        item.publish(artifact, checksum, identity)


def test_retention_current_tree_bounded_but_history_retained(store, tmp_path):
    item, _ = store
    first = None
    for number in range(1, 10):
        artifact, checksum, identity = pair(tmp_path, number)
        first = first or identity
        result = item.publish(artifact, checksum, identity)
    assert result["active_points"] == 8
    tree = item.tree(item.transport.remote, result["commit"])
    assert PREFIX + first + ".enc" not in tree
    previous = item.command(item.transport.remote, "rev-parse", REF + "^").strip().decode()
    assert PREFIX + first + ".enc" in item.tree(item.transport.remote, previous)


def test_retention_keeps_daily_points_beyond_latest_eight():
    identities = {f"202609{day:02d}T000000000000-" + f"{day:032x}" for day in range(1, 18)}
    identities |= {f"20260917T01{minute:02d}00000000-" + f"{minute + 100:032x}" for minute in range(12)}
    keep = retained(identities)
    assert len(keep) == 14
    assert {value[:8] for value in keep} == {f"202609{day:02d}" for day in range(11, 18)}
