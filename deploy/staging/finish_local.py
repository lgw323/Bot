"""Finite sequence of previously reviewed synthetic deploy, promotion and reboot drills."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def main() -> None:
    work = Path("/home/os/discordbot-phase9")
    if os.geteuid() != 0 or not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Interactive sudo and synthetic installation required")
    subprocess.run(["python3", str(work / "rehearse_release.py"), "--commit",
                    "0376f14868461d16220e6c1877d826d17823439a", "--resume-prepared"], check=True, timeout=1950)
    transaction = json.loads((work / "release-rehearsal-progress.json").read_text())
    if transaction.get("returncode") != 0 or json.loads(transaction["result"])["result"] != "ok":
        raise RuntimeError("Successful second release required")
    subprocess.run(["python3", str(work / "promotion_probe.py")], check=True, timeout=330)
    if json.loads((work / "promotion-result.json").read_text())["promotion_returncode"] != 0:
        raise RuntimeError("Synthetic promotion failed; inspect evidence")
    expected = json.loads(transaction["result"])["release"]
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 70
    while True:
        try:
            pair = []
            for port in (9010, 9011):
                with opener.open(f"http://127.0.0.1:{port}/health/ready", timeout=2) as response:
                    pair.append(json.loads(response.read(8192)))
            if all(value.get("ready") and value.get("release") == expected for value in pair):
                break
        except (OSError, ValueError):
            # Expected while starting; the fixed deadline below remains authoritative.
            pair = []
        if time.monotonic() >= deadline:
            raise RuntimeError("Post-promotion readiness failed")
        time.sleep(0.25)
    subprocess.run(["python3", str(work / "reboot_probe.py")], check=True, timeout=300)


if __name__ == "__main__":
    main()
