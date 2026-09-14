"""Explicit clean staging reboot after successful local readiness and backup checks."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def main() -> None:
    root = Path("/var/lib/discordbot")
    work = Path("/home/os/discordbot-phase9")
    if os.geteuid() != 0 or not (root / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Interactive sudo and synthetic staging required")
    release = Path("/opt/discordbot/current").resolve(strict=True).name
    for unit in ("discordbot-stage-release", "discordbot-backup", "discordbot-recovery-probe"):
        state = subprocess.run(["systemctl", "show", unit, "--property=ActiveState", "--value"],
                               check=True, capture_output=True, text=True, timeout=10)
        if state.stdout.strip() not in {"inactive", "failed"}:
            raise RuntimeError("Another operation is active")
    opener = build_opener(ProxyHandler({}))
    for port in (9010, 9011):
        with opener.open(f"http://127.0.0.1:{port}/health/ready", timeout=2) as response:
            health = json.loads(response.read(8192))
        if not health.get("ready") or health.get("release") != release:
            raise RuntimeError("Staging pair is not coherent")
    promotion = json.loads((work / "promotion-result.json").read_text())
    recovery = json.loads((work / "recovery-result.json").read_text())
    if promotion["promotion_returncode"] != 0 or recovery["drill_returncode"] != 0:
        raise RuntimeError("Recovery/promotion evidence required")
    units = ("watch-web.service", "discordbot-staging-discord.service", "discordbot-backup.timer")
    assets = [str(Path("/etc/systemd/system") / name) for name in (*units, "discordbot-backup.service", "discordbot-update.timer")]
    subprocess.run(["systemd-analyze", "verify", *assets], check=True, capture_output=True, timeout=30)
    subprocess.run(["systemctl", "enable", *units], check=True, capture_output=True, timeout=30)
    subprocess.run(["systemctl", "start", "discordbot-backup.timer"], check=True, capture_output=True, timeout=30)
    timer = subprocess.run(["systemctl", "show", "discordbot-backup.timer", "-p", "NextElapseUSecRealtime",
                            "-p", "LastTriggerUSec", "-p", "Persistent", "-p", "ActiveState"],
                           check=True, capture_output=True, text=True, timeout=10)
    # Persistent activation may trigger a missed backup; let the finite oneshot finish before reboot.
    deadline = time.monotonic() + 190
    while True:
        result = subprocess.run(["systemctl", "show", "discordbot-backup", "--property=ActiveState", "--value"],
                                check=True, capture_output=True, text=True, timeout=10)
        if result.stdout.strip() == "inactive":
            break
        if time.monotonic() >= deadline or result.stdout.strip() == "failed":
            raise RuntimeError("Backup did not finish before reboot")
        time.sleep(1)
    evidence = {"boot_id_before": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "release": release, "timer": timer.stdout, "time": time.time(),
                "enabled": units, "production_discord_enabled": False, "update_timer_enabled": False}
    path = work / "reboot-before.json"
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)
    subprocess.run(["systemctl", "reboot"], check=True, timeout=30)


if __name__ == "__main__":
    main()
