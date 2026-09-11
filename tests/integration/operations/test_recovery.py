import errno
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.filesystem import digest, read_json, atomic_json
from discordbot.operations.adapters.recovery import Backups, promote
from discordbot.platform.errors import ConflictError, DataIntegrityError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER


@pytest_asyncio.fixture
async def backup(tmp_path):
    for name in ("backups", "audit"):
        (tmp_path / name).mkdir()
    db = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="test-operations")
    await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    await db.start()
    item = Backups(db, tmp_path / "backups", Fernet.generate_key(), "synthetic-key", executor, Audit(tmp_path / "audit"))
    try:
        yield item
    finally:
        await db.stop()
        await executor.close(grace_seconds=5)


@pytest.mark.asyncio
async def test_newest_valid_and_corrupt_latest_fallback(backup, tmp_path):
    first = await backup.create("release1")
    second = await backup.create("release2")
    assert await backup.restore(tmp_path / "newest.db", "release2", candidates=(second, first)) == second
    (backup.root / (second + ".enc")).write_bytes(b"partial")
    assert await backup.restore(tmp_path / "fallback.db", "release2", candidates=(second, first)) == first
    assert read_json(backup.root / "latest.json")["identity"] == second


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["wrong_key", "tamper", "schema", "partial_metadata"])
async def test_invalid_backup_never_overwrites_live(backup, tmp_path, fault):
    identity = await backup.create("release")
    if fault == "wrong_key":
        backup.key = Fernet.generate_key()
    elif fault == "tamper":
        path = backup.root / (identity + ".enc")
        data = path.read_bytes()
        path.write_bytes(data[:-8] + b"tampered")
        record = read_json(backup.root / (identity + ".json"))
        record["sha256"] = digest(path)
        atomic_json(backup.root / (identity + ".json"), record)
    elif fault == "schema":
        record = read_json(backup.root / (identity + ".json"))
        record["schema"] = 99
        atomic_json(backup.root / (identity + ".json"), record)
    else:
        (backup.root / (identity + ".json")).write_text("{")
    before = digest(backup.database.config.path)
    with pytest.raises(DataIntegrityError):
        await backup.restore(tmp_path / "rehearsal.db", "release")
    assert digest(backup.database.config.path) == before
    assert not (tmp_path / "rehearsal.db").exists()


@pytest.mark.asyncio
async def test_remote_failure_keeps_last_good_latest(backup):
    first = await backup.create("release")
    class Remote:
        async def publish(self, *args): raise OSError("unavailable")
    backup.remote = Remote()
    with pytest.raises(OSError): await backup.create("release")
    assert read_json(backup.root / "latest.json")["identity"] == first


@pytest.mark.asyncio
async def test_semantically_invalid_encrypted_latest_falls_back(backup, tmp_path):
    first = await backup.create("release")
    second = await backup.create("release")
    path = backup.root / (second + ".enc")
    cipher = Fernet(backup.key)
    sql = cipher.decrypt(path.read_bytes()[len(BACKUP_HEADER):]).decode()
    sql = sql.replace("COMMIT;", "INSERT INTO users(guild_id,user_id,xp) VALUES(1,2,-1);\nCOMMIT;")
    path.write_bytes(BACKUP_HEADER + cipher.encrypt(sql.encode()))
    record = read_json(backup.root / (second + ".json"))
    record["sha256"] = digest(path)
    atomic_json(backup.root / (second + ".json"), record)
    assert await backup.restore(tmp_path / "good.db", "release", candidates=(second, first)) == first


@pytest.mark.asyncio
async def test_cancelled_restore_never_promotes_or_leaves_plaintext_temp(backup, tmp_path, monkeypatch):
    await backup.create("release")
    async def cancel(*args, **kwargs): raise asyncio.CancelledError
    monkeypatch.setattr(DataRecovery, "restore_copy", cancel)
    with pytest.raises(asyncio.CancelledError):
        await backup.restore(tmp_path / "candidate.db", "release")
    assert not (tmp_path / "candidate.db").exists()
    assert not list(tmp_path.glob(".rehearsal-*"))


@pytest.mark.asyncio
async def test_backup_retention_keeps_bounded_verified_alternatives(backup):
    for _ in range(10):
        await backup.create("release")
    assert len(backup.candidates()) == 8
    assert len(list(backup.root.glob("*.enc"))) == 8


@pytest.mark.asyncio
async def test_backup_audit_failure_preserves_previous_latest(backup, monkeypatch):
    first = await backup.create("release")
    def fail(*args): raise OSError("audit full")
    monkeypatch.setattr(backup.audit, "write", fail)
    with pytest.raises(OSError): await backup.create("release")
    assert read_json(backup.root / "latest.json")["identity"] == first


@pytest.mark.asyncio
async def test_explicit_promotion_requires_quiescence_and_unchanged_candidate(backup, tmp_path):
    await backup.create("release")
    candidate = tmp_path / "candidate.db"
    await backup.restore(candidate, "release")
    live = tmp_path / "offline-live.db"
    live.write_bytes(b"prior")
    with pytest.raises(ConflictError):
        promote(candidate, live, digest(candidate), stopped=False, audit=backup.audit, release="release")
    promote(candidate, live, digest(candidate), stopped=True, audit=backup.audit, release="release")
    assert digest(live) == digest(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [errno.ENOSPC, errno.EACCES])
async def test_promotion_atomic_failure_preserves_previous(backup, tmp_path, monkeypatch, error):
    await backup.create("release")
    candidate = tmp_path / "candidate.db"
    await backup.restore(candidate, "release")
    live = tmp_path / "offline-live.db"
    live.write_bytes(b"prior")
    replace = __import__("os").replace
    def fail(source, destination):
        if destination == live:
            raise OSError(error, "injected")
        replace(source, destination)
    monkeypatch.setattr("discordbot.operations.adapters.recovery.os.replace", fail)
    with pytest.raises(OSError):
        promote(candidate, live, digest(candidate), stopped=True, audit=backup.audit, release="release")
    assert live.read_bytes() == b"prior" and not list(tmp_path.glob(".restore-*"))
