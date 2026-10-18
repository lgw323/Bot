import errno
import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.filesystem import digest, read_json, atomic_json
from discordbot.operations.adapters.recovery import Backups, promote
from discordbot.operations.adapters import recovery as recovery_module
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


async def _promotion_pair(backup: Backups, tmp_path: Path) -> tuple[Path, Path]:
    await backup.create("release")
    candidate = tmp_path / "candidate.db"
    await backup.restore(candidate, "release")
    with closing(sqlite3.connect(candidate, isolation_level=None)) as conn:
        conn.execute("INSERT INTO users VALUES (1,1,10,1,0,NULL,NULL)")
    live = tmp_path / "offline-live.db"
    live.write_bytes(b"prior")
    return candidate, live


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["present", "during_copy"])
async def test_promotion_rejects_latest_writes_in_source_wal(
    backup: Backups, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    with closing(sqlite3.connect(candidate, isolation_level=None)) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchall() == [("wal",)]
    expected = digest(candidate)
    holders: list[sqlite3.Connection] = []
    preserved: dict[Path, bytes] = {}

    def write_latest() -> None:
        conn = sqlite3.connect(candidate, isolation_level=None)
        holders.append(conn)
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE users SET xp=123")
        assert conn.execute("SELECT xp FROM users").fetchone() == (123,)
        assert digest(candidate) == expected  # Latest commit is only in WAL.
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(candidate) + suffix)
            preserved[path] = path.read_bytes()

    original_copy = recovery_module.shutil.copyfileobj

    def copy_then_write(*args, **kwargs) -> None:
        original_copy(*args, **kwargs)
        write_latest()

    try:
        if when == "present":
            write_latest()
        else:
            monkeypatch.setattr(recovery_module.shutil, "copyfileobj", copy_then_write)
        rejected = False
        try:
            promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
        except ConflictError:
            rejected = True
        if not rejected:
            with closing(sqlite3.connect(live)) as copied:
                published = copied.execute("SELECT xp FROM users").fetchone()[0]
            pytest.fail(f"source committed synthetic XP123, but promotion published XP{published}")
        assert preserved and all(path.read_bytes() == value for path, value in preserved.items())
        assert live.read_bytes() == b"prior"
        assert not list(tmp_path.glob(".restore-*"))
    finally:
        for conn in holders:
            conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
async def test_promotion_rejects_source_sidecar_without_changing_files(
    backup: Backups, tmp_path: Path, suffix: str,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    expected = digest(candidate)
    sidecar = Path(str(candidate) + suffix)
    sidecar.write_bytes(b"synthetic-sidecar-preserve")
    with pytest.raises(ConflictError):
        promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
    assert digest(candidate) == expected and sidecar.read_bytes() == b"synthetic-sidecar-preserve"
    assert live.read_bytes() == b"prior" and not list(tmp_path.glob(".restore-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("when", ["after_source_hash", "after_copy", "after_final_source_hash"])
async def test_promotion_rechecks_source_sidecars_before_replacement(
    backup: Backups, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, when: str,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    expected = digest(candidate)
    sidecar = Path(str(candidate) + suffix)
    original_digest, original_copy = recovery_module.digest, recovery_module.shutil.copyfileobj
    source_hashes = 0

    def hash_then_sidecar(path: Path, *args, **kwargs) -> str:
        nonlocal source_hashes
        value = original_digest(path, *args, **kwargs)
        if path == candidate:
            source_hashes += 1
            if source_hashes == (2 if when == "after_final_source_hash" else 1):
                sidecar.write_bytes(b"synthetic-concurrent-sidecar")
        return value

    def copy_then_sidecar(*args, **kwargs) -> None:
        original_copy(*args, **kwargs)
        sidecar.write_bytes(b"synthetic-concurrent-sidecar")

    if when != "after_copy":
        monkeypatch.setattr(recovery_module, "digest", hash_then_sidecar)
    else:
        monkeypatch.setattr(recovery_module.shutil, "copyfileobj", copy_then_sidecar)
    with pytest.raises(ConflictError):
        promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
    assert sidecar.read_bytes() == b"synthetic-concurrent-sidecar"
    assert original_digest(candidate) == expected and live.read_bytes() == b"prior"
    assert not list(tmp_path.glob(".restore-*"))


@pytest.mark.asyncio
async def test_promotion_sidecar_stat_error_is_not_treated_as_absent(
    backup: Backups, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    expected = digest(candidate)
    original = Path.lstat

    def denied(path: Path, *args, **kwargs):
        if path == Path(str(candidate) + "-wal"):
            raise PermissionError("synthetic denied sidecar metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(PermissionError):
        promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
    assert digest(candidate) == expected and live.read_bytes() == b"prior"


@pytest.mark.asyncio
async def test_promotion_rejects_source_changed_after_copy(
    backup: Backups, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    expected = digest(candidate)
    original = recovery_module.shutil.copyfileobj

    def copy_then_write(*args, **kwargs) -> None:
        original(*args, **kwargs)
        with closing(sqlite3.connect(candidate, isolation_level=None)) as conn:
            conn.execute("UPDATE users SET xp=123")

    monkeypatch.setattr(recovery_module.shutil, "copyfileobj", copy_then_write)
    with pytest.raises(DataIntegrityError):
        promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
    with closing(sqlite3.connect(candidate)) as conn:
        assert conn.execute("SELECT xp FROM users").fetchone() == (123,)
    assert live.read_bytes() == b"prior" and not list(tmp_path.glob(".restore-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["directory_sync", "success_audit"])
async def test_promotion_post_replace_failure_may_have_published(
    backup: Backups, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    candidate, live = await _promotion_pair(backup, tmp_path)
    expected = digest(candidate)
    original_audit = backup.audit.write

    def fail_sync(path: Path) -> None:
        raise OSError("synthetic directory sync failure")

    def fail_success(operation: str, release: str, result: str, reason: str) -> None:
        if result == "ok":
            raise OSError("synthetic success audit failure")
        original_audit(operation, release, result, reason)

    if fault == "directory_sync":
        monkeypatch.setattr(recovery_module, "sync_dir", fail_sync)
    else:
        monkeypatch.setattr(backup.audit, "write", fail_success)
    with pytest.raises(OSError):
        promote(candidate, live, expected, stopped=True, audit=backup.audit, release="release")
    assert digest(live) == digest(candidate) == expected
    assert not list(tmp_path.glob(".restore-*"))
