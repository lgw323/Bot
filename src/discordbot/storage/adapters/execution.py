"""Two bounded lanes: one SQLite writer, one independent snapshot reader."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Callable, TypeVar

from discordbot.platform.errors import (
    AppError, CancellationError, ConflictError, DataIntegrityError,
    DatabaseUnavailableError,
)
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.schema import validate
from discordbot.storage.adapters.probe_diagnostics import ProbeTrace
from discordbot.storage.ports.contracts import (
    DatabaseConfig, DatabaseDeadlineError, DatabaseObservation, DatabaseRequest, DatabaseState, ValidationReport,
)

T = TypeVar("T")


class WorkControl:
    """Cooperative thread cancellation, including SQLite progress callbacks."""

    def __init__(self, request: DatabaseRequest) -> None:
        self.request = request
        self.cancelled = threading.Event()

    def checkpoint(self) -> None:
        if self.cancelled.is_set():
            raise CancellationError("database work cancelled")
        if time.monotonic() >= self.request.deadline:
            raise DatabaseDeadlineError("database work deadline exceeded")

    def progress(self) -> int:
        return int(self.cancelled.is_set() or time.monotonic() >= self.request.deadline)


def connect(path: Path, control: WorkControl, *, writable: bool, busy_seconds: float = 0.1,
            trace: ProbeTrace | None = None) -> sqlite3.Connection:
    control.checkpoint()
    conn = sqlite3.connect(
        path.as_uri() + ("?mode=rw" if writable else "?mode=ro"), uri=True,
        timeout=min(busy_seconds, max(0, control.request.deadline - time.monotonic())),
        isolation_level=None,
    )
    if trace is not None:
        trace.connection_opened = True
        trace.stage = 'probe_configure'
    try:
        conn.set_progress_handler(control.progress, 1000)
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-2000")
        conn.execute("PRAGMA trusted_schema=OFF")
        if not writable:
            conn.execute("PRAGMA query_only=ON")
        return conn
    except BaseException as exc:
        if trace is None:
            conn.close()
        else:
            if isinstance(exc, Exception):
                trace.capture(exc)
            trace.close(conn)
        raise


def checked_validation(conn: sqlite3.Connection) -> ValidationReport:
    # Local import avoids a module cycle; no work is performed on import.
    from discordbot.storage.adapters.migrations import validate_ledger

    report = validate(conn)
    if report.state is not DatabaseState.VALID:
        return report
    try:
        version = validate_ledger(conn)
    except DataIntegrityError:
        return replace(report, state=DatabaseState.INVALID_LEDGER)
    return replace(report, migration_version=version)


def require_valid(report: ValidationReport) -> ValidationReport:
    if report.state is not DatabaseState.VALID:
        raise DataIntegrityError("database validation failed", context={"state": report.state.value})
    return report


def inspect_path(path: Path, control: WorkControl) -> ValidationReport:
    control.checkpoint()
    if not path.exists():
        return ValidationReport(DatabaseState.MISSING)
    if path.is_symlink() or not path.is_file():
        return ValidationReport(DatabaseState.WRONG_SCHEMA)
    if path.stat().st_size == 0:
        return ValidationReport(DatabaseState.EMPTY)
    try:
        with closing(connect(path, control, writable=False)) as conn:
            conn.execute("BEGIN")
            return checked_validation(conn)
    except sqlite3.DatabaseError as exc:
        control.checkpoint()
        if getattr(exc, "sqlite_errorcode", 0) & 0xFF in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            return ValidationReport(DatabaseState.CORRUPT)
        raise


class SqliteDatabase:
    """Lifecycle-owned resource, never wired into a production root in Phase 3.

    Connections belong to the worker invocation and close on that same thread.
    Callback APIs are adapter-private; application code uses context repositories.
    """

    name = "database"
    required = True

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self._reader = BoundedExecutor(workers=1, queue_capacity=config.queue_capacity, name="db-read")
        self._writer = BoundedExecutor(workers=1, queue_capacity=config.queue_capacity, name="db-write")
        self._history: deque[DatabaseObservation] = deque(maxlen=4 * (config.queue_capacity + 2))
        self._history_lock = threading.Lock()
        self._ready = False
        self._closed = False

    @property
    def admitted(self) -> tuple[int, int]:
        return self._reader.admitted, self._writer.admitted

    @property
    def observations(self) -> tuple[DatabaseObservation, ...]:
        with self._history_lock:
            return tuple(self._history)

    def _observe(self, observation: DatabaseObservation) -> None:
        with self._history_lock:
            self._history.append(observation)

    async def _dispatch(self, lane: str, request: DatabaseRequest, work: Callable[[WorkControl], T]) -> T:
        if self._closed:
            raise ConflictError("database admission is closed")
        control = WorkControl(request)
        control.checkpoint()
        admitted_at = time.monotonic()

        def execute() -> T:
            started = time.monotonic()
            result = "ok"
            try:
                control.checkpoint()
                return work(control)
            except sqlite3.Error as exc:
                try:
                    control.checkpoint()
                except AppError as interrupted:
                    result = interrupted.code.value
                    raise
                code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_CONSTRAINT}:
                    error = DataIntegrityError("SQLite integrity failure")
                else:
                    error = DatabaseUnavailableError("SQLite operation unavailable", context={"sqlite_code": code})
                result = error.code.value
                raise error from None
            except OSError:
                result = "database_unavailable"
                raise DatabaseUnavailableError("database filesystem operation unavailable") from None
            except AppError as exc:
                result = exc.code.value
                raise
            except Exception:
                result = "internal"
                # Do not forward unexpected callbacks' raw SQL/row/exception text.
                raise DataIntegrityError("database adapter operation failed") from None
            finally:
                self._observe(DatabaseObservation(lane, "worker_finished", result, request.correlation_id,
                                                  started - admitted_at, time.monotonic() - started))

        executor = self._reader if lane == "read" else self._writer
        try:
            async with asyncio.timeout(max(0, request.deadline - time.monotonic())):
                return await executor.run(execute)
        except TimeoutError:
            control.cancelled.set()
            self._observe(DatabaseObservation(lane, "awaiter_finished", "deadline_exceeded", request.correlation_id))
            raise DatabaseDeadlineError("database request deadline exceeded", context={"commit_outcome": "unconfirmed"}) from None
        except asyncio.CancelledError:
            control.cancelled.set()
            self._observe(DatabaseObservation(lane, "awaiter_finished", "cancelled", request.correlation_id))
            raise
        except AppError as exc:
            self._observe(DatabaseObservation(lane, "awaiter_finished", exc.code.value, request.correlation_id))
            raise

    async def inspect(self, request: DatabaseRequest) -> ValidationReport:
        return await self._dispatch("read", request, lambda control: inspect_path(self.config.path, control))

    async def start(self) -> None:
        if self._ready or self._closed:
            raise ConflictError("database lifecycle cannot start again")
        try:
            require_valid(await self.inspect(DatabaseRequest.within(self.config.startup_timeout_seconds, "database-startup")))
        except BaseException:
            await self.stop()
            raise
        self._ready = True

    async def stop(self) -> None:
        self._ready = False
        self._closed = True
        # Close both lanes even if one cannot drain in its grace period.
        results = await asyncio.gather(
            self._reader.close(grace_seconds=self.config.shutdown_grace_seconds),
            self._writer.close(grace_seconds=self.config.shutdown_grace_seconds), return_exceptions=True,
        )
        if any(isinstance(result, BaseException) for result in results):
            raise ConflictError("database workers did not drain")

    async def maintenance(self, request: DatabaseRequest, work: Callable[[WorkControl], T]) -> T:
        """Explicit copy/bootstrap operations; never accepted after runtime start."""
        if self._ready:
            raise ConflictError("offline data operation requires stopped feature admission")
        return await self._dispatch("maintenance", request, work)

    async def read(self, request: DatabaseRequest, query: Callable[[sqlite3.Connection], T]) -> T:
        return await self._transaction(request, query, writable=False)

    async def probe(self, request: DatabaseRequest) -> tuple[int]:
        """Same bounded read lane/connection policy, with fixed-operation diagnostics."""
        if not self._ready:
            raise ConflictError("database is not ready")

        def execute(control: WorkControl) -> tuple[int]:
            trace = ProbeTrace()
            conn = None
            result = None
            try:
                conn = connect(self.config.path, control, writable=False,
                               busy_seconds=self.config.busy_timeout_seconds, trace=trace)
                trace.stage = 'probe_begin'
                conn.execute('BEGIN')
                trace.stage = 'probe_execute'
                cursor = conn.execute('SELECT 1')
                trace.stage = 'probe_fetch'
                result = cursor.fetchone()
                trace.stage = 'probe_commit'
                control.checkpoint()
                conn.commit()
            except Exception as exc:
                if isinstance(exc, sqlite3.Error):
                    try:
                        control.checkpoint()
                    except AppError as interrupted:
                        if trace.error is not None:
                            trace.stage = str(trace.error.context.get('stage', 'probe_configure'))
                            trace.error = None
                        trace.capture(interrupted)
                # connect() already recorded configuration failures before cleanup.
                if trace.error is None:
                    trace.capture(exc)
            finally:
                if conn is not None:
                    # Read-only transaction; close rolls back after a failed read.
                    trace.close(conn)
            trace.raise_if_failed()
            if result != (1,):
                raise DataIntegrityError('Fixed database probe returned an invalid result')
            return result

        return await self._dispatch('read', request, execute)

    async def write(self, request: DatabaseRequest, mutation: Callable[[sqlite3.Connection], T]) -> T:
        return await self._transaction(request, mutation, writable=True)

    async def _transaction(self, request: DatabaseRequest, work: Callable[[sqlite3.Connection], T], *, writable: bool) -> T:
        if not self._ready:
            raise ConflictError("database is not ready")

        def execute(control: WorkControl) -> T:
            with closing(connect(self.config.path, control, writable=writable,
                                 busy_seconds=self.config.busy_timeout_seconds)) as conn:
                conn.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
                try:
                    result = work(conn)
                    control.checkpoint()
                    conn.commit()
                    return result
                except BaseException:
                    conn.rollback()
                    raise

        return await self._dispatch("write" if writable else "read", request, execute)
