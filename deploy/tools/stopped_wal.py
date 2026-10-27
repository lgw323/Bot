"""Auxiliary stopped-cutover operation; no CLI, runtime hook or host adapter.

The caller must hold OperationOwner continuously across stop, final backup,
normalization and any later pointer change. A reviewed supervisor must supply
fresh exclusive-access evidence; SQLite checkpoint success is NOT that evidence.
Current validation uses synthetic temporary paths only. See the adjacent runbook.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from typing import Callable, TextIO

from discordbot.operations.adapters.filesystem import ExclusiveLock
from discordbot.storage.adapters.execution import checked_validation, require_valid
from discordbot.storage.adapters.files import sync_directory

SIDECARS = ("-wal", "-shm", "-journal")
UNITS = {"discord-bot", "watch-web"}
MAX_BYTES = 256 * 1024 * 1024


class Refused(RuntimeError):
    pass


class NormalizationFailed(RuntimeError):
    def __init__(self, receipt: dict) -> None:
        super().__init__("WAL operation not verified; inspect receipt before any further action")
        self.receipt = receipt


@dataclass(frozen=True)
class StopEvidence:
    # Adapter contract: check all DB consumers and prevent new opens/starts, not
    # just these two systemd units. No production adapter is supplied here.
    target: Path
    operation_lock: Path
    epoch: str
    valid_until: float  # monotonic; adapter must return within caller's deadline
    consumers_excluded: bool
    services: dict[str, tuple[str, str, int]]  # ActiveState, Result, MainPID


class OperationOwner:
    """Real kernel lock, with live supervisor evidence checked inside ownership.

    This context owns the shared operation lock itself. Do not nest it inside an
    existing owner or release/reacquire a deployment lock just to call this tool.
    The future controller must integrate one continuous ownership context.
    """
    def __init__(self, lock: Path, observe: Callable[[Path, float], StopEvidence]) -> None:
        self.path = lock.absolute()
        self.observe = observe
        self.held = False
        self.epoch: str | None = None

    def __enter__(self) -> OperationOwner:
        if self.held or self.path.resolve() != self.path or self.path.is_symlink():
            raise Refused("invalid operation lock path or repeated ownership")
        if self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink != 1):
            raise Refused("operation lock must be a private regular inode")
        self.context = ExclusiveLock(self.path, timeout=0).acquire()
        self.context.__enter__()
        try:
            self.identity = identity(self.path)
        except BaseException:
            self.context.__exit__(None, None, None)
            raise
        self.held = True
        return self

    def __exit__(self, *args: object) -> None:
        self.held = False
        self.epoch = None
        self.context.__exit__(*args)

    def check(self, target: Path, lock: Path, deadline: float) -> None:
        if not self.held or self.path != lock or identity(self.path) != self.identity:
            raise Refused("continuous shared operation ownership missing")
        check_deadline(deadline)
        evidence = self.observe(target, deadline)
        check_deadline(deadline)
        if not self.held or identity(self.path) != self.identity:
            raise Refused("operation ownership changed during observation")
        if (evidence.target != target or evidence.operation_lock != lock
                or not evidence.epoch or evidence.consumers_excluded is not True
                or not time.monotonic() < evidence.valid_until
                or set(evidence.services) != UNITS
                or any(value != ("inactive", "success", 0) for value in evidence.services.values())):
            raise Refused("exclusive stopped consumers not confirmed")
        if self.epoch is not None and evidence.epoch != self.epoch:
            raise Refused("exclusive ownership epoch changed")
        self.epoch = evidence.epoch


@dataclass(frozen=True)
class Request:
    database: Path
    operation_lock: Path
    # Restored and verified final stopped backup, supplied explicitly. Accepted
    # DELETE artifact is read immutably and never converted or promoted here.
    final_restore: Path
    restore_sha256: str
    preservation: Path  # new private directory; no overwrite/cleanup
    receipt: Path       # new JSONL file; no overwrite
    seconds: float = 15.0


def check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise Refused("operation deadline exceeded")


def regular(path: Path) -> os.stat_result:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or path.absolute() != path.resolve()):
        raise Refused("existing private regular file required")
    if info.st_size > MAX_BYTES:
        raise Refused("file exceeds operation size budget")
    return info


def identity(path: Path) -> tuple[int, int]:
    info = regular(path)
    return info.st_dev, info.st_ino


def checksum(path: Path) -> str:
    regular(path)
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(path: Path) -> dict:
    result = {}
    for suffix in ("", *SIDECARS):
        file = Path(str(path) + suffix)
        try:
            info = regular(file)
        except FileNotFoundError:
            if suffix == "":
                raise
            result[suffix] = None
        else:
            result[suffix] = {"sha256": checksum(file), "size": info.st_size,
                              "identity": [info.st_dev, info.st_ino]}
    with path.open("rb") as stream:
        header = stream.read(20)
    if not header.startswith(b"SQLite format 3\x00"):
        raise Refused("SQLite header required")
    result["header_mode"] = list(header[18:20])
    return result


def connect(path: Path, deadline: float, *, immutable: bool = False) -> sqlite3.Connection:
    check_deadline(deadline)
    query = "?mode=ro&immutable=1" if immutable else "?mode=rw"
    conn = sqlite3.connect(path.as_uri() + query, uri=True, isolation_level=None,
                           timeout=min(0.1, max(0, deadline - time.monotonic())))
    conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    return conn


def semantic(path: Path, deadline: float, *, immutable: bool = False) -> dict:
    # Fully close this validation handle before opening the transition handle:
    # retained validation statements on the same handle caused SQLITE_LOCKED.
    with closing(connect(path, deadline, immutable=immutable)) as conn:
        conn.execute("BEGIN")
        with closing(conn.execute("PRAGMA integrity_check")) as cursor:
            if cursor.fetchall() != [("ok",)]:
                raise Refused("SQLite integrity failed")
        report = require_valid(checked_validation(conn))
        return {"version": report.migration_version, "data": report.data_checksum,
                "metadata": report.metadata_checksum, "counts": report.counts}


def append_receipt(stream: TextIO, value: dict) -> None:
    stream.write(json.dumps(value, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def close_receipt(stream: TextIO) -> None:
    stream.close()


def normalize(request: Request, owner: OperationOwner | None) -> dict:
    """Normalize the SAME latest database inode; never restore or delete files.

    Raises NormalizationFailed with an in-memory receipt on any non-success.
    Error after any writable SQLite open is conservatively classified as possibly
    changed, even when observed bytes match. Physical before/after cannot prove
    absence of intermediate changes. No automatic reversal or pointer action.
    """
    result: dict = {"outcome": "refused", "stage": "admission", "target_access_started": False,
                    "before": None, "after": None, "receipt_persisted": False}
    stream = None
    target = request.database
    try:
        paths = [target, request.operation_lock, request.final_restore, request.preservation, request.receipt]
        if (not 0 < request.seconds <= 60 or any(not p.is_absolute() or p != p.resolve() for p in paths)
                or len(set(paths)) != len(paths)):
            raise Refused("explicit distinct canonical paths and bounded deadline required")
        if (request.preservation.exists() or request.receipt.exists()
                or request.final_restore.parent == request.preservation
                or any(p.is_relative_to(request.preservation) for p in paths if p != request.preservation)
                or any(str(p) == str(q) + s for p in paths for q in paths if p != q for s in SIDECARS)):
            raise Refused("new separate receipt and preservation paths required")
        deadline = time.monotonic() + request.seconds
        if owner is None:
            raise Refused("operation owner required")
        owner.check(target, request.operation_lock, deadline)
        before = inventory(target)
        result["before"] = before
        result["database"] = str(target)
        result["preservation"] = str(request.preservation)
        result["restore_sha256"] = request.restore_sha256
        target_id = identity(target)
        restore_before = inventory(request.final_restore)
        if (restore_before["header_mode"] != [1, 1]
                or any(restore_before[s] is not None for s in SIDECARS)
                or restore_before[""]["sha256"] != request.restore_sha256):
            raise Refused("final verified DELETE restore identity mismatch")
        if (before["-journal"] is not None or before["header_mode"] not in ([1, 1], [2, 2])
                or (before["header_mode"] == [1, 1] and any(before[s] is not None for s in SIDECARS))):
            raise Refused("ambiguous live sidecars or journal mode")
        if sum(item["size"] for key, item in before.items() if key != "header_mode" and item) > MAX_BYTES:
            raise Refused("preservation set exceeds size budget")
        # Receipt exists before the first SQLite connection or preservation copy.
        fd = os.open(request.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        stream = os.fdopen(fd, "w", encoding="utf-8")
        append_receipt(stream, {**result, "event": "admitted"})
        sync_directory(request.receipt.parent)
        request.preservation.mkdir(mode=0o700)
        result["stage"] = "preserve"
        for suffix in ("", *SIDECARS):
            if before[suffix] is None:
                continue
            source = Path(str(target) + suffix)
            dest = request.preservation / ("original.db" + suffix)
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out, source.open("rb") as incoming:
                while block := incoming.read(1024 * 1024):
                    check_deadline(deadline)
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            if checksum(dest) != before[suffix]["sha256"]:
                raise Refused("preservation copy mismatch")
        if inventory(target) != before:
            raise Refused("source changed while preserving")
        sync_directory(request.preservation)
        sync_directory(request.preservation.parent)
        result["originals_preserved"] = True
        owner.check(target, request.operation_lock, deadline)
        result["stage"] = "validate_final_backup"
        reference = semantic(request.final_restore, deadline, immutable=True)
        result["reference"] = reference
        result["stage"] = "validate_latest"
        # RW validation/close can itself checkpoint or remove WAL/SHM via SQLite.
        result["target_access_started"] = True
        append_receipt(stream, {**result, "event": "before_sqlite_access"})
        before_data = semantic(target, deadline)
        result["semantic_before"] = before_data
        if before_data != reference:
            raise Refused("final stopped backup does not match latest database")
        owner.check(target, request.operation_lock, deadline)
        if identity(target) != target_id:
            raise Refused("database inode changed")
        result["stage"] = "normalize"
        with closing(connect(target, deadline)) as conn:
            if conn.in_transaction:
                raise Refused("autocommit connection required")
            with closing(conn.execute("PRAGMA journal_mode=WAL")) as cursor:
                if cursor.fetchall() != [("wal",)]:
                    raise Refused("WAL mode not confirmed")
            result["wal_returned"] = True
            append_receipt(stream, {**result, "event": "wal_returned"})
            with closing(conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")) as cursor:
                checkpoint = cursor.fetchall()
            result["checkpoint"] = checkpoint
            if checkpoint != [(0, 0, 0)]:
                raise Refused("checkpoint incomplete")
        result["stage"] = "verify"
        after_data = semantic(target, deadline)
        result["semantic_after"] = after_data
        after = inventory(target)
        result["after"] = after
        if (after_data != before_data or identity(target) != target_id
                or after["header_mode"] != [2, 2]
                or any(after[s] is not None for s in SIDECARS)):
            raise Refused("final data/mode/sidecar postcondition failed")
        if inventory(request.final_restore) != restore_before:
            raise Refused("original recovery artifact changed")
        owner.check(target, request.operation_lock, deadline)
        sync_directory(target.parent)
        result.update(outcome="verified", stage="complete", receipt_persisted=True)
        append_receipt(stream, {**result, "event": "complete"})
        close_receipt(stream)
        stream = None
        return result
    except BaseException as error:
        result["outcome"] = "failed_after_target_access" if result["target_access_started"] else "refused"
        result["receipt_persisted"] = False
        result["error_type"] = type(error).__name__
        result["reason"] = str(error) if isinstance(error, Refused) else "operation failed; inspect stage and error type"
        result["sqlite_errorcode"] = getattr(error, "sqlite_errorcode", None)
        if result["before"] is not None:
            try:
                result["after"] = inventory(target)  # physical inspection only; no retry/SQLite
            except Exception as inspection_error:
                result["after"] = None
                result["after_error_type"] = type(inspection_error).__name__
        try:
            if stream is not None:
                append_receipt(stream, {**result, "event": "failed"})
                result["receipt_persisted"] = True
        except Exception as receipt_error:
            result["receipt_error_type"] = type(receipt_error).__name__
        if not isinstance(error, Exception):
            raise
        raise NormalizationFailed(result) from error
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception as close_error:
                result["receipt_close_error_type"] = type(close_error).__name__
