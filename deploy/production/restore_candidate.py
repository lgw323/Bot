"""10A approved encrypted-input restore to a NEW private path. No canonical operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

WORK = Path("/home/os/discordbot-phase10")
ROOT = Path("/var/lib/discordbot")
RUN = ROOT / "phase10-recovery-20260916-01"
IDENTITY = "20260915T015843161244-45854a29b85740c9b605da6163980095"
CHECKSUM = "be2bc99031d64c6a6c59303bbaedb33b9647190a42fbf40921d3ccc53c850454"
COUNTS = {"users": 15, "favorites": 40, "music_settings": 1, "music_play_counts": 50,
          "watch_sessions": 0, "watch_playlists": 0}
CONFIG = Path("/etc/discordbot/production-candidate/config.json")


def checked(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Isolated verification failed")
    return result.stdout


def digest(path: Path) -> str:
    import hashlib
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("Linked evidence refused")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o644)
    temporary.replace(path)


def report_valid(report) -> None:
    if report.migration_version != 5 or dict(report.counts) != COUNTS:
        raise ValueError("Reviewed production aggregates differ")


async def worker(release: str, reader_only: bool) -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path("/opt/discordbot/releases") / release / "app/src"))
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.recovery import Backups
    from discordbot.platform.executors import BoundedExecutor
    from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
    from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
    candidate = RUN / "restored/candidate.db"
    database = SqliteDatabase(DatabaseConfig(candidate))
    if reader_only:
        try:
            await database.start()
            report_valid(require_valid(await database.inspect(DatabaseRequest.within(30))))
        finally:
            await database.stop()
        print(json.dumps({"runtime_user_open_close": "pass", "schema": 5}))
        return
    settings = load_settings(CONFIG, Path(os.environ["CREDENTIALS_DIRECTORY"]), "operations")
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="candidate-recovery")
    audit = Audit(RUN / "audit")
    result = {"release": release, "production_promoted": False, "key_id": settings.key_id}
    started = time.monotonic()
    try:
        incoming = Backups(database, RUN / "incoming", settings.secrets.db_key, settings.key_id, executor, audit)
        # Backups.restore opens only NEW isolated paths. It never starts its source database.
        selected = await incoming.restore(candidate, release, candidates=(IDENTITY,))
        result["input_identity"] = selected
        await database.start()
        before = require_valid(await database.inspect(DatabaseRequest.within(30)))
        report_valid(before)
        produced = Backups(database, RUN / "backups", settings.secrets.db_key, settings.key_id, executor, audit)
        created = await produced.create(release)
        repeated = RUN / "restored/roundtrip.db"
        await produced.restore(repeated, release, candidates=(created,))
        second = SqliteDatabase(DatabaseConfig(repeated))
        try:
            await second.start()
            after = require_valid(await second.inspect(DatabaseRequest.within(30)))
            report_valid(after)
            if (before.data_checksum, before.metadata_checksum, before.counts) != (
                    after.data_checksum, after.metadata_checksum, after.counts):
                raise ValueError("Roundtrip data differs")
        finally:
            await second.stop()
        result.update(schema=5, counts=dict(before.counts), semantic_reconciliation="pass",
                      backup_identity=created, backup_sha256=digest(RUN / "backups" / (created + ".enc")))
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)
    candidate.chmod(0o660)
    result.update(candidate_sha256=digest(candidate), seconds=round(time.monotonic() - started, 3))
    record(RUN / "result.json", result)


def parent(release: str) -> None:
    import grp
    import pwd
    if os.geteuid() != 0:
        raise ValueError("Interactive sudo required")
    evidence = {"release": release, "production_promoted": False, "production_started": False}
    progress = WORK / "recovery-progress.json"
    stage = "admission"
    try:
        record(progress, dict(evidence, stage=stage))
        verification = json.loads((WORK / "verification-progress.json").read_text())
        if (verification.get("stage") != "verified_not_activated"
                or verification["build"]["release"] != release
                or verification["candidate_config_sha256"] != digest(CONFIG)):
            raise ValueError("Verified config/release required")
        if (not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file()
                or checked(["systemctl", "show", "discord-bot", "-p", "ActiveState", "--value"]).strip() != "inactive"):
            raise ValueError("10A host boundary changed")
        previous = Path("/opt/discordbot/current").resolve(strict=True)
        canonical_inode = (ROOT / "data/bot_database.db").stat().st_ino
        original = WORK / "recovery-input" / (IDENTITY + ".enc")
        if original.is_symlink() or digest(original) != CHECKSUM:
            raise ValueError("Approved encrypted payload differs")
        record_source = original.with_suffix(".json")
        metadata = json.loads(record_source.read_text())
        if metadata.get("identity") != IDENTITY or metadata.get("sha256") != CHECKSUM or metadata.get("schema") != 5:
            raise ValueError("Backup metadata differs")
        RUN.mkdir(mode=0o750)
        uid = pwd.getpwnam("discordbot-deploy").pw_uid
        gid = grp.getgrnam("discordbot").gr_gid
        for name in ("incoming", "restored", "backups", "audit"):
            (RUN / name).mkdir(mode=0o750)
        for source in (original, record_source):
            shutil.copyfile(source, RUN / "incoming" / source.name)
        helper = RUN / "restore_candidate.py"
        shutil.copyfile(__file__, helper)
        for path in (RUN, *RUN.rglob("*")):
            os.chown(path, uid, gid)
            path.chmod(0o750 if path.is_dir() else 0o640)
        helper.chmod(0o644)
        (RUN / "restored").chmod(0o2770)
        stage = "isolated_restore_backup_roundtrip"
        record(progress, dict(evidence, stage=stage))
        python = Path("/opt/discordbot/releases") / release / ".venv/bin/python"
        command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-phase10-recovery",
                   "-p", "User=discordbot-deploy", "-p", "Group=discordbot", "-p", "UMask=0007",
                   "-p", "PrivateNetwork=yes", "-p", "ProtectSystem=strict", "-p", "ProtectHome=yes",
                   "-p", "NoNewPrivileges=yes", "-p", "RuntimeMaxSec=300", "-p", "ReadWritePaths=" + str(RUN),
                   "-p", "LoadCredential=db_key:" + str(CONFIG.parent / "secrets/db_key"),
                   str(python), "-I", "-B", str(helper), "--release", release, "--worker"]
        checked(command, 330)
        evidence["recovery"] = json.loads((RUN / "result.json").read_text())
        stage = "runtime_user_open_close"
        record(progress, dict(evidence, stage=stage))
        # No credentials or network for the independent runtime-user reader.
        command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-phase10-reader",
                   "-p", "User=discordbot", "-p", "Group=discordbot", "-p", "UMask=0007",
                   "-p", "PrivateNetwork=yes", "-p", "ProtectSystem=strict", "-p", "ProtectHome=yes",
                   "-p", "NoNewPrivileges=yes", "-p", "RuntimeMaxSec=60", "-p", "ReadWritePaths=" + str(RUN / "restored"),
                   str(python), "-I", "-B", str(helper), "--release", release, "--reader"]
        evidence["reader"] = json.loads(checked(command, 80))
        evidence["candidate_unchanged"] = digest(RUN / "restored/candidate.db") == evidence["recovery"]["candidate_sha256"]
        evidence["current_unchanged"] = previous == Path("/opt/discordbot/current").resolve(strict=True)
        evidence["canonical_inode_unchanged"] = canonical_inode == (ROOT / "data/bot_database.db").stat().st_ino
        if not all(evidence[name] for name in ("candidate_unchanged", "current_unchanged", "canonical_inode_unchanged")):
            raise ValueError("Reviewed state changed")
        record(progress, dict(evidence, stage="verified_not_promoted"))
        print("Isolated production candidate recovery verified. Canonical DB and running services unchanged.")
    except BaseException as error:
        record(progress, dict(evidence, stage="failed", failed_stage=stage, error_type=type(error).__name__))
        print("Recovery verification stopped; inspect safe recovery-progress.json. No promotion was attempted.")
        raise SystemExit(1) from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--worker", action="store_true")
    group.add_argument("--reader", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", args.release):
        raise SystemExit("Reviewed release required")
    if args.worker or args.reader:
        asyncio.run(worker(args.release, args.reader))
    else:
        parent(args.release)


if __name__ == "__main__":
    main()
