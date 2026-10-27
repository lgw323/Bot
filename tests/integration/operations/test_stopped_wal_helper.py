"""Temporary synthetic fixtures only; no service/host adapter or canonical data."""
from contextlib import closing
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

import pytest
import pytest_asyncio

from discordbot.operations.adapters.filesystem import ExclusiveLock
from discordbot.platform.errors import ConflictError
from discordbot.storage.adapters.execution import SqliteDatabase, WorkControl
from discordbot.storage.adapters.recovery import DataRecovery, snapshot
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("stopped_wal_helper", ROOT / "deploy/tools/stopped_wal.py")
wal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wal
SPEC.loader.exec_module(wal)


def sql(path, statement):
    with closing(sqlite3.connect(path, isolation_level=None, timeout=0.1)) as conn:
        return conn.execute(statement).fetchall()


@pytest_asyncio.fixture
async def request_pair(tmp_path):
    path = tmp_path / "latest.db"
    database = SqliteDatabase(DatabaseConfig(path))
    try:
        await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    finally:
        await database.stop()
    sql(path, "PRAGMA journal_mode=DELETE")
    sql(path, "INSERT INTO users(user_id,guild_id,xp,level) VALUES(1,1,21,1)")
    reference = tmp_path / "final-restored.db"
    snapshot(path, reference, WorkControl(DatabaseRequest.within(5)))
    return wal.Request(path, tmp_path / "operations.lock", reference, wal.checksum(reference),
                       tmp_path / "originals", tmp_path / "receipt.jsonl", seconds=5)


def observer(request, **overrides):
    def observe(target, deadline):
        return replace(wal.StopEvidence(request.database, request.operation_lock, "synthetic-owned-epoch",
                                        time.monotonic() + 2, True,
                                        {"discord-bot": ("inactive", "success", 0),
                                         "watch-web": ("inactive", "success", 0)}), **overrides)
    return observe


def execute(request, observe=None):
    with wal.OperationOwner(request.operation_lock, observe or observer(request)) as owner:
        return wal.normalize(request, owner)


def failure(request, observe=None):
    with pytest.raises(wal.NormalizationFailed) as caught:
        execute(request, observe)
    return caught.value.receipt


@pytest.mark.asyncio
async def test_delete_to_wal_preserves_latest_and_originals(request_pair):
    request = request_pair
    before = wal.inventory(request.database)
    original = request.database.read_bytes()
    restored = request.final_restore.read_bytes()
    result = execute(request)
    assert result["outcome"] == "verified" and result["receipt_persisted"]
    assert result["semantic_before"] == result["semantic_after"] == result["reference"]
    assert result["after"][""]["identity"] == before[""]["identity"]
    assert result["after"]["header_mode"] == [2, 2]
    assert result["after"][""]["sha256"] != before[""]["sha256"]
    assert all(result["after"][s] is None for s in wal.SIDECARS)
    assert sql(request.database, "SELECT xp FROM users") == [(21,)]
    assert (request.preservation / "original.db").read_bytes() == original
    assert request.final_restore.read_bytes() == restored
    assert wal.inventory(request.final_restore)["header_mode"] == [1, 1]
    records = [json.loads(line) for line in request.receipt.read_text().splitlines()]
    assert [record["event"] for record in records] == ["admitted", "before_sqlite_access", "wal_returned", "complete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["absent", "unentered", "released", "wrong_lock"])
async def test_missing_real_ownership_refuses_without_target_access(request_pair, case):
    request = request_pair
    before = wal.inventory(request.database)
    owner = None if case == "absent" else wal.OperationOwner(request.operation_lock, observer(request))
    if case == "released":
        with owner:
            pass
    if case == "wrong_lock":
        owner = wal.OperationOwner(request.operation_lock.with_name("other.lock"), observer(request))
        owner.__enter__()
    try:
        with pytest.raises(wal.NormalizationFailed) as caught:
            wal.normalize(request, owner)
    finally:
        if owner is not None and owner.held:
            owner.__exit__(None, None, None)
    assert caught.value.receipt["outcome"] == "refused"
    assert not caught.value.receipt["target_access_started"]
    assert wal.inventory(request.database) == before
    assert not request.receipt.exists() and not request.preservation.exists()


@pytest.mark.asyncio
async def test_actual_operation_lock_contention(request_pair):
    request = request_pair
    before = wal.inventory(request.database)
    with ExclusiveLock(request.operation_lock).acquire():
        with pytest.raises(ConflictError):
            execute(request)
    assert wal.inventory(request.database) == before and not request.receipt.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"consumers_excluded": False}, {"valid_until": 0}, {"epoch": ""}, {"services": {}},
    {"services": {"discord-bot": ("active", "success", 33), "watch-web": ("inactive", "success", 0)}},
    {"services": {"discord-bot": ("inactive", "success", 33), "watch-web": ("inactive", "success", 0)}},
    {"services": {"discord-bot": ("inactive", "exit-code", 0), "watch-web": ("inactive", "success", 0)}},
    {"target": Path("/wrong")}, {"operation_lock": Path("/wrong")},
])
async def test_unconfirmed_stopped_consumers_refuse(request_pair, change):
    before = wal.inventory(request_pair.database)
    result = failure(request_pair, observer(request_pair, **change))
    assert result["outcome"] == "refused" and not result["target_access_started"]
    assert wal.inventory(request_pair.database) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", wal.SIDECARS)
async def test_delete_sidecar_refused_and_preserved(request_pair, suffix):
    sidecar = Path(str(request_pair.database) + suffix)
    sidecar.write_bytes(b"synthetic-not-owned")
    before = wal.inventory(request_pair.database)
    result = failure(request_pair)
    assert result["outcome"] == "refused" and wal.inventory(request_pair.database) == before
    assert sidecar.read_bytes() == b"synthetic-not-owned"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["hash", "old_backup", "existing_preservation", "existing_receipt", "reference_sidecar", "alias", "relative", "deadline"])
async def test_invalid_preconditions_do_not_switch_mode(request_pair, case):
    request = request_pair
    if case == "hash":
        request = replace(request, restore_sha256="0" * 64)
    elif case == "old_backup":
        sql(request.final_restore, "UPDATE users SET xp=10")
        request = replace(request, restore_sha256=wal.checksum(request.final_restore))
    elif case == "existing_preservation":
        request.preservation.mkdir()
    elif case == "existing_receipt":
        request.receipt.write_text("keep")
    elif case == "reference_sidecar":
        Path(str(request.final_restore) + "-wal").write_bytes(b"keep")
    elif case == "alias":
        request = replace(request, receipt=Path(str(request.final_restore) + "-wal"))
    elif case == "relative":
        request = replace(request, database=Path("relative.db"))
    elif case == "deadline":
        request = replace(request, seconds=61)
    before = wal.inventory(request_pair.database)
    result = failure(request)
    assert result["outcome"] != "verified"
    assert wal.inventory(request_pair.database) == before
    assert sql(request_pair.database, "SELECT xp FROM users") == [(21,)]


@pytest.mark.asyncio
@pytest.mark.parametrize("when", [2, 3, 4])
async def test_lease_loss_at_rechecks_prevents_success(request_pair, when):
    calls = 0
    good = observer(request_pair)
    def observe(target, deadline):
        nonlocal calls
        calls += 1
        return replace(good(target, deadline), epoch="lost" if calls >= when else "first")
    result = failure(request_pair, observe)
    assert result["outcome"] != "verified" and calls == when
    assert sql(request_pair.database, "SELECT xp FROM users") == [(21,)]
    if when == 4:
        assert result["outcome"] == "failed_after_target_access"
        assert result["after"]["header_mode"] == [2, 2]
    else:
        assert result["after"]["header_mode"] == [1, 1]


@pytest.mark.asyncio
async def test_actual_backup_residue_uses_sqlite_cleanup_only(request_pair, monkeypatch):
    request = request_pair
    sql(request.database, "PRAGMA journal_mode=WAL")
    with closing(sqlite3.connect(request.database.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("SELECT * FROM users").fetchall()
    assert Path(str(request.database) + "-wal").exists()
    before = wal.inventory(request.database)
    def forbidden(*args, **kwargs):
        raise AssertionError("manual filesystem removal forbidden")
    monkeypatch.setattr(Path, "unlink", forbidden)
    monkeypatch.setattr(wal.os, "unlink", forbidden)
    monkeypatch.setattr(wal.os, "remove", forbidden)
    result = execute(request)
    assert result["outcome"] == "verified"
    for suffix in ("", *wal.SIDECARS):
        if before[suffix] is not None:
            assert wal.checksum(request.preservation / ("original.db" + suffix)) == before[suffix]["sha256"]
    assert all(result["after"][suffix] is None for suffix in wal.SIDECARS)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["reader", "writer", "wal_writer", "wal_committed_keeper"])
async def test_real_held_sqlite_connections_block_success(request_pair, mode):
    request = request_pair
    if mode.startswith("wal"):
        sql(request.database, "PRAGMA journal_mode=WAL")
    with closing(sqlite3.connect(request.database, isolation_level=None, timeout=0.1)) as holder:
        if mode == "reader":
            holder.execute("BEGIN")
            holder.execute("SELECT xp FROM users").fetchall()
        elif mode == "wal_committed_keeper":
            holder.execute("UPDATE users SET xp=21")
        else:
            holder.execute("BEGIN IMMEDIATE")
            holder.execute("UPDATE users SET xp=999")
        result = failure(request)
        assert result["outcome"] != "verified"
        if holder.in_transaction:
            holder.rollback()
    assert sql(request.database, "SELECT xp FROM users") == [(21,)]


@pytest.mark.asyncio
async def test_latest_commit_in_wal_is_preserved_not_old_main(request_pair):
    request = request_pair
    sql(request.database, "PRAGMA journal_mode=WAL")
    # Keep WAL resident, snapshot the latest committed state, then close the writer
    # while a readonly holder prevents SQLite's automatic final cleanup.
    with closing(sqlite3.connect(request.database, isolation_level=None)) as writer:
        writer.execute("UPDATE users SET xp=123")
        reader = sqlite3.connect(request.database.as_uri() + "?mode=ro", uri=True)
        reader.execute("SELECT xp FROM users").fetchall()
        latest = request.final_restore.with_name("new-final-restored.db")
        snapshot(request.database, latest, WorkControl(DatabaseRequest.within(5)))
    reader.close()
    request = replace(request, final_restore=latest, restore_sha256=wal.checksum(latest))
    assert wal.inventory(request.database)["-wal"]["size"] > 0
    result = execute(request)
    assert result["outcome"] == "verified" and sql(request.database, "SELECT xp FROM users") == [(123,)]
    assert result["semantic_before"] == result["semantic_after"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["wal_returned", "complete", "receipt_unavailable"])
async def test_post_change_failure_reports_already_changed(request_pair, monkeypatch, stage):
    real = wal.append_receipt
    def append(stream, value):
        if value["event"] == ("wal_returned" if stage == "receipt_unavailable" else stage):
            raise OSError("synthetic-receipt-fault")
        if stage == "receipt_unavailable" and value["event"] == "failed":
            raise OSError("synthetic-second-receipt-fault")
        return real(stream, value)
    monkeypatch.setattr(wal, "append_receipt", append)
    result = failure(request_pair)
    assert result["outcome"] == "failed_after_target_access"
    assert result["wal_returned"] and result["after"]["header_mode"] == [2, 2]
    assert result["semantic_before"] == result["reference"]
    assert result["receipt_persisted"] == (stage != "receipt_unavailable")
    assert sql(request_pair.database, "SELECT xp FROM users") == [(21,)]
    assert wal.inventory(request_pair.final_restore)["header_mode"] == [1, 1]


@pytest.mark.asyncio
async def test_integrity_failure_is_not_misreported_as_success(request_pair, monkeypatch):
    real = wal.semantic
    def bad(path, deadline, **kwargs):
        if path == request_pair.database:
            raise wal.Refused("synthetic integrity failure")
        return real(path, deadline, **kwargs)
    monkeypatch.setattr(wal, "semantic", bad)
    result = failure(request_pair)
    assert result["outcome"] == "failed_after_target_access" and "wal_returned" not in result
    assert result["after"]["header_mode"] == [1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["permission", "observer", "preservation_sync", "final_sync", "receipt_close"])
async def test_io_errors_have_honest_before_after_receipts(request_pair, monkeypatch, case):
    request = request_pair
    real_inventory = wal.inventory
    real_sync = wal.sync_directory
    def fail(*args, **kwargs):
        raise PermissionError("synthetic permission refusal")
    if case == "permission":
        monkeypatch.setattr(wal, "connect", fail)
    elif case == "observer":
        result = failure(request, fail)
        assert result["outcome"] == "refused" and not result["target_access_started"]
        return
    elif case in {"preservation_sync", "final_sync"}:
        calls = 0
        def sync(path):
            nonlocal calls
            calls += 1
            # Receipt-parent, preservation-dir, preservation-parent, target-parent.
            if calls == (2 if case == "preservation_sync" else 4):
                raise OSError("synthetic directory sync failure")
            return real_sync(path)
        monkeypatch.setattr(wal, "sync_directory", sync)
    else:
        def close(stream):
            stream.close()
            raise OSError("synthetic close error after close")
        monkeypatch.setattr(wal, "close_receipt", close)
    result = failure(request)
    assert result["outcome"] != "verified" and result["before"] and result["after"]
    assert result["after"] == real_inventory(request.database)
    if case in {"final_sync", "receipt_close"}:
        assert result["outcome"] == "failed_after_target_access"
        assert result["after"]["header_mode"] == [2, 2]
    else:
        assert result["after"]["header_mode"] == [1, 1]
    if case == "receipt_close":
        assert not result["receipt_persisted"] and result["receipt_error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_wal_repeat_is_idempotent_and_keeps_new_receipts(request_pair):
    first = execute(request_pair)
    second = replace(request_pair, preservation=request_pair.preservation.with_name("originals-2"),
                     receipt=request_pair.receipt.with_name("receipt-2.jsonl"))
    result = execute(second)
    assert result["outcome"] == "verified"
    assert first["semantic_after"] == result["semantic_after"]
    assert first["after"] == result["after"]
