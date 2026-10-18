"""Finite operator-authenticated lifecycle probe for the synthetic staging pair."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


WORK = Path("/home/os/discordbot-phase9")
UNITS = ("discordbot-staging-discord", "watch-web")
OPENER = build_opener(ProxyHandler({}))


def state(unit: str) -> dict[str, str]:
    result = subprocess.run(["systemctl", "show", unit, "-p", "MainPID", "-p", "Result",
                             "-p", "ActiveState", "-p", "NRestarts"],
                            check=True, capture_output=True, text=True, timeout=10)
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def health(index: int, path: str = "/health/ready") -> dict:
    with OPENER.open(f"http://127.0.0.1:{9010 + index}{path}", timeout=2) as response:
        return json.loads(response.read(8192))


def ready(release: str) -> float:
    start = time.monotonic()
    while time.monotonic() - start < 70:
        try:
            values = [health(index) for index in range(2)]
            if all(value.get("ready") and value.get("release") == release for value in values):
                return round(time.monotonic() - start, 3)
        except (OSError, ValueError):
            # Connection refusal/503 is expected while the bounded startup runs.
            # Retry only until the fixed deadline; never treat it as readiness.
            time.sleep(0.25)
            continue
        time.sleep(0.25)
    raise RuntimeError("Staging readiness deadline exceeded")


def sample() -> dict:
    values = {}
    for unit in UNITS:
        status = state(unit)
        pid = int(status["MainPID"])
        if not pid:
            raise RuntimeError("Staging process is not running")
        proc = Path("/proc") / str(pid)
        memory = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line)
        values[unit] = {**status, "rss_kib": int(memory["VmRSS"].split()[0]),
                        "threads": int(memory["Threads"]), "fds": len(list((proc / "fd").iterdir()))}
    values["temperature_c"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    values["load_average"] = os.getloadavg()
    return values


def main() -> None:
    if os.geteuid() != 0 or not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Explicit synthetic installation and interactive sudo required")
    release = Path("/opt/discordbot/current").resolve(strict=True).name
    ready(release)
    if health(0, "/health/staging") != {"synthetic_gateway": True, "external_integration": False}:
        raise RuntimeError("Expected synthetic peer")
    evidence = {"release": release, "external_integration": False, "before": sample(), "cycles": []}
    for index, unit in enumerate(UNITS):
        peer = UNITS[1-index]
        peer_pid = state(peer)["MainPID"]
        started = time.monotonic()
        subprocess.run(["systemctl", "stop", unit], check=True, timeout=90)
        stopped = state(unit)
        if stopped["ActiveState"] != "inactive" or stopped["Result"] != "success":
            raise RuntimeError("Shutdown did not complete cleanly")
        if state(peer)["MainPID"] != peer_pid or not health(1-index, "/health/live")["live"]:
            raise RuntimeError("Peer isolation failed")
        stop_seconds = round(time.monotonic() - started, 3)
        started = time.monotonic()
        subprocess.run(["systemctl", "start", unit], check=True, timeout=90)
        ready(release)
        evidence["cycles"].append({"unit": unit, "stop_seconds": stop_seconds,
                                    "start_to_ready_seconds": round(time.monotonic()-started, 3),
                                    "peer_pid_unchanged": True})
    start = time.monotonic()
    samples = []
    for _ in range(6):
        ready(release)
        samples.append(sample())
        time.sleep(10)
    evidence.update(soak_seconds=round(time.monotonic()-start, 3), samples=samples, after=sample())
    path = WORK / "lifecycle-result.json"
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)


if __name__ == "__main__":
    main()
