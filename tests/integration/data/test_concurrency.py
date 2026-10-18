"""CF-07/14/20/21: barrier-driven data failures, never operational data."""

import asyncio
import sqlite3
import threading
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.platform.errors import CapacityError, ConflictError, DatabaseUnavailableError, DeadlineExceededError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


def request(seconds=5):
    return DatabaseRequest.within(seconds, "synthetic-concurrency")


@pytest.mark.asyncio
async def test_busy_writer_keeps_event_loop_and_read_lane_alive(database):
    with closing(sqlite3.connect(database.config.path, isolation_level=None)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        repo = SqliteEngagementRepository(database)
        blocked = asyncio.create_task(repo.add_progress(100, 10, 1, 0, request()))
        read = await repo.get_member(100, 10, request())
        assert read.xp == 31
        with pytest.raises(DatabaseUnavailableError) as failure:
            await blocked
        assert failure.value.context["sqlite_code"] == sqlite3.SQLITE_BUSY
        lock.rollback()
    assert (await repo.get_member(100, 10, request())).xp == 31
    assert any(obs.result == "database_unavailable" for obs in database.observations)


@pytest.mark.asyncio
async def test_queue_saturation_waiting_cancellation_and_running_capacity(legacy_db):
    db = SqliteDatabase(DatabaseConfig(legacy_db, queue_capacity=1))
    await db.start()
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    called = False
    def hold(conn):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    def queued(conn):
        nonlocal called
        called = True
    first = asyncio.create_task(db.write(request(), hold))
    second = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        second = asyncio.create_task(db.write(request(), queued))
        await asyncio.sleep(0)  # Hand over exactly once to admission; no race sleep.
        assert db.admitted[1] == 2
        with pytest.raises(CapacityError):
            await db.write(request(), queued)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert db.admitted[1] >= 1  # Running thread retains its capacity.
    finally:
        release.set()
        await asyncio.gather(first, *( [second] if second else []), return_exceptions=True)
        await db.stop()
    assert not called and db.admitted == (0, 0)
    assert any(obs.result == "cancelled" for obs in db.observations)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_cancel_or_deadline_before_commit_rolls_back_and_is_observed(database, cancel):
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def mutation(conn):
        conn.execute("UPDATE users SET xp=xp+1000 WHERE guild_id=100")
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
    task = asyncio.create_task(database.write(request(5 if cancel else 0.1), mutation))
    try:
        await asyncio.wait_for(started.wait(), 2)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else DeadlineExceededError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    # Same writer lane is a deterministic barrier after the cancelled worker.
    await database.write(request(), lambda conn: None)
    assert (await SqliteEngagementRepository(database).get_member(100, 10, request())).xp == 31
    assert any(obs.phase == "worker_finished" and obs.result == "cancellation" for obs in database.observations)


@pytest.mark.asyncio
async def test_sqlite_progress_handler_interrupts_long_query(database):
    def expensive(conn):
        return conn.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000000) SELECT sum(x) FROM n").fetchone()
    with pytest.raises(DeadlineExceededError):
        await database.read(request(0.03), expensive)
    assert await database.read(request(), lambda conn: conn.execute("SELECT 1").fetchone()) == (1,)


@pytest.mark.asyncio
async def test_snapshot_during_atomic_cross_table_write_is_one_point_in_time(database, tmp_path, monkeypatch):
    from discordbot.storage.adapters import recovery
    real_snapshot = recovery.snapshot
    pinned = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def snapshot_with_barrier(source, destination, control, **kwargs):
        seen = False
        def progress(status, remaining, total):
            nonlocal seen
            if not seen:
                seen = True
                loop.call_soon_threadsafe(pinned.set)
                assert release.wait(3)
        return real_snapshot(source, destination, control, progress, **kwargs)
    monkeypatch.setattr(recovery, "snapshot", snapshot_with_barrier)
    key = Fernet.generate_key()
    backup = tmp_path / "concurrent.sql"
    task = asyncio.create_task(DataRecovery(database).backup(backup, key, request()))
    try:
        await asyncio.wait_for(pinned.wait(), 2)
        def write_pair(conn):
            conn.execute("UPDATE users SET xp=999 WHERE guild_id=100")
            conn.execute("UPDATE music_play_counts SET play_count=999 WHERE guild_id=100")
        await database.write(request(), write_pair)
    finally:
        release.set()
    await task
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    try:
        restored = tmp_path / "restored.db"
        await DataRecovery(worker).restore_copy(RecoveryCandidate(backup, key), restored, request())
        with closing(sqlite3.connect(restored)) as conn:
            assert conn.execute("SELECT xp FROM users WHERE guild_id=100").fetchone() == (31,)
            assert conn.execute("SELECT max(play_count) FROM music_play_counts WHERE guild_id=100").fetchone() == (60,)
        assert (await SqliteEngagementRepository(database).get_member(100, 10, request())).xp == 999
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_shutdown_closes_both_lanes_and_rejects_admission(legacy_db):
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    await db.start()
    await db.stop()
    with pytest.raises(ConflictError):
        await db.read(request(), lambda conn: None)
    assert db.admitted == (0, 0)
