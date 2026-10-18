"""Explicit bootstrap, verified snapshots and restore-to-new-path primitives."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from discordbot.platform.errors import ConflictError, DataIntegrityError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER, cipher_from, decode, restore_script
from discordbot.storage.adapters.execution import (
    SqliteDatabase, WorkControl, checked_validation, connect, inspect_path, require_valid,
)
from discordbot.storage.adapters.files import candidate_file, distinct_paths, publish_new, sync_directory, sync_file
from discordbot.storage.adapters.migrations import apply_pending
from discordbot.storage.adapters.schema import create_legacy_schema
from discordbot.storage.ports.contracts import DatabaseRequest, ValidationReport


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    path: Path = field(repr=False)
    key: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    selected_index: int
    rejected_indices: tuple[int, ...]
    report: ValidationReport


def snapshot(source: Path, destination: Path, control: WorkControl,
             progress: Callable[[int, int, int], None] | None = None,
             *, max_bytes: int = 256 * 1024 * 1024) -> ValidationReport:
    """Pinned read transaction + online backup, bounded by caller deadline.

    WAL writers can commit while the read snapshot is pinned. Rollback-journal
    sources remain supported; their writers may encounter bounded busy failure.
    """
    with closing(connect(source, control, writable=False)) as conn:
        conn.execute("BEGIN")
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        if page_size * conn.execute("PRAGMA page_count").fetchone()[0] > max_bytes:
            raise DataIntegrityError("snapshot exceeds configured size budget")
        before = require_valid(checked_validation(conn))
        with closing(sqlite3.connect(destination, isolation_level=None)) as target:
            target.set_progress_handler(control.progress, 1000)
            def step(status: int, remaining: int, total: int) -> None:
                control.checkpoint()
                if progress is not None:
                    progress(status, remaining, total)
                control.checkpoint()

            conn.backup(target, pages=16, progress=step, sleep=0.01)
            target.execute("PRAGMA journal_mode=DELETE")
            after = require_valid(checked_validation(target))
            if (before.data_checksum, before.metadata_checksum, before.counts) != (after.data_checksum, after.metadata_checksum, after.counts):
                raise DataIntegrityError("snapshot reconciliation failed")
        return after


class DataRecovery:
    def __init__(self, database: SqliteDatabase) -> None:
        self._db = database

    async def bootstrap(self, request: DatabaseRequest) -> ValidationReport:
        """Explicit empty initialization, refusing every existing destination."""
        destination = self._db.config.path

        def work(control: WorkControl) -> ValidationReport:
            if destination.exists():
                raise ConflictError("explicit bootstrap refuses an existing file")
            with candidate_file(destination) as candidate:
                with closing(sqlite3.connect(candidate, isolation_level=None)) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    create_legacy_schema(conn)
                    control.checkpoint()
                    conn.commit()
                    apply_pending(conn, control.checkpoint)
                    report = require_valid(checked_validation(conn))
                    conn.execute("PRAGMA journal_mode=WAL")
                control.checkpoint()
                publish_new(candidate, destination)
                return report

        return await self._db.maintenance(request, work)

    async def migrated_copy(self, source: Path, destination: Path, request: DatabaseRequest) -> ValidationReport:
        """Source never mutated. Publish only a reconciled, expanded new copy."""
        def work(control: WorkControl) -> ValidationReport:
            distinct_paths(source, destination)
            require_valid(inspect_path(source, control))
            with candidate_file(destination) as candidate:
                before = snapshot(source, candidate, control, max_bytes=self._db.config.max_backup_bytes * 4)
                with closing(connect(candidate, control, writable=True)) as conn:
                    apply_pending(conn, control.checkpoint)
                    after = require_valid(checked_validation(conn))
                    if (before.data_checksum, before.metadata_checksum, before.counts) != (after.data_checksum, after.metadata_checksum, after.counts):
                        raise DataIntegrityError("migration semantic reconciliation failed")
                control.checkpoint()
                publish_new(candidate, destination)
                return after

        return await self._db.maintenance(request, work)

    def _restore(self, candidate: RecoveryCandidate, destination: Path, control: WorkControl) -> ValidationReport:
        distinct_paths(candidate.path, destination)
        with candidate.path.open("rb") as stream:
            payload = stream.read(self._db.config.max_backup_bytes + 1)
        sql, legacy = decode(payload, candidate.key, self._db.config.max_backup_bytes)
        control.checkpoint()
        with candidate_file(destination) as temporary:
            with closing(sqlite3.connect(temporary, isolation_level=None)) as conn:
                conn.execute(f"PRAGMA max_page_count={self._db.config.max_backup_bytes // 1024}")
                conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, self._db.config.max_backup_bytes)
                restore_script(conn, sql, legacy=legacy, key=candidate.key, control=control)
                report = require_valid(checked_validation(conn))
            control.checkpoint()
            publish_new(temporary, destination)
            return report

    async def restore_copy(self, candidate: RecoveryCandidate, destination: Path, request: DatabaseRequest) -> ValidationReport:
        return await self._db.maintenance(request, lambda control: self._restore(candidate, destination, control))

    async def recover_first_valid(self, candidates: tuple[RecoveryCandidate, ...], destination: Path, request: DatabaseRequest) -> RecoveryResult:
        """Ordered local/downloaded candidates; this layer performs no network I/O."""
        if not 1 <= len(candidates) <= 8:
            raise ConflictError("recovery requires one to eight explicit candidates")

        def work(control: WorkControl) -> RecoveryResult:
            if destination.exists():
                raise ConflictError("recovery destination must be new")
            rejected = []
            for index, candidate in enumerate(candidates):
                control.checkpoint()
                try:
                    report = self._restore(candidate, destination, control)
                    return RecoveryResult(index, tuple(rejected), report)
                except (DataIntegrityError, FileNotFoundError):
                    rejected.append(index)
            raise DataIntegrityError("no valid recovery candidate", context={"rejected_count": len(rejected)})

        return await self._db.maintenance(request, work)

    async def backup(self, destination: Path, key: bytes, request: DatabaseRequest) -> ValidationReport:
        """Online data-side snapshot; only the encrypted artifact replaces latest."""
        source = self._db.config.path
        def work(control: WorkControl) -> ValidationReport:
            distinct_paths(source, destination)
            cipher = cipher_from(key)
            with candidate_file(destination) as snap:
                report = snapshot(source, snap, control, max_bytes=self._db.config.max_backup_bytes * 4)
                with closing(connect(snap, control, writable=False)) as conn:
                    chunks = []
                    length = 0
                    for line in conn.iterdump():
                        control.checkpoint()
                        chunk = (line + "\n").encode("utf-8")
                        length += len(chunk)
                        # Fernet/base64 envelope expansion fits the configured input cap.
                        if length > (self._db.config.max_backup_bytes - 256) * 3 // 4:
                            raise DataIntegrityError("backup exceeds configured size budget")
                        chunks.append(chunk)
                plaintext = b"".join(chunks)
                payload = BACKUP_HEADER + cipher.encrypt(plaintext)
                # Verify the exact emitted format through the independent restore reader.
                sql, legacy = decode(payload, key, self._db.config.max_backup_bytes)
                with candidate_file(destination) as verification:
                    with closing(sqlite3.connect(verification, isolation_level=None)) as conn:
                        restore_script(conn, sql, legacy=legacy, key=key, control=control)
                        verified = require_valid(checked_validation(conn))
                        if (report.data_checksum, report.metadata_checksum, report.counts, report.migration_version) != (verified.data_checksum, verified.metadata_checksum, verified.counts, verified.migration_version):
                            raise DataIntegrityError("backup restore reconciliation failed")
                with candidate_file(destination, ".encrypted") as encrypted:
                    encrypted.write_bytes(payload)
                    sync_file(encrypted)
                    control.checkpoint()
                    if destination.is_symlink():
                        raise ConflictError("backup destination must not be a symlink")
                    os.replace(encrypted, destination)
                    sync_directory(destination.parent)
                return report

        # Backup is read-side maintenance allowed while normal writers are active.
        return await self._db._dispatch("read", request, work)
