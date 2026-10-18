"""Offline production config/credential check. Never opens a database or starts an application."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


SCOPES = {"discord-bot": {"discord_token", "gemini_key", "control_key"},
          "watch-web": {"capability_key", "control_key"}, "operations": {"db_key"}}


def check(config: Path, credentials: Path, service: str, mounted: bool) -> dict:
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.filesystem import read_json

    scope = SCOPES[service]
    if service == "operations" and read_json(config, 65536).get("backup_remote") is not None:
        scope = scope | {"backup_ssh_key", "known_hosts"}
    if set(path.name for path in credentials.iterdir()) != scope:
        raise ValueError("Credential scope differs")
    settings = load_settings(config, credentials, service)
    if settings.environment != "production":
        raise ValueError("Production configuration required")
    if mounted:
        if os.name != "posix" or not str(credentials).startswith("/run/credentials/"):
            raise ValueError("systemd credential mount required")
        if not os.statvfs(credentials).f_flag & os.ST_RDONLY:
            raise ValueError("Read-only credential mount required")
    return {"service": service, "configuration": "valid", "secret_format": "valid",
            "scope": "exact", "readonly_mount": mounted,
            "network_login": "not_attempted", "database_open": "not_attempted"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--service", choices=SCOPES, required=True)
    parser.add_argument("--source", type=Path, required=True, help="Reviewed release app/src directory")
    parser.add_argument("--require-mounted", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve(strict=True)))
    try:
        result = check(args.config, args.credentials, args.service, args.require_mounted)
    except Exception as error:
        print(json.dumps({"service": args.service, "status": "failed", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
