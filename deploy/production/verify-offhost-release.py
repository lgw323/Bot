"""Build the reviewed source and exercise opt-in backup on an isolated DB copy."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path("/var/lib/discordbot")
WORK = Path("/home/os/discordbot-phase10")
SOURCE_CONFIG = Path("/etc/discordbot/production-candidate/config.json")
SOURCE_DB = ROOT / "phase10-recovery-20260916-01/restored/candidate.db"
DB_HASH = "8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b"
REMOTE_CONFIG = {"kind": "git-ssh", "repository": "git@github.com:lgw323/Bot-Data.git", "ref": "refs/heads/db-backup"}


def checked(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Isolated verification failed; raw output withheld")
    return result.stdout


def source(release: str) -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path("/opt/discordbot/releases") / release / "app/src"))


async def worker(run: Path, release: str) -> None:
    source(release)
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.deployment import backup_once
    from discordbot.operations.adapters.filesystem import atomic_json, read_json
    from discordbot.operations.adapters.git_backup import GitBackupStore, GitTransport
    from discordbot.operations.adapters.recovery import Backups
    from discordbot.platform.executors import BoundedExecutor
    from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
    from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
    credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
    if (set(p.name for p in credentials.iterdir()) != {"db_key", "backup_ssh_key", "known_hosts"}
            or not os.statvfs(credentials).f_flag & os.ST_RDONLY):
        raise ValueError("Scoped read-only credentials required")
    settings = load_settings(run / "config.json", credentials, "operations")
    database = SqliteDatabase(DatabaseConfig(settings.database))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="offhost-readback")
    audit = Audit(settings.audit)
    restored = SqliteDatabase(DatabaseConfig(run / "restored/remote.db"))
    try:
        await database.start()
        before = require_valid(await database.inspect(DatabaseRequest.within(20)))
        await database.stop()
        identity = await backup_once(settings, audit, release)
        remote = settings.backup_remote
        def download():
            transport = GitTransport(remote.key_file, remote.known_hosts_file)
            return GitBackupStore(transport, remote.workspace).download(identity, run / "downloaded")
        downloaded = await executor.run(download)
        backups = Backups(restored, run / "downloaded", settings.secrets.db_key, settings.key_id, executor, audit)
        await backups.restore(restored.config.path, release, candidates=(identity,))
        await restored.start()
        after = require_valid(await restored.inspect(DatabaseRequest.within(20)))
        if (before.data_checksum, before.metadata_checksum, before.counts, before.migration_version) != (
                after.data_checksum, after.metadata_checksum, after.counts, after.migration_version):
            raise ValueError("Remote restore semantic mismatch")
        if read_json(settings.backups / "latest.json")["identity"] != identity:
            raise ValueError("Successful remote backup did not advance latest")
        atomic_json(run / "result.json", {"release": release, "remote": downloaded, "schema": after.migration_version,
                    "counts": dict(after.counts), "semantic_reconciliation": "pass", "runtime_backup_entrypoint": "pass",
                    "readonly_credential_scope": ["db_key", "backup_ssh_key", "known_hosts"], "production_enabled": False})
    finally:
        await database.stop()
        await restored.stop()
        await executor.close(grace_seconds=95)


def observation_details() -> dict:
    path = ROOT / "phase10-observation-20260915/samples.jsonl"
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        return {"status": "unavailable"}
    samples = [json.loads(line) for line in path.read_text().splitlines()]
    errors: Counter[str] = Counter()
    throttling: Counter[str] = Counter()
    for item in samples:
        for error in item["errors"]:
            if re.fullmatch(r"(?:9010|9011):[A-Za-z]+Error", error):
                errors[error] += 1
            else:
                errors["other_collection_error"] += 1
        raw = item["throttling"]
        match = re.fullmatch(r"(?:throttled=)?(0x[0-9a-fA-F]+|[0-9]+)", raw)
        throttling[str(int(match[1], 0)) if match else "unparsed"] += 1
    drops = []
    for before, after in zip(samples, samples[1:]):
        delta = after["disk_free_bytes"] - before["disk_free_bytes"]
        if delta < 0:
            drops.append({"time_unix": after["time_unix"], "free_delta_bytes": delta,
                          "backup_bytes_delta": after.get("backups", {}).get("bytes", 0) - before.get("backups", {}).get("bytes", 0),
                          "audit_bytes_delta": after.get("audit", {}).get("bytes", 0) - before.get("audit", {}).get("bytes", 0)})
    return {"samples": len(samples), "collection_errors": dict(errors), "throttling_numeric_values": dict(throttling),
            "largest_free_space_drops": sorted(drops, key=lambda value: value["free_delta_bytes"])[:5]}


def parent(commit: str, archive_sha256: str) -> None:
    import grp
    import pwd
    if os.geteuid() != 0:
        raise ValueError("Interactive sudo required")
    before = Path("/opt/discordbot/current").resolve(strict=True)
    source(before.name)
    from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
    if (not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file()
            or checked(["systemctl", "show", "discord-bot", "-p", "ActiveState", "--value"]).strip() != "inactive"
            or read_json(WORK / "offhost-progress.json")["stage"] != "verified_not_enabled"
            or digest(SOURCE_DB) != DB_HASH):
        raise ValueError("Reviewed 10A state required")
    run = ROOT / ("phase10-offhost-wiring-" + commit[:12])
    run.mkdir(mode=0o750)
    progress = WORK / "offhost-wiring-progress.json"
    result = {"commit": commit, "production_enabled": False}
    stage = "offline_build"
    try:
        atomic_json(progress, dict(result, stage=stage))
        config_hash = digest(SOURCE_CONFIG)
        canonical_inode = (ROOT / "data/bot_database.db").stat().st_ino
        # Preserve earlier build evidence before the existing verifier publishes its new result.
        shutil.copyfile(WORK / "verification-progress.json", run / "previous-verification.json")
        checked(["python3", "-I", str(WORK / "verify_candidate.py"), "--commit", commit,
                 "--archive-sha256", archive_sha256, "--run", str(ROOT / ("phase10-readiness-" + commit[:12]))], 1400)
        verified = read_json(WORK / "verification-progress.json")
        if verified["stage"] != "verified_not_activated":
            raise ValueError("Offline release verification required")
        release = verified["build"]["release"]
        result["build"] = verified["build"]
        config = read_json(SOURCE_CONFIG)
        config["backup_remote"] = REMOTE_CONFIG
        for name in ("data", "state", "cache", "backups", "audit", "restored"):
            (run / name).mkdir(mode=0o700)
        for name in ("state", "cache", "backups", "audit"):
            config["paths"][name] = str(run / name)
        config["paths"]["database"] = str(run / "data/candidate.db")
        config["paths"]["operation_lock"] = str(run / "operations.lock")
        shutil.copyfile(SOURCE_DB, run / "data/candidate.db")
        if digest(run / "data/candidate.db") != DB_HASH:
            raise ValueError("Isolated copy changed")
        atomic_json(run / "config.json", config)
        helper = run / Path(__file__).name
        shutil.copyfile(__file__, helper)
        uid, gid = pwd.getpwnam("discordbot-deploy").pw_uid, grp.getgrnam("discordbot").gr_gid
        for item in (run, *run.rglob("*")):
            os.chown(item, uid, gid)
            item.chmod(0o700 if item.is_dir() else 0o600)
        stage = "isolated_runtime_backup"
        atomic_json(progress, dict(result, stage=stage))
        python = Path("/opt/discordbot/releases") / release / ".venv/bin/python"
        checked(["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-phase10-offhost-wiring",
                 "-p", "User=discordbot-deploy", "-p", "Group=discordbot", "-p", "UMask=0077",
                 "-p", "ProtectSystem=strict", "-p", "ProtectHome=yes", "-p", "NoNewPrivileges=yes",
                 "-p", "RuntimeMaxSec=600", "-p", "TimeoutStopSec=130", "-p", "ReadWritePaths=" + str(run),
                 "-p", "LoadCredential=db_key:" + str(SOURCE_CONFIG.parent / "secrets/db_key"),
                 "-p", "LoadCredential=backup_ssh_key:/etc/discordbot/backup-ssh-candidate/id_ed25519",
                 "-p", "LoadCredential=known_hosts:/etc/discordbot/backup-ssh-candidate/known_hosts",
                 str(python), "-I", "-B", str(helper), "--worker", "--commit", commit, "--release", release], 640)
        result["verification"] = read_json(run / "result.json")
        result["observation_details"] = observation_details()
        if (before != Path("/opt/discordbot/current").resolve(strict=True) or digest(SOURCE_CONFIG) != config_hash
                or canonical_inode != (ROOT / "data/bot_database.db").stat().st_ino):
            raise ValueError("Reviewed host state changed")
        atomic_json(progress, dict(result, stage="verified_not_activated"))
        progress.chmod(0o644)
        print("Offline build and isolated runtime off-host backup/restore: PASS. Production remains inactive.")
    except BaseException as error:
        atomic_json(progress, dict(result, stage="failed", failed_stage=stage, error_type=type(error).__name__))
        progress.chmod(0o644)
        print("Verification stopped. See safe offhost-wiring-progress.json. No activation attempted.")
        raise SystemExit(1) from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--release")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("Exact reviewed commit required")
    if args.worker:
        if not args.release or not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", args.release):
            raise SystemExit("Reviewed release required")
        asyncio.run(worker(ROOT / ("phase10-offhost-wiring-" + args.commit[:12]), args.release))
    else:
        if not args.archive_sha256 or not re.fullmatch(r"[0-9a-f]{64}", args.archive_sha256):
            raise SystemExit("Reviewed source digest required")
        parent(args.commit, args.archive_sha256)


if __name__ == "__main__":
    main()
