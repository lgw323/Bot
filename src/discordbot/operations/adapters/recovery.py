"""Operational backup archives and isolated restore around Phase 3 primitives."""

from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Protocol
from uuid import uuid4

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.filesystem import atomic_json, contained, digest, identifier, read_json, sync_dir
from discordbot.platform.errors import DataIntegrityError, ConflictError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.adapters.files import publish_new
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


class RemoteBackup(Protocol):
    """Implementations publish an immutable encrypted object and verify its digest.

    No destination is inferred from the source repository. The caller supplies
    an approved destination/auth adapter; no plaintext or keys cross this port.
    """
    async def publish(self, artifact: Path, checksum: str, identity: str) -> None: ...


class Backups:
    def __init__(self, database: SqliteDatabase, root: Path, key: bytes, key_id: str,
                 executor: BoundedExecutor, audit: Audit, *, remote: RemoteBackup | None = None) -> None:
        self.database, self.root, self.key = database, root, key
        self.key_id = identifier(key_id)
        self.executor, self.audit, self.remote = executor, audit, remote

    async def create(self, release: str) -> str:
        if await self.executor.run(lambda: sum(1 for _ in self.root.iterdir())) >= 65:
            raise ConflictError("backup artifact capacity reached; inspect failed publications")
        identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid4().hex
        artifact = contained(self.root, self.root / (identity + ".enc"))
        await self.executor.run_retained(self.audit.write, "backup", release, "started", "snapshot")
        try:
            report = await DataRecovery(self.database).backup(artifact, self.key, DatabaseRequest.within(120))
            if report.migration_version != 5:
                raise DataIntegrityError("backup schema is incompatible with current application")
            checksum = await self.executor.run(digest, artifact)
            record = dict(identity=identity, sha256=checksum, key_id=self.key_id, release=identifier(release),
                          schema=report.migration_version, timestamp=datetime.now(timezone.utc).isoformat())
            await self.executor.run_retained(atomic_json, self.root / (identity + ".json"), record)
            # Failed remote publication never advances latest. Local verified
            # artifacts remain recoverable; transport retry is an operator action.
            if self.remote:
                await self.remote.publish(artifact, checksum, identity)
            # Validate the exact local artifacts before committing latest or deleting
            # anything. Failed publications may leave valid or corrupt orphans.
            removals = await self._retention_plan(8, newest=identity)
            await self.executor.run_retained(self.audit.write, "backup", release, "ok", "verified")
            await self.executor.run_retained(atomic_json, self.root / "latest.json", {"identity": identity})
            await self.executor.run_retained(self._prune, removals)
            return identity
        except BaseException:
            await self.executor.run_retained(self.audit.write, "backup", release, "failed", "snapshot_or_publish")
            raise

    def candidates(self) -> tuple[str, ...]:
        records = sorted((p.stem for p in self.root.glob("*.json") if p.name != "latest.json"), reverse=True)
        # Timestamped archive order remains usable when latest itself is corrupt.
        return tuple(records[:8])

    async def _retention_plan(self, count: int, *, newest: str | None = None) -> tuple[str, ...]:
        if not 2 <= count <= 32:
            raise ValueError("backup retention must preserve alternatives")
        try:
            latest = identifier((await self.executor.run(read_json, self.root / "latest.json")).get("identity"))
        except (DataIntegrityError, FileNotFoundError):
            latest = None  # A missing/corrupt pointer cannot identify a protected archive.
        records = await self.executor.run(
            lambda: sorted((p.stem for p in self.root.glob("*.json") if p.name != "latest.json"), reverse=True)
        )
        verified: list[str] = []
        for identity in records:
            try:
                async with self._validated_candidate(identity, self.root):
                    verified.append(identity)
            except (DataIntegrityError, FileNotFoundError):
                if identity == newest:
                    raise
                # Unverified artifacts stay available for operator reconciliation;
                # they cannot consume the recovery floor. I/O/cancellation propagates.
        if newest is not None and newest not in verified:
            raise DataIntegrityError("new backup is not recoverable")
        protected = set(verified[:count]) | {latest, newest}
        return tuple(identity for identity in verified if identity not in protected)

    async def retain(self, count: int) -> None:
        removals = await self._retention_plan(count)
        await self.executor.run_retained(self._prune, removals)

    def _prune(self, identities: tuple[str, ...]) -> None:
        for identity in identities:
            identifier(identity)
            for suffix in (".json", ".enc"):
                contained(self.root, self.root / (identity + suffix)).unlink(missing_ok=True)

    @asynccontextmanager
    async def _validated_candidate(self, identity: str, directory: Path) -> AsyncIterator[Path]:
        identifier(identity)
        isolated = directory / (".rehearsal-" + uuid4().hex + ".db")
        try:
            record = await self.executor.run(read_json, self.root / (identity + ".json"))
            artifact = contained(self.root, self.root / (identity + ".enc"))
            if (record.get("identity") != identity or record.get("schema") != 5
                    or record.get("key_id") != self.key_id
                    or await self.executor.run(digest, artifact) != record.get("sha256")):
                raise DataIntegrityError("backup metadata validation failed")
            offline = SqliteDatabase(DatabaseConfig(isolated.absolute()))
            try:
                await DataRecovery(offline).restore_copy(RecoveryCandidate(artifact, self.key),
                                                         isolated, DatabaseRequest.within(120))
            finally:
                await offline.stop()
            # The same independent application compatibility check gates both
            # restore publication and eligibility to displace older recovery points.
            candidate_db = SqliteDatabase(DatabaseConfig(isolated.absolute()))
            try:
                await candidate_db.start()
                report = await candidate_db.inspect(DatabaseRequest.within(10))
                if report.state is not DatabaseState.VALID or report.migration_version != 5:
                    raise DataIntegrityError("restored application compatibility failed")
            finally:
                await candidate_db.stop()
            yield isolated
        finally:
            def cleanup() -> None:
                for suffix in ("", "-wal", "-shm", "-journal"):
                    Path(str(isolated) + suffix).unlink(missing_ok=True)
            await self.executor.run_retained(cleanup)

    async def restore(self, destination: Path, release: str, *, candidates: tuple[str, ...] | None = None) -> str:
        candidates = candidates if candidates is not None else await self.executor.run(self.candidates)
        if not 1 <= len(candidates) <= 8 or destination.exists():
            raise ConflictError("restore requires candidates and a new isolated destination")
        await self.executor.run_retained(self.audit.write, "restore_rehearsal", release, "started", "validation")
        try:
            for identity in candidates:
                identifier(identity)
                try:
                    async with self._validated_candidate(identity, destination.parent) as isolated:
                        await self.executor.run_retained(publish_new, isolated, destination)
                except (DataIntegrityError, FileNotFoundError):
                    continue
                await self.executor.run_retained(self.audit.write, "restore_rehearsal", release, "ok", "validated")
                return identity
            raise DataIntegrityError("no valid backup candidate")
        except BaseException:
            # An isolated completed file may exist after cancellation; it remains
            # unpromoted and must be revalidated explicitly, never auto-selected.
            await self.executor.run_retained(self.audit.write, "restore_rehearsal", release, "failed", "validation")
            raise


def _reject_promotion_source_sidecars(candidate: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            Path(str(candidate) + suffix).lstat()
        except FileNotFoundError:
            continue
        # lstat also rejects dangling links; metadata access errors propagate.
        raise ConflictError("promotion source requires quiescence without sidecars")


def promote(candidate: Path, live: Path, expected_sha256: str, *, stopped: bool, audit: Audit, release: str) -> None:
    """Explicit offline promotion only. Caller validates and checks service state.

    The operator must retain approved encrypted recovery evidence before invocation.
    Source sidecars, canonical WAL/SHM or a changed candidate block promotion.
    Caller owns the operation lock and prevents writers throughout; filesystem
    rechecks do not acquire a SQLite lock. No checkpoint or down-migration.
    """
    if not stopped or candidate == live or digest(candidate) != expected_sha256:
        raise ConflictError("promotion preconditions not satisfied")
    _reject_promotion_source_sidecars(candidate)
    contained(live.parent, live)
    if any(Path(str(live) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise ConflictError("promotion requires quiescent database without sidecars")
    audit.write("restore_promotion", release, "started", "operator_approved")
    temporary = contained(live.parent, live.with_name(".restore-" + uuid4().hex))
    try:
        with candidate.open("rb") as source, temporary.open("xb") as output:
            os.chmod(temporary, 0o660)  # Dedicated service group owns the shared two-process store.
            shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if digest(temporary) != expected_sha256:
            raise DataIntegrityError("promotion copy changed")
        _reject_promotion_source_sidecars(candidate)
        if digest(candidate) != expected_sha256:
            raise DataIntegrityError("promotion source changed")
        _reject_promotion_source_sidecars(candidate)
        os.replace(temporary, live)
        sync_dir(live.parent)
        audit.write("restore_promotion", release, "ok", "complete")
    finally:
        temporary.unlink(missing_ok=True)
