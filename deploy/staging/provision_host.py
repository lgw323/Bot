"""Explicit clean-host preparation for PHASE 9; invoke through interactive sudo.

Does not configure sudo/auth, load secrets, enable services, or touch production data.
The caller reviews this file before invocation. Existing install paths are refused.
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
from pathlib import Path


LAYOUT = (
    ("/opt/discordbot", "discordbot-deploy", "discordbot", "2750"),
    ("/opt/discordbot/releases", "discordbot-deploy", "discordbot", "2750"),
    ("/opt/discordbot/candidates", "discordbot-deploy", "discordbot", "2750"),
    ("/var/lib/discordbot", "discordbot-deploy", "discordbot", "2770"),
    ("/var/lib/discordbot/data", "discordbot", "discordbot", "2770"),
    ("/var/lib/discordbot/state", "discordbot", "discordbot", "2770"),
    ("/var/lib/discordbot/cache", "discordbot", "discordbot", "2770"),
    ("/var/lib/discordbot/backups", "discordbot-deploy", "discordbot", "2750"),
    ("/var/lib/discordbot/audit", "discordbot-deploy", "discordbot", "2770"),
    ("/var/lib/discordbot/wheels", "discordbot-deploy", "discordbot", "2750"),
    ("/etc/discordbot", "root", "discordbot", "0750"),
    ("/etc/discordbot/secrets", "root", "root", "0700"),
)


def run(*args: str, timeout: int = 60) -> None:
    subprocess.run(args, check=True, timeout=timeout, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                                        "DEBIAN_FRONTEND": "noninteractive"})


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Use interactive sudo; no password argument is accepted")
    for name in ("discordbot", "discordbot-deploy"):
        try:
            pwd.getpwnam(name)
        except KeyError:
            continue
        raise SystemExit("Existing service account requires operator reconciliation")
    for path in ("/opt/discordbot", "/var/lib/discordbot", "/etc/discordbot"):
        if Path(path).exists() or Path(path).is_symlink():
            raise SystemExit("Existing installation requires operator reconciliation")
    run("apt-get", "update", timeout=600)
    run("apt-get", "install", "--yes", "--no-install-recommends", "python3.12-venv", "ffmpeg", timeout=900)
    run("useradd", "--system", "--user-group", "--home-dir", "/var/lib/discordbot",
        "--shell", "/usr/sbin/nologin", "discordbot")
    run("useradd", "--system", "--gid", "discordbot", "--home-dir", "/var/lib/discordbot/source",
        "--shell", "/usr/sbin/nologin", "discordbot-deploy")
    for path, owner, group, mode in LAYOUT:
        run("install", "-d", "-o", owner, "-g", group, "-m", mode, path)
    run("install", "-o", "discordbot-deploy", "-g", "discordbot", "-m", "0660", "/dev/null",
        "/var/lib/discordbot/operations.lock")
    print(json.dumps({"phase9_host_preparation": "complete", "services_enabled": False,
                      "credentials_created": False}), flush=True)


if __name__ == "__main__":
    main()
