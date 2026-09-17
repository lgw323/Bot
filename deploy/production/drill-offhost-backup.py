"""One approved Bot-Data upload/download drill; no runtime config or timer activation."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

WORK = Path("/home/os/discordbot-phase10")
ROOT = Path("/var/lib/discordbot")
RUN = ROOT / "phase10-offhost-20260917-01"
RECOVERY = ROOT / "phase10-recovery-20260916-01"
RELEASE = "r-672694d3f0c5418e-d026a47ed4f4b38a"
IDENTITY = "20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71"
CHECKSUM = "3dcaf8eafd9cb33309531e556593dc4a968b3696df2f9236b254625ce1b43766"
CONFIG = Path("/etc/discordbot/production-candidate/config.json")
CONFIG_HASH = "5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3"


def checked(arguments: list[str], timeout: int = 30) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Off-host drill stopped; raw output withheld")
    return result.stdout


def source() -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path("/opt/discordbot/releases") / RELEASE / "app/src"))


def credentials(names: set[str]) -> Path:
    root = Path(os.environ["CREDENTIALS_DIRECTORY"])
    if (set(p.name for p in root.iterdir()) != names
            or not str(root).startswith("/run/credentials/")
            or not os.statvfs(root).f_flag & os.ST_RDONLY):
        raise ValueError("Exact read-only systemd credential scope required")
    return root


def upload() -> None:
    from discordbot.operations.adapters.filesystem import atomic_json
    scoped = credentials({"backup_ssh_key", "known_hosts"})
    spec = importlib.util.spec_from_file_location("reviewed_git_backup", RUN / "git_backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    transport = module.GitTransport(scoped / "backup_ssh_key", scoped / "known_hosts")
    store = module.GitBackupStore(transport, RUN / "transport")
    published = store.publish(RUN / "incoming" / (IDENTITY + ".enc"), CHECKSUM, IDENTITY)
    downloaded = store.download(IDENTITY, RUN / "downloaded")
    if downloaded["sha256"] != CHECKSUM:
        raise ValueError("Remote download mismatch")
    atomic_json(RUN / "upload-result.json", {"published": published, "downloaded": downloaded,
                "scope": "backup_ssh_only", "automatic_backup_enabled": False})


async def restore() -> None:
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.filesystem import atomic_json, digest
    from discordbot.operations.adapters.recovery import Backups
    from discordbot.platform.executors import BoundedExecutor
    from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
    from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
    scoped = credentials({"db_key"})
    settings = load_settings(CONFIG, scoped, "operations")
    candidate = RUN / "restored/remote-candidate.db"
    database = SqliteDatabase(DatabaseConfig(candidate))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="offhost-drill")
    try:
        backups = Backups(database, RUN / "downloaded", settings.secrets.db_key,
                          settings.key_id, executor, Audit(RUN / "audit"))
        await backups.restore(candidate, RELEASE, candidates=(IDENTITY,))
        await database.start()
        report = require_valid(await database.inspect(DatabaseRequest.within(30)))
        counts = {"users": 15, "favorites": 40, "music_settings": 1, "music_play_counts": 50,
                  "watch_sessions": 0, "watch_playlists": 0}
        if report.migration_version != 5 or dict(report.counts) != counts:
            raise ValueError("Restored aggregate mismatch")
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)
    atomic_json(RUN / "restore-result.json", {"schema": 5, "counts": counts, "key_id": settings.key_id,
                "decrypt_checksum_application_open_close": "pass", "candidate_sha256": digest(candidate),
                "production_promoted": False, "scope": "db_key_only_no_network"})


def parent() -> None:
    import grp
    import pwd
    if os.geteuid() != 0:
        raise ValueError("Interactive sudo required")
    from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
    if (not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file()
            or checked(["systemctl", "show", "discord-bot", "-p", "ActiveState", "--value"]).strip() != "inactive"
            or read_json(WORK / "recovery-progress.json")["stage"] != "verified_not_promoted"
            or digest(CONFIG) != CONFIG_HASH):
        raise ValueError("Reviewed 10A state required")
    artifact = RECOVERY / "backups" / (IDENTITY + ".enc")
    if digest(artifact) != CHECKSUM:
        raise ValueError("Reviewed backup changed")
    previous = Path("/opt/discordbot/current").resolve(strict=True)
    canonical_inode = (ROOT / "data/bot_database.db").stat().st_ino
    RUN.mkdir(mode=0o750)
    for name in ("incoming", "transport", "restored", "audit"):
        (RUN / name).mkdir(mode=0o700)
    for item in (artifact, artifact.with_suffix(".json")):
        shutil.copyfile(item, RUN / "incoming" / item.name)
    for item in (Path(__file__), WORK / "git_backup.py"):
        shutil.copyfile(item, RUN / item.name)
    uid = pwd.getpwnam("discordbot-deploy").pw_uid
    gid = grp.getgrnam("discordbot").gr_gid
    for item in (RUN, *RUN.rglob("*")):
        os.chown(item, uid, gid)
        item.chmod(0o700 if item.is_dir() else 0o600)
    progress = WORK / "offhost-progress.json"
    result = {"remote": "git@github.com:lgw323/Bot-Data.git", "ref": "refs/heads/db-backup",
              "production_promoted": False, "automatic_backup_enabled": False}
    stage = "upload_download"
    try:
        atomic_json(progress, dict(result, stage=stage))
        python = Path("/opt/discordbot/releases") / RELEASE / ".venv/bin/python"
        common = ["systemd-run", "--wait", "--pipe", "--collect", "-p", "User=discordbot-deploy",
                  "-p", "Group=discordbot", "-p", "UMask=0077", "-p", "ProtectSystem=strict",
                  "-p", "ProtectHome=yes", "-p", "NoNewPrivileges=yes", "-p", "RuntimeMaxSec=600",
                  "-p", "ReadWritePaths=" + str(RUN)]
        ssh_root = Path("/etc/discordbot/backup-ssh-candidate")
        checked([*common, "--unit=discordbot-phase10-offhost-upload",
                 "-p", "LoadCredential=backup_ssh_key:" + str(ssh_root / "id_ed25519"),
                 "-p", "LoadCredential=known_hosts:" + str(ssh_root / "known_hosts"),
                 str(python), "-I", "-B", str(RUN / Path(__file__).name), "--upload"], 630)
        result["transport"] = read_json(RUN / "upload-result.json")
        stage = "offline_download_restore"
        atomic_json(progress, dict(result, stage=stage))
        checked([*common, "--unit=discordbot-phase10-offhost-restore", "-p", "PrivateNetwork=yes",
                 "-p", "LoadCredential=db_key:" + str(CONFIG.parent / "secrets/db_key"),
                 str(python), "-I", "-B", str(RUN / Path(__file__).name), "--restore"], 180)
        result["restore"] = read_json(RUN / "restore-result.json")
        if (previous != Path("/opt/discordbot/current").resolve(strict=True)
                or canonical_inode != (ROOT / "data/bot_database.db").stat().st_ino
                or digest(CONFIG) != CONFIG_HASH):
            raise ValueError("Reviewed host state changed")
        atomic_json(progress, dict(result, stage="verified_not_enabled"))
        progress.chmod(0o644)
        print("Off-host upload/download/isolated restore: PASS. Automatic backup remains disabled.")
    except BaseException as error:
        atomic_json(progress, dict(result, stage="failed", failed_stage=stage, error_type=type(error).__name__))
        progress.chmod(0o644)
        print("Off-host drill stopped. See safe offhost-progress.json; no automatic activation.")
        raise SystemExit(1) from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--upload", action="store_true")
    group.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    source()
    if args.upload:
        upload()
    elif args.restore:
        asyncio.run(restore())
    else:
        parent()


if __name__ == "__main__":
    main()
