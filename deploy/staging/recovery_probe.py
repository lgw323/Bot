"""Synthetic installed backup/restore drill; no production data or remote destination."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/var/lib/discordbot")
WORK = Path("/home/os/discordbot-phase9")
DRILL = ROOT / "state/recovery-drill"


async def worker() -> None:
    sys.dont_write_bytecode = True
    release = Path("/opt/discordbot/current").resolve(strict=True)
    sys.path.insert(0, str(release / "app/src"))
    from cryptography.fernet import Fernet
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.filesystem import ExclusiveLock, atomic_json, digest, read_json
    from discordbot.operations.adapters.recovery import Backups
    from discordbot.platform.errors import DataIntegrityError
    from discordbot.platform.executors import BoundedExecutor
    from discordbot.storage.adapters.execution import SqliteDatabase
    from discordbot.storage.ports.contracts import DatabaseConfig

    settings = load_settings(Path("/etc/discordbot/config.json"),
                             Path(os.environ["CREDENTIALS_DIRECTORY"]), "operations")
    DRILL.mkdir(mode=0o700)  # Refuse to overwrite any prior drill.
    (DRILL / "archives").mkdir(mode=0o700)
    database = SqliteDatabase(DatabaseConfig(settings.database))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="staging-recovery")
    audit = Audit(settings.audit)
    evidence = {"release": release.name, "synthetic_only": True}
    try:
        with ExclusiveLock(settings.operation_lock).acquire():
            await database.start()
            real = Backups(database, settings.backups, settings.secrets.db_key, settings.key_id, executor, audit)
            start = time.monotonic()
            first = await real.create(release.name)
            evidence["online_backup_seconds"] = round(time.monotonic()-start, 3)
            second = await real.create(release.name)
            evidence["archive_bytes"] = (settings.backups / (second + ".enc")).stat().st_size
            evidence["archive_mode"] = oct((settings.backups / (second + ".enc")).stat().st_mode & 0o777)
            for identity in (first, second):
                for suffix in (".enc", ".json"):
                    shutil.copyfile(settings.backups / (identity + suffix), DRILL / "archives" / (identity + suffix))
            fault = Backups(database, DRILL / "archives", settings.secrets.db_key, settings.key_id, executor, audit)
            start = time.monotonic()
            selected = await fault.restore(DRILL / "candidate.db", release.name, candidates=(second, first))
            evidence["newest_restore_seconds"] = round(time.monotonic()-start, 3)
            evidence["newest_selected"] = selected == second
            archive = fault.root / (second + ".enc")
            original = archive.read_bytes()
            archive.write_bytes(b"synthetic-corrupt-archive")
            start = time.monotonic()
            evidence["fallback_selected_previous"] = await fault.restore(DRILL / "fallback.db", release.name,
                                                                         candidates=(second, first)) == first
            evidence["fallback_seconds"] = round(time.monotonic()-start, 3)
            archive.write_bytes(original)
            for case in ("wrong_key", "tamper", "schema"):
                record = read_json(fault.root / (second + ".json"))
                original_record = dict(record)
                if case == "wrong_key":
                    fault.key = Fernet.generate_key()
                elif case == "tamper":
                    archive.write_bytes(original[:-8] + b"tampered")
                    record["sha256"] = digest(archive)
                else:
                    record["schema"] = 99
                atomic_json(fault.root / (second + ".json"), record)
                destination = DRILL / (case + ".db")
                try:
                    await fault.restore(destination, release.name, candidates=(second,))
                except DataIntegrityError:
                    evidence[case + "_rejected"] = not destination.exists()
                else:
                    raise RuntimeError("Invalid synthetic backup accepted")
                fault.key = settings.secrets.db_key
                archive.write_bytes(original)
                atomic_json(fault.root / (second + ".json"), original_record)
            for _ in range(8):
                await real.create(release.name)
            evidence["retained_archives"] = len(list(settings.backups.glob("*.enc")))
            if evidence["retained_archives"] != 8:
                raise RuntimeError("Retention count differs")
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)
    atomic_json(DRILL / "result.json", evidence)


def main() -> None:
    if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Synthetic installation required")
    if "--worker" in sys.argv:
        asyncio.run(worker())
        return
    if os.geteuid() != 0:
        raise RuntimeError("Interactive sudo required")
    tool = ROOT / "staging-tools/recovery_probe.py"
    if tool.exists():
        raise RuntimeError("Existing drill helper requires reconciliation")
    shutil.copyfile(Path(__file__), tool)
    tool.chmod(0o644)
    # Exercise the installed production backup entrypoint before the isolated fault drill.
    start = time.monotonic()
    result = subprocess.run(["systemctl", "start", "discordbot-backup"], capture_output=True, text=True, timeout=190)
    evidence = {"oneshot_returncode": result.returncode, "oneshot_seconds": round(time.monotonic()-start, 3)}
    if result.returncode == 0:
        command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-recovery-probe",
                   "--property=User=discordbot-deploy", "--property=Group=discordbot", "--property=UMask=0077",
                   "--property=LoadCredential=db_key:/etc/discordbot/secrets/db_key",
                   "--property=RuntimeMaxSec=600", "--property=TimeoutStopSec=30",
                   "/opt/discordbot/current/.venv/bin/python", "-I", "-B", str(tool), "--worker"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=650)
        evidence["drill_returncode"] = result.returncode
        if result.returncode == 0:
            evidence["drill"] = json.loads((DRILL / "result.json").read_text())
    evidence["diagnostic"] = result.stderr[-3000:]
    path = WORK / "recovery-result.json"
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)


if __name__ == "__main__":
    main()
