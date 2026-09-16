"""Finite synthetic-only observation. Records allowlisted metadata, never DB rows, logs or secrets."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import ProxyHandler, build_opener


ROOT = Path("/var/lib/discordbot")
UNITS = ("discordbot-staging-discord.service", "watch-web.service", "discord-bot.service",
         "discordbot-backup.service", "discordbot-backup.timer", "discordbot-update.timer")
FIELDS = ("ActiveState", "Result", "MainPID", "NRestarts", "MemoryCurrent", "TasksCurrent",
          "LastTriggerUSec", "ExecMainStatus", "CPUUsageNSec")
METRICS = {"process_ready", "tasks_active", "database_recent_failures", "database_last_execution_seconds",
           "database_read_admitted", "database_write_admitted", "backup_age_seconds", "backup_rpo_exceeded",
           "telemetry_dropped", "metric_series_dropped", "database_probe_total{result=\"ok\"}",
           "database_probe_total{result=\"failed\"}"}


def systemd(unit: str) -> dict:
    result = subprocess.run(["systemctl", "show", unit, *["--property=" + item for item in FIELDS]],
                            check=True, capture_output=True, text=True, timeout=5)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def process(pid: int) -> dict:
    if not pid:
        return {"running": False}
    root = Path("/proc") / str(pid)
    fields = {}
    for line in (root / "status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"VmRSS", "VmHWM", "Threads", "FDSize"}:
            fields[key] = int(value.split()[0])
    fields["fd_count"] = sum(1 for _ in (root / "fd").iterdir())
    return fields


def size(path: Path, limit: int = 20000) -> dict:
    count = total = 0
    for parent, directories, files in os.walk(path, followlinks=False):
        directories[:] = [name for name in directories if not (Path(parent) / name).is_symlink()]
        for name in files:
            item = Path(parent) / name
            if not item.is_symlink():
                total += item.stat().st_size
                count += 1
            if count >= limit:
                return {"files": count, "bytes": total, "truncated": True}
    return {"files": count, "bytes": total, "truncated": False}


def sample() -> dict:
    result = {"time_unix": time.time(), "services": {}, "health": {}, "errors": []}
    for unit in UNITS:
        try:
            state = systemd(unit)
            state["process"] = process(int(state.get("MainPID", "0")))
            result["services"][unit] = state
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result["errors"].append(unit + ":" + type(error).__name__)
    opener = build_opener(ProxyHandler({}))
    for port in (9010, 9011):
        try:
            with opener.open(f"http://127.0.0.1:{port}/health/ready", timeout=3) as response:
                ready = json.loads(response.read(8192))
            health = {"ready": ready.get("ready") is True,
                      "release": ready.get("release") if re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", str(ready.get("release"))) else "invalid"}
            with opener.open(f"http://127.0.0.1:{port}/metrics", timeout=3) as response:
                raw = response.read(65536).decode()
            health["metrics"] = {}
            for line in raw.splitlines():
                parts = line.rsplit(" ", 1)
                if len(parts) == 2 and parts[0] in METRICS:
                    value = float(parts[1])
                    if math.isfinite(value):
                        health["metrics"][parts[0]] = value
            result["health"][str(port)] = health
        except (OSError, ValueError) as error:
            result["errors"].append(str(port) + ":" + type(error).__name__)
    for name in ("cache", "backups", "audit"):
        try:
            result[name] = size(ROOT / name)
        except OSError as error:
            result["errors"].append(name + ":" + type(error).__name__)
    result["disk_free_bytes"] = shutil.disk_usage(ROOT).free
    result["temperature_c"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    throttle = Path("/sys/devices/platform/soc/soc:firmware/get_throttled")
    result["throttling"] = throttle.read_text().strip() if throttle.is_file() else "unavailable"
    result["load_average"] = list(os.getloadavg())
    return result


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def observe(output: Path, seconds: int, interval: int) -> None:
    started = time.monotonic()
    count = 0
    errors = Counter()
    first = None
    while True:
        # Stop automatically if the synthetic marker disappears or production starts.
        if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file() or systemd("discord-bot.service")["ActiveState"] != "inactive":
            raise RuntimeError("Synthetic-only boundary changed")
        value = sample()
        first = first or value
        count += 1
        errors.update(value["errors"])
        with (output / "samples.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        elapsed = time.monotonic() - started
        write_json(output / "summary.json", {"status": "complete" if elapsed >= seconds else "observing",
                   "requested_seconds": seconds, "observed_seconds": elapsed, "samples": count,
                   "error_counts": dict(errors), "first": first, "last": value})
        if elapsed >= seconds:
            return
        time.sleep(min(interval, seconds - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=86400)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or not 60 <= args.seconds <= 86400 or not 10 <= args.interval <= 600:
        raise SystemExit("Interactive sudo and bounded observation required")
    output = args.output.absolute()
    # Aggregate evidence is operator-readable without granting access to protected data/secrets.
    if output.parent != Path("/var/tmp") or not re.fullmatch(r"phase10-observation-[a-z0-9-]+", output.name) or output.is_symlink():
        raise SystemExit("New PHASE 10 observation directory required")
    if args.install:
        if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file() or systemd("discord-bot.service")["ActiveState"] != "inactive":
            raise SystemExit("Synthetic staging required")
        output.mkdir(mode=0o755)
        target = output / "observe.py"
        shutil.copyfile(__file__, target)
        target.chmod(0o644)
        subprocess.run(["systemd-run", "--unit=" + output.name, "--collect",
                        "--property=RuntimeMaxSec=" + str(args.seconds + 600),
                        "--property=UMask=0022", "--property=NoNewPrivileges=true",
                        "--property=ProtectSystem=strict", "--property=ProtectHome=true",
                        "--property=ReadWritePaths=" + str(output),
                        "--property=IPAddressDeny=any", "--property=IPAddressAllow=localhost",
                        "/usr/bin/python3", "-I", str(target), "--output", str(output),
                        "--seconds", str(args.seconds), "--interval", str(args.interval)], check=True, timeout=15)
        print("Finite synthetic observation started; no production service or timer changed.")
    else:
        observe(output, args.seconds, args.interval)


if __name__ == "__main__":
    main()
