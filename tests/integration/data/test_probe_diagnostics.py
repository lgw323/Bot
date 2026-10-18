"""Synthetic probe boundaries and real cross-process SQLite locks; no live DB."""
import asyncio
from contextlib import closing
import errno
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from discordbot.platform.errors import AppError, DataIntegrityError, DatabaseUnavailableError
from discordbot.storage.adapters import execution
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


def request():
    return DatabaseRequest.within(3, "synthetic-probe")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
@pytest.mark.parametrize("transaction", ["BEGIN", "BEGIN IMMEDIATE", "BEGIN EXCLUSIVE"])
async def test_actual_cross_process_probe_contention(legacy_db, mode, transaction):
    with closing(sqlite3.connect(legacy_db)) as conn:
        assert conn.execute("PRAGMA journal_mode=" + mode).fetchone()[0] == mode.lower()
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    await db.start()
    # A separate process owns the lock; pipe barriers replace race-prone sleeps.
    script = """
import sqlite3, sys
conn=sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute(sys.argv[2])
conn.execute('UPDATE users SET xp=xp WHERE guild_id=100')
print('locked',flush=True)
sys.stdin.readline()
conn.rollback();conn.close()
"""
    child = subprocess.Popen([sys.executable, "-I", "-c", script, str(legacy_db), transaction],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert await asyncio.wait_for(asyncio.to_thread(child.stdout.readline), 5) == "locked\n"
        if mode == "DELETE" and transaction == "BEGIN EXCLUSIVE":
            with pytest.raises(DatabaseUnavailableError) as failed:
                await db.probe(request())
            fields = failed.value.context
            assert fields["sqlite_errorcode"] & 255 == sqlite3.SQLITE_BUSY
            assert fields["sqlite_family"] == "busy"
            assert fields["stage"] == "probe_configure"
            assert fields["connection_opened"] and fields["close_succeeded"]
        else:
            assert await db.probe(request()) == (1,)
    finally:
        child.communicate("release\n", timeout=5)
        assert child.returncode == 0
        await db.stop()


@pytest.mark.asyncio
async def test_legacy_read_already_reports_busy_in_rollback_mode(legacy_db):
    with closing(sqlite3.connect(legacy_db)) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    await db.start()
    try:
        with closing(sqlite3.connect(legacy_db)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            with pytest.raises(DatabaseUnavailableError) as failed:
                await db.read(request(), lambda conn: conn.execute("SELECT 1").fetchone())
            assert failed.value.context["sqlite_code"] == sqlite3.SQLITE_BUSY
            lock.rollback()
        assert await db.read(request(), lambda conn: conn.execute("SELECT 1").fetchone()) == (1,)
    finally:
        await db.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["open", "configure", "begin", "execute", "fetch", "commit", "close"])
@pytest.mark.parametrize("code,family", [(sqlite3.SQLITE_BUSY, "busy"), (sqlite3.SQLITE_LOCKED, "locked"),
                                        (sqlite3.SQLITE_IOERR | (1 << 8), "io"),
                                        (sqlite3.SQLITE_CORRUPT, "corrupt"), (sqlite3.SQLITE_NOTADB, "notadb")])
async def test_probe_failure_boundaries_hide_sensitive_text(database, monkeypatch, boundary, code, family):
    closed = []
    error = sqlite3.OperationalError("private SQL /private/path user-content credential-value")
    error.sqlite_errorcode = code
    error.sqlite_errorname = "private-symbol-must-not-escape"
    def fail(stage):
        if stage == boundary:
            raise error
    class Cursor:
        def fetchone(self):
            fail("fetch"); return (1,)
    class Connection:
        def set_progress_handler(self, *args): pass
        def execute(self, sql):
            fail("execute" if sql == "SELECT 1" else "begin" if sql == "BEGIN" else "configure")
            return Cursor()
        def commit(self): fail("commit")
        def close(self):
            closed.append(True); fail("close")
    def connect(*args, **kwargs):
        fail("open"); return Connection()
    monkeypatch.setattr(execution.sqlite3, "connect", connect)
    expected = DataIntegrityError if family in {"corrupt", "notadb"} else DatabaseUnavailableError
    with pytest.raises(expected) as failed:
        await database.probe(request())
    fields = dict(failed.value.context)
    assert fields["operation"] == "select1_probe"
    assert fields["stage"] == "probe_" + boundary
    assert fields["sqlite_errorcode"] == code and fields["sqlite_family"] == family
    assert fields["connection_opened"] == (boundary != "open")
    assert fields["close_succeeded"] == (boundary not in {"open", "close"})
    assert closed == ([] if boundary == "open" else [True])
    assert "private" not in json.dumps(fields) + str(failed.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("number,category", [(errno.EACCES, "access"), (errno.EPERM, "access"),
                                            (errno.ENOENT, "missing"), (errno.EIO, "io"),
                                            (errno.EROFS, "readonly"), (errno.ENOSPC, "space")])
async def test_filesystem_error_allowlist(database, monkeypatch, number, category):
    def fail(*args, **kwargs):
        raise OSError(number, "private exception", "/private/database")
    monkeypatch.setattr(execution.sqlite3, "connect", fail)
    with pytest.raises(DatabaseUnavailableError) as failed:
        await database.probe(request())
    assert failed.value.context["errno_category"] == category
    assert "private" not in json.dumps(dict(failed.value.context))


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["missing_file", "missing_parent", "notadb", "permission"])
async def test_real_file_conditions(database, tmp_path, condition, monkeypatch):
    # Switch only the synthetic fixture's path after lifecycle admission.
    path = tmp_path / "separate-probe.db"
    if condition == "missing_parent": path = tmp_path / "absent" / "probe.db"
    elif condition == "notadb": path.write_bytes(b"synthetic non-database" * 100)
    elif condition == "permission":
        path.write_bytes(b"synthetic")
        if os.name == "posix" and os.geteuid() != 0:
            path.chmod(0)
        else:
            # Windows/root cannot reproduce POSIX mode denial; exercise the same OS boundary.
            def denied(*args, **kwargs): raise PermissionError(errno.EACCES, "private")
            monkeypatch.setattr(execution.sqlite3, "connect", denied)
    database.config = DatabaseConfig(path)
    try:
        with pytest.raises(AppError) as failed:
            await database.probe(request())
        fields = failed.value.context
        if condition == "notadb":
            assert failed.value.code.value == "data_integrity" and fields["sqlite_family"] == "notadb"
        elif condition == "permission":
            assert fields.get("errno_category") == "access" or fields.get("sqlite_family") in {"cantopen", "perm"}
        else:
            assert fields["sqlite_family"] == "cantopen" and not path.exists()
    finally:
        if condition == "permission": path.chmod(0o600)


@pytest.mark.asyncio
async def test_probe_cancellation_retains_worker_capacity_and_closes(database, monkeypatch):
    started, release = threading.Event(), threading.Event()
    real_connect = execution.sqlite3.connect
    closed = []
    class Connection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == "SELECT 1":
                started.set(); assert release.wait(5)
            return super().execute(sql, *args)
        def close(self):
            closed.append(True); super().close()
    monkeypatch.setattr(execution.sqlite3, "connect", lambda *a, **k: real_connect(*a, **k, factory=Connection))
    task = asyncio.create_task(database.probe(request()))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert database.admitted[0] == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    await database.read(request(), lambda conn: None)  # same-lane drain barrier
    assert closed == [True, True] and database.admitted == (0, 0)


@pytest.mark.asyncio
async def test_actual_shared_cache_schema_lock_is_locked_and_stays_hard(database, monkeypatch):
    from discordbot.operations.adapters.probe_policy import ProbePolicy
    real_connect = execution.sqlite3.connect
    with closing(real_connect(database.config.path.as_uri() + '?cache=shared', uri=True)) as lock:
        lock.execute('BEGIN EXCLUSIVE')
        lock.execute('CREATE TABLE synthetic_uncommitted (n INTEGER)')
        monkeypatch.setattr(execution.sqlite3, 'connect',
            lambda address, **kwargs: real_connect(address + '&cache=shared', **kwargs))
        with pytest.raises(DatabaseUnavailableError) as failed:
            await database.probe(request())
        assert failed.value.context['sqlite_errorcode'] & 255 == sqlite3.SQLITE_LOCKED
        assert ProbePolicy().failure(dict(failed.value.context) | {'error_code':'database_unavailable'}, 0, True) == 'hard'
        lock.rollback()


@pytest.mark.asyncio
async def test_real_corrupt_schema_is_hard(database):
    path = database.config.path
    with path.open('r+b') as stream:
        stream.seek(100); stream.write(b'\xff')  # invalid first B-tree page type in a synthetic DB
    with pytest.raises(DataIntegrityError) as failed:
        await database.probe(request())
    assert failed.value.context['sqlite_family'] == 'corrupt'


@pytest.mark.asyncio
async def test_primary_busy_with_close_failure_is_never_transient(database, monkeypatch):
    from discordbot.operations.adapters.probe_policy import ProbePolicy
    class Connection:
        def set_progress_handler(self, *args): pass
        def execute(self, sql):
            error = sqlite3.OperationalError('private'); error.sqlite_errorcode = 5
            raise error
        def close(self): raise OSError(errno.EIO, 'private')
    monkeypatch.setattr(execution.sqlite3, 'connect', lambda *a, **k: Connection())
    with pytest.raises(DatabaseUnavailableError) as failed:
        await database.probe(request())
    fields = dict(failed.value.context) | {'error_code':'database_unavailable'}
    assert fields['cleanup_failed'] and not fields['close_succeeded']
    assert ProbePolicy().failure(fields, 0, True) == 'hard'


@pytest.mark.asyncio
async def test_short_lived_writer_releases_during_probe_connection(database, monkeypatch):
    path = database.config.path
    with closing(sqlite3.connect(path)) as conn: conn.execute('PRAGMA journal_mode=DELETE')
    script = """
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN EXCLUSIVE')
print('locked',flush=True);sys.stdin.readline();c.rollback();c.close();print('released',flush=True)
"""
    child = subprocess.Popen([sys.executable, '-I', '-c', script, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    real_connect = execution.sqlite3.connect
    try:
        assert await asyncio.wait_for(asyncio.to_thread(child.stdout.readline), 5) == 'locked\n'
        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            child.stdin.write('release\n'); child.stdin.flush()
            assert child.stdout.readline() == 'released\n'
            return conn
        monkeypatch.setattr(execution.sqlite3, 'connect', connect)
        assert await database.probe(request()) == (1,)
    finally:
        child.communicate(timeout=5)
        assert child.returncode == 0
