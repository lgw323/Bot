"""A8-M2: synthetic encrypted archives must earn the recovery retention floor."""

import asyncio
import errno
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from discordbot.operations.adapters import recovery
from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
from discordbot.platform.errors import ConflictError, DataIntegrityError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER
from tests.integration.operations.test_recovery import backup


async def failed_publication(backup) -> str:
    before = set(backup.root.glob("*.enc"))

    class Remote:
        async def publish(self, *args) -> None:
            raise OSError("synthetic remote failure")

    backup.remote = Remote()
    try:
        with pytest.raises(OSError, match="synthetic remote failure"):
            await backup.create("synthetic-release")
    finally:
        backup.remote = None
    created = set(backup.root.glob("*.enc")) - before
    assert len(created) == 1
    return created.pop().stem


def corrupt(backup, identity: str, fault: str) -> None:
    artifact = backup.root / (identity + ".enc")
    metadata = backup.root / (identity + ".json")
    record = read_json(metadata)
    if fault == "missing":
        artifact.unlink()
    elif fault == "metadata":
        metadata.write_text("{", encoding="utf-8")
        return
    elif fault in {"identity", "key_id", "schema", "sha256"}:
        record[fault] = 99 if fault == "schema" else "incorrect"
    elif fault == "ciphertext":
        artifact.write_bytes(b"synthetic corrupt ciphertext")
    elif fault == "authentication":
        artifact.write_bytes(BACKUP_HEADER + Fernet(Fernet.generate_key()).encrypt(b"invalid"))
        record["sha256"] = digest(artifact)
    elif fault in {"semantic", "ledger"}:
        cipher = Fernet(backup.key)
        sql = cipher.decrypt(artifact.read_bytes()[len(BACKUP_HEADER):]).decode()
        if fault == "semantic":
            sql = sql.replace("COMMIT;", "INSERT INTO users(guild_id,user_id,xp) VALUES(1,2,-1);\nCOMMIT;")
        else:
            sql = "BEGIN TRANSACTION;\nCREATE TABLE users (guild_id INTEGER);\nCOMMIT;\n"
        artifact.write_bytes(BACKUP_HEADER + cipher.encrypt(sql.encode()))
        record["sha256"] = digest(artifact)
    else:
        raise AssertionError(fault)
    atomic_json(metadata, record)


def archives(backup) -> set[str]:
    return {p.stem for p in backup.root.glob("*.enc")}


def assert_no_plaintext(backup) -> None:
    assert all(p.suffix in {".enc", ".json"} for p in backup.root.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "metadata", "identity", "key_id", "schema", "sha256",
                                 "ciphertext", "authentication", "semantic", "ledger"])
async def test_invalid_records_never_count_as_recoverable(backup, tmp_path, fault):
    valid = [await backup.create("synthetic-release") for _ in range(8)]
    orphan = await failed_publication(backup)
    corrupt(backup, orphan, fault)
    with pytest.raises(DataIntegrityError):
        await backup.restore(tmp_path / "rejected.db", "synthetic-release", candidates=(orphan,))
    newest = await backup.create("synthetic-release")
    assert set(valid[1:]) | {newest} <= archives(backup)
    assert valid[0] not in archives(backup)
    for index, identity in enumerate(valid[1:] + [newest]):
        assert await backup.restore(tmp_path / f"valid-{index}.db", "synthetic-release",
                                    candidates=(identity,)) == identity
    assert_no_plaintext(backup)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 7, 8, 9, 10])
async def test_valid_only_retention_boundaries(backup, tmp_path, count):
    created = [await backup.create("synthetic-release") for _ in range(count)]
    assert archives(backup) == set(created[-8:])
    for index, identity in enumerate(created[-8:]):
        assert await backup.restore(tmp_path / f"valid-{index}.db", "synthetic-release",
                                    candidates=(identity,)) == identity
    assert_no_plaintext(backup)


@pytest.mark.asyncio
async def test_recoverable_failed_publications_keep_prior_latest_and_filename_order(backup, tmp_path):
    previous = await backup.create("synthetic-release")
    orphans = [await failed_publication(backup) for _ in range(9)]
    # Metadata timestamps/mtime deliberately disagree with the established ID order.
    for index, identity in enumerate(orphans):
        record = read_json(backup.root / (identity + ".json"))
        record["timestamp"] = f"2000-01-{20-index:02}T00:00:00+00:00"
        atomic_json(backup.root / (identity + ".json"), record)
        os.utime(backup.root / (identity + ".json"), (1000 - index, 1000 - index))
    newest = await backup.create("synthetic-release")
    assert archives(backup) == {previous, newest, *orphans[-7:]}
    assert read_json(backup.root / "latest.json")["identity"] == newest
    for index, identity in enumerate(sorted(archives(backup))):
        assert await backup.restore(tmp_path / f"kept-{index}.db", "synthetic-release",
                                    candidates=(identity,)) == identity


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["remote", "success_audit", "latest_replace", "validation_io", "cancel", "corrupt_new"])
async def test_failure_before_latest_preserves_pointer_and_all_prior_archives(backup, monkeypatch, fault):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    pointer = (backup.root / "latest.json").read_bytes()
    old_bytes = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    error = asyncio.CancelledError if fault == "cancel" else DataIntegrityError if fault == "corrupt_new" else OSError
    if fault in {"remote", "corrupt_new"}:
        class Remote:
            async def publish(self, artifact, *args):
                if fault == "remote":
                    raise OSError("synthetic failure")
                artifact.write_bytes(b"synthetic corrupt publication")
        backup.remote = Remote()
    elif fault == "success_audit":
        original = backup.audit.write
        def audit(operation, release, result, reason):
            if result == "ok":
                raise OSError("synthetic success audit failure")
            return original(operation, release, result, reason)
        monkeypatch.setattr(backup.audit, "write", audit)
    elif fault == "latest_replace":
        original = recovery.os.replace
        def replace(source, destination):
            if destination == backup.root / "latest.json":
                raise OSError("synthetic pointer failure")
            return original(source, destination)
        monkeypatch.setattr(recovery.os, "replace", replace)
    else:
        original = recovery.DataRecovery.restore_copy
        async def validate(self, candidate, *args, **kwargs):
            # The snapshot's own verification stays real; fail retention verification.
            if candidate.path.stem == prior[0]:
                if fault == "cancel":
                    raise asyncio.CancelledError
                raise PermissionError(errno.EACCES, "synthetic validation failure")
            return await original(self, candidate, *args, **kwargs)
        monkeypatch.setattr(recovery.DataRecovery, "restore_copy", validate)
    with pytest.raises(error):
        await backup.create("synthetic-release")
    assert (backup.root / "latest.json").read_bytes() == pointer
    for name, data in old_bytes.items():
        assert (backup.root / name).read_bytes() == data
    assert_no_plaintext(backup)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 8])
async def test_direct_retention_is_idempotent_and_protects_old_latest(backup, count):
    latest = await backup.create("synthetic-release")
    orphans = [await failed_publication(backup) for _ in range(9)]
    corrupt(backup, orphans[-1], "semantic")
    expected = {latest, *orphans[-(count + 1):]}
    await backup.retain(count)
    assert archives(backup) == expected
    before = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    await backup.retain(count)
    assert {p.name: p.read_bytes() for p in backup.root.iterdir()} == before
    assert_no_plaintext(backup)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 33])
async def test_invalid_retention_count_never_mutates(backup, count):
    await backup.create("synthetic-release")
    before = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    with pytest.raises(ValueError, match="preserve alternatives"):
        await backup.retain(count)
    assert {p.name: p.read_bytes() for p in backup.root.iterdir()} == before


@pytest.mark.asyncio
async def test_clock_regression_cannot_delete_new_legitimate_latest(backup, monkeypatch, tmp_path):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    class OldClock:
        @staticmethod
        def now(zone):
            return datetime(2000, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(recovery, "datetime", OldClock)
    newest = await backup.create("synthetic-release")
    assert newest < min(prior)
    assert archives(backup) == set(prior) | {newest}
    assert read_json(backup.root / "latest.json")["identity"] == newest
    assert await backup.restore(tmp_path / "newest.db", "synthetic-release", candidates=(newest,)) == newest


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "malformed"])
async def test_success_repairs_unusable_pointer_without_losing_valid_floor(backup, fault):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    if fault == "missing":
        (backup.root / "latest.json").unlink()
    else:
        (backup.root / "latest.json").write_bytes(b"{")
    newest = await backup.create("synthetic-release")
    assert archives(backup) == set(prior[1:]) | {newest}
    assert read_json(backup.root / "latest.json")["identity"] == newest


@pytest.mark.asyncio
async def test_old_key_archives_are_preserved_for_operator_reconciliation(backup):
    prior = [await backup.create("synthetic-release") for _ in range(2)]
    backup.key, backup.key_id = Fernet.generate_key(), "synthetic-rotated-key"
    current = [await backup.create("synthetic-release") for _ in range(9)]
    assert archives(backup) == set(prior + current[-8:])
    assert_no_plaintext(backup)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["disk_full", "metadata_permission"])
async def test_validation_operational_fault_propagates_before_any_pruning(backup, monkeypatch, fault):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    before = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    if fault == "disk_full":
        original = recovery.DataRecovery.restore_copy
        async def restore(self, candidate, *args, **kwargs):
            if candidate.path.stem == prior[0]:
                raise OSError(errno.ENOSPC, "synthetic disk full")
            return await original(self, candidate, *args, **kwargs)
        monkeypatch.setattr(recovery.DataRecovery, "restore_copy", restore)
    else:
        original = recovery.read_json
        def read(path, *args):
            if path == backup.root / (prior[0] + ".json"):
                raise PermissionError(errno.EACCES, "synthetic metadata permission")
            return original(path, *args)
        monkeypatch.setattr(recovery, "read_json", read)
    with pytest.raises(OSError):
        await backup.create("synthetic-release")
    for name, data in before.items():
        assert (backup.root / name).read_bytes() == data
    assert_no_plaintext(backup)


@pytest.mark.asyncio
@pytest.mark.parametrize("entries", [64, 65])
async def test_capacity_remains_fail_closed_without_pruning_evidence(backup, entries):
    first = await backup.create("synthetic-release")
    for index in range(entries - 3):
        (backup.root / f"synthetic-orphan-{index}.enc").write_bytes(b"synthetic")
    before = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    if entries == 65:
        with pytest.raises(ConflictError, match="backup artifact capacity"):
            await backup.create("synthetic-release")
    else:
        await backup.create("synthetic-release")
    for name, data in before.items():
        if name != "latest.json":
            assert (backup.root / name).read_bytes() == data
    assert first in archives(backup)


@pytest.mark.asyncio
async def test_delete_failure_leaves_eight_valid_alternatives_and_new_latest(backup, monkeypatch, tmp_path):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == backup.root / (prior[0] + ".enc"):
            raise PermissionError(errno.EACCES, "synthetic retention failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError):
        await backup.create("synthetic-release")
    newest = read_json(backup.root / "latest.json")["identity"]
    assert newest not in prior
    for index, identity in enumerate(prior[1:] + [newest]):
        assert await backup.restore(tmp_path / f"kept-{index}.db", "synthetic-release",
                                    candidates=(identity,)) == identity
    assert_no_plaintext(backup)
