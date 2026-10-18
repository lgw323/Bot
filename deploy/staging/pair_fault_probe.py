"""Actual local split-release/readiness faults, with a bounded restoration of the synthetic pair."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


RESULT = Path("/home/os/discordbot-phase9/pair-fault-result.json")


def record(stage: str, **fields) -> None:
    RESULT.write_text(json.dumps({"stage": stage, **fields}, indent=2))
    RESULT.chmod(0o644)


def main() -> None:
    root = Path("/var/lib/discordbot")
    if os.geteuid() != 0 or not (root / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Interactive sudo and synthetic installation required")
    sys.dont_write_bytecode = True
    current = Path("/opt/discordbot/current").resolve(strict=True)
    previous = Path("/opt/discordbot/releases/r-bb0fca6cf8b97586-d026a47ed4f4b38a")
    if current == previous or not previous.is_dir():
        raise RuntimeError("Two previously verified distinct releases required")
    sys.path.insert(0, str(current / "app/src"))
    from discordbot.operations.adapters.build import CommandRunner
    from discordbot.operations.adapters.deployment import Services
    from discordbot.platform.errors import ExternalTemporaryError
    services = Services(CommandRunner(), current, (9010, 9011))
    record("initial_readiness")
    services.ready(current.name, timeout=70)
    evidence = {"current": current.name, "alternate": previous.name, "synthetic_only": True}
    command = lambda args: subprocess.run(args, check=True, capture_output=True, text=True, timeout=100)
    child_started = False
    try:
        record("split_probe_starting")
        command(["systemctl", "stop", "discordbot-staging-discord"])
        code = ("import asyncio,runpy; from pathlib import Path; "
                "m=runpy.run_path('/var/lib/discordbot/staging-tools/local_discord.py'); "
                f"asyncio.run(m['run'](Path({str(previous)!r})))")
        command(["systemd-run", "--collect", "--unit=discordbot-split-probe", "--property=User=discordbot",
                 "--property=Group=discordbot", "--property=RuntimeMaxSec=120", "--property=TimeoutStopSec=90",
                 "--property=NoNewPrivileges=yes", "--property=ProtectSystem=strict", "--property=ProtectHome=yes",
                 "--property=ReadWritePaths=/var/lib/discordbot/data", "--property=UMask=0077",
                 str(previous / ".venv/bin/python"), "-I", "-B", "-c", code])
        child_started = True
        deadline = time.monotonic()+70
        while True:
            try:
                value = services.probe(0, "/health/ready")
                if value.get("ready") and value.get("release") == previous.name:
                    break
            except ExternalTemporaryError:
                # Expected startup refusal, bounded by the explicit deadline.
                value = {}
            if time.monotonic() >= deadline:
                raise RuntimeError("Alternate release did not become ready")
            time.sleep(.25)
        evidence["actual_pair"] = [value, services.probe(1, "/health/ready")]
        try:
            services.coherent(current.name)
        except ExternalTemporaryError:
            evidence["split_rejected"] = True
        else:
            raise RuntimeError("Split release was incorrectly accepted")
        command(["systemctl", "stop", "discordbot-split-probe"])
        child_started = False
        command(["systemctl", "start", "discordbot-staging-discord"])
        services.ready(current.name, timeout=70)
        command(["systemctl", "stop", "watch-web"])
        try:
            services.coherent(current.name)
        except ExternalTemporaryError:
            evidence["missing_peer_rejected"] = True
        else:
            raise RuntimeError("Unavailable peer was incorrectly accepted")
    finally:
        if child_started:
            command(["systemctl", "stop", "discordbot-split-probe"])
        start = time.monotonic()
        command(["systemctl", "start", "watch-web", "discordbot-staging-discord"])
        services.ready(current.name, timeout=70)
        evidence["pair_recovery_seconds"] = round(time.monotonic()-start, 3)
    evidence["restored_pair"] = [services.probe(index, "/health/ready") for index in range(2)]
    stats = os.statvfs("/")
    evidence["filesystem_available_bytes"] = stats.f_bavail * stats.f_frsize
    evidence["temperature_c"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text())/1000
    record("complete", **evidence)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        previous = json.loads(RESULT.read_text()) if RESULT.exists() else {}
        record("failed", failed_stage=previous.get("stage"), error_type=type(error).__name__)
        raise
