"""Promote only the verified synthetic drill candidate with both staging services stopped."""

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
UNITS = ("discordbot-staging-discord", "watch-web")


def worker() -> None:
    sys.dont_write_bytecode = True
    release = Path("/opt/discordbot/current").resolve(strict=True)
    sys.path.insert(0, str(release / "app/src"))
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.cli import validate_candidate
    from discordbot.operations.adapters.filesystem import ExclusiveLock, digest
    from discordbot.operations.adapters.recovery import promote
    candidate = ROOT / "state/recovery-drill/candidate.db"
    with ExclusiveLock(ROOT / "operations.lock").acquire():
        for unit in UNITS:
            state = subprocess.run(["systemctl", "show", unit, "--property=ActiveState", "--value"],
                                   check=True, capture_output=True, text=True, timeout=10)
            if state.stdout.strip() != "inactive":
                raise RuntimeError("Both synthetic services must be stopped")
        asyncio.run(validate_candidate(candidate))
        promote(candidate, ROOT / "data/bot_database.db", digest(candidate), stopped=True,
                audit=Audit(ROOT / "audit"), release=release.name)


def main() -> None:
    if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Synthetic installation required")
    if "--worker" in sys.argv:
        worker()
        return
    if os.geteuid() != 0:
        raise RuntimeError("Interactive sudo required")
    # Refuse overlap with any deployment or backup rather than force-stop it.
    for unit in ("discordbot-stage-release", "discordbot-backup", "discordbot-recovery-probe"):
        result = subprocess.run(["systemctl", "show", unit, "--property=ActiveState", "--value"],
                                check=True, capture_output=True, text=True, timeout=10)
        if result.stdout.strip() not in {"inactive", "failed"}:
            raise RuntimeError("Another staging operation is active")
    if not (ROOT / "backups/latest.json").is_file():
        raise RuntimeError("Existing verified synthetic backup required")
    tool = ROOT / "staging-tools/promotion_probe.py"
    if tool.exists():
        raise RuntimeError("Existing promotion helper requires reconciliation")
    shutil.copyfile(Path(__file__), tool)
    tool.chmod(0o644)
    start = time.monotonic()
    subprocess.run(["systemctl", "stop", *UNITS], check=True, timeout=100)
    result = subprocess.run(["runuser", "-u", "discordbot-deploy", "--",
                             "/opt/discordbot/current/.venv/bin/python", "-I", "-B", str(tool), "--worker"],
                            capture_output=True, text=True, timeout=120)
    evidence = {"promotion_returncode": result.returncode, "seconds": round(time.monotonic()-start, 3),
                "synthetic_only": True, "diagnostic": result.stderr[-3000:]}
    if result.returncode == 0:
        subprocess.run(["systemctl", "start", *UNITS], check=True, timeout=100)
    path = WORK / "promotion-result.json"
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)


if __name__ == "__main__":
    main()
