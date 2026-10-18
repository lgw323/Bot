"""Real operations transaction with ONLY the Discord unit mapped to a local fixture.

The real Discord entrypoint remains blocked on staging credentials. Other service,
DB, backup, filesystem, audit and readiness adapters run normally on Linux.
"""

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--fault", choices=("none", "smoke"), default="none")
    args = parser.parse_args()
    if not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise SystemExit("Explicit synthetic installation required")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.source / "src"))
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.build import Builder, CommandRunner
    from discordbot.operations.adapters.configuration import load_settings
    from discordbot.operations.adapters.deployment import LocalDeployment, Services
    from discordbot.operations.adapters.filesystem import ReleaseStore
    from discordbot.operations.application.deployment import Deployment
    from discordbot.platform.errors import ExternalTemporaryError

    class FixtureRunner(CommandRunner):
        @staticmethod
        def mapped(arguments):
            if arguments[0] == "systemctl":
                return ["discordbot-staging-discord" if value == "discord-bot" else value for value in arguments]
            return arguments
        def run(self, arguments, cwd, timeout):
            return super().run(self.mapped(arguments), cwd, timeout)
        def read(self, arguments, cwd, timeout):
            return super().read(self.mapped(arguments), cwd, timeout)

    settings = load_settings(Path("/etc/discordbot/config.json"), args.credentials, "operations")
    runner = FixtureRunner()
    store = ReleaseStore(settings.release_root)
    builder = Builder(store, runner, args.source, Path("/var/lib/discordbot/wheels"), python="/usr/bin/python3.12")
    class DrillServices(Services):
        injected = False

        def smoke(self, release):
            super().smoke(release)
            if args.fault == "smoke" and not self.injected:
                self.injected = True
                raise ExternalTemporaryError("explicit synthetic smoke gate failure")

    services = DrillServices(runner, store.root, (9010, 9011))
    port = LocalDeployment(settings, builder, services, Audit(settings.audit))
    start = time.monotonic()
    result = Deployment(port).run(args.commit)
    print(json.dumps({"result": result.result, "stage": result.stage, "rollback": result.rollback,
                      "release": result.release, "duration_seconds": round(time.monotonic()-start, 3),
                      "discord_gateway": "synthetic_fixture_only", "injected_fault": args.fault}), flush=True)
    if result.result != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
