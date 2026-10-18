"""PHASE 10A copy-only candidate and isolated encrypted recovery evidence. Never promotes."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from scripts.rehearse_v2_data import check_copy, fingerprint
from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.configuration import read_secret
from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.operations.adapters.recovery import Backups
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


def standalone(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Standalone source required")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Source sidecars require writer reconciliation")


def durable_copy(source: Path, destination: Path) -> None:
    with source.open("rb") as incoming, destination.open("xb") as output:
        os.chmod(destination, 0o600)
        shutil.copyfileobj(incoming, output)
        output.flush()
        os.fsync(output.fileno())


async def prepare(source: Path, output: Path) -> dict:
    """Caller confirms authoritative source and no writer. Original is never opened by SQLite."""
    standalone(source)
    if output.exists() or source == output or source.is_relative_to(output):
        raise ValueError("New isolated output directory required")
    before = fingerprint(source)
    output.mkdir(parents=True, mode=0o700)
    evidence = {"status": "preparing", "source": str(source), "source_before": before,
                "production_promoted": False, "backup_restore": "pending_operator_key"}
    try:
        preserved = output / "preserved-original.db"
        durable_copy(source, preserved)
        if fingerprint(preserved) != before:
            raise ValueError("Preservation copy differs")
        preserved.chmod(0o400)
        with tempfile.TemporaryDirectory(prefix="migration-working-", dir=output) as temporary:
            work = Path(temporary)
            working = work / "source-working.db"
            durable_copy(preserved, working)
            evidence["validation"] = await check_copy(working, work)
            expanded = work / "expanded.db"
            standalone(expanded)
            durable_copy(expanded, output / "candidate.db")
        candidate = output / "candidate.db"
        evidence["candidate"] = fingerprint(candidate)
        candidate.chmod(0o400)
        evidence["status"] = "migration_verified"
    finally:
        evidence["source_after"] = fingerprint(source)
        evidence["source_unchanged"] = before == evidence["source_after"]
        if not evidence["source_unchanged"]:
            evidence["status"] = "source_changed_rejected"
        atomic_json(output / "evidence.json", evidence)
    if not evidence["source_unchanged"]:
        raise ValueError("Source changed during rehearsal")
    return evidence


async def recover(output: Path, key_file: Path, key_id: str, release: str) -> dict:
    """Use an operator-provided key file; verify an isolated restore, never a canonical target."""
    if key_file.name.startswith(".env"):
        raise ValueError("No dotenv inputs")
    evidence = json.loads((output / "evidence.json").read_text())
    if evidence.get("status") != "migration_verified" or evidence.get("backup_restore") != "pending_operator_key":
        raise ValueError("Unconsumed verified candidate required")
    candidate = output / "candidate.db"
    standalone(candidate)
    if fingerprint(candidate) != evidence["candidate"]:
        raise ValueError("Reviewed candidate changed")
    key = read_secret(key_file.parent, key_file.name).encode()
    # Validate the key before creating any recovery destination; do not print it.
    from cryptography.fernet import Fernet
    Fernet(key)
    for name in ("backups", "audit", "restore"):
        (output / name).mkdir(mode=0o700)
    database = SqliteDatabase(DatabaseConfig(candidate))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="production-rehearsal")
    try:
        await database.start()
        before = require_valid(await database.inspect(DatabaseRequest.within(30)))
        backups = Backups(database, output / "backups", key, key_id, executor, Audit(output / "audit"))
        identity = await backups.create(release)
        restored = output / "restore/restored-candidate.db"
        selected = await backups.restore(restored, release, candidates=(identity,))
        reader = SqliteDatabase(DatabaseConfig(restored))
        try:
            await reader.start()
            after = require_valid(await reader.inspect(DatabaseRequest.within(30)))
            if (before.counts != after.counts or before.data_checksum != after.data_checksum
                    or before.migration_version != 5 or after.migration_version != 5):
                raise ValueError("Restored data differs")
        finally:
            await reader.stop()
        artifact = output / "backups" / (identity + ".enc")
        evidence["recovery"] = {"identity": selected, "key_id": key_id, "release": release,
                                "encrypted_artifact": fingerprint(artifact), "restored": fingerprint(restored),
                                "schema": 5, "semantic_reconciliation": "pass", "isolated_open_close": "pass"}
        restored.chmod(0o400)
        evidence["backup_restore"] = "verified"
        evidence["status"] = "candidate_and_recovery_verified_not_promoted"
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)
    if fingerprint(candidate) != evidence["candidate"]:
        raise ValueError("Candidate changed during backup")
    atomic_json(output / "evidence.json", evidence)
    return evidence


async def preserve_recovery(output: Path, key_file: Path, key_id: str, release: str) -> dict:
    """Also preserve a verified encrypted schema-zero recovery point for V1 reconciliation."""
    if key_file.name.startswith(".env"):
        raise ValueError("No dotenv inputs")
    evidence = json.loads((output / "evidence.json").read_text())
    preserved = output / "preserved-original.db"
    standalone(preserved)
    if (evidence.get("status") not in {"migration_verified", "candidate_and_recovery_verified_not_promoted"}
            or fingerprint(preserved) != evidence["source_before"]):
        raise ValueError("Verified unchanged preservation copy required")
    key = read_secret(key_file.parent, key_file.name).encode()
    from cryptography.fernet import Fernet
    Fernet(key)
    recovery_root = output / "preservation-recovery"
    recovery_root.mkdir(mode=0o700)
    artifact = recovery_root / "pre-migration.enc"
    restored = recovery_root / "restored-v1.db"
    with tempfile.TemporaryDirectory(prefix="working-", dir=recovery_root) as temporary:
        working = Path(temporary) / "v1-working.db"
        durable_copy(preserved, working)
        database = SqliteDatabase(DatabaseConfig(working))
        try:
            before = await DataRecovery(database).backup(artifact, key, DatabaseRequest.within(60))
            after = await DataRecovery(database).restore_copy(RecoveryCandidate(artifact, key), restored,
                                                             DatabaseRequest.within(60))
            if (before.counts, before.data_checksum, before.metadata_checksum, before.migration_version) != (
                    after.counts, after.data_checksum, after.metadata_checksum, after.migration_version):
                raise ValueError("Preservation restore differs")
            if before.migration_version != evidence["validation"]["version_before"]:
                raise ValueError("Preservation schema differs")
        finally:
            await database.stop()
    restored.chmod(0o400)
    if fingerprint(preserved) != evidence["source_before"]:
        raise ValueError("Preservation copy changed")
    evidence["preservation_recovery"] = {"key_id": key_id, "release": release,
            "encrypted_artifact": fingerprint(artifact), "restored": fingerprint(restored),
            "schema": after.migration_version, "semantic_reconciliation": "pass"}
    atomic_json(output / "evidence.json", evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "recovery", "preservation"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--authoritative-source-confirmed", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--key-id")
    parser.add_argument("--release")
    args = parser.parse_args()
    scratch = Path(__file__).resolve().parents[1] / "scratch"
    output = args.output.resolve()
    if not output.is_relative_to(scratch) or output == scratch:
        parser.error("Use an isolated run directory under ignored scratch")
    logging.disable(logging.CRITICAL)
    try:
        if args.command == "prepare":
            if not args.source or not args.authoritative_source_confirmed:
                raise ValueError("Explicit source confirmation required")
            evidence = asyncio.run(prepare(args.source.absolute(), output))
        else:
            if not args.key_file or not args.key_id or not args.release:
                raise ValueError("Explicit key file, key identity and release required")
            operation = recover if args.command == "recovery" else preserve_recovery
            evidence = asyncio.run(operation(output, args.key_file.absolute(), args.key_id, args.release))
        print(json.dumps(evidence, ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "production_promoted": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
