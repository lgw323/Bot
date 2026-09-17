"""Reviewed 10B code-pointer activation only; never starts services or promotes data."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


def activate(store, runner, audit, lock, target: str, expected: str, approved: bool) -> None:
    from discordbot.platform.errors import ConflictError, DataIntegrityError
    if not approved or not all(re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", x) for x in (target, expected)):
        raise ConflictError("Exact reviewed releases and final cutover approval required")
    with lock.acquire():
        if store.current() != expected:
            raise ConflictError("Current release changed; reconcile before activation")
        manifest = store.validate(target)
        if not manifest["schema_min"] <= 5 <= manifest["schema_max"]:
            raise DataIntegrityError("Candidate cannot read the reviewed schema")
        units = ("discord-bot.service", "watch-web.service", "discordbot-staging-discord.service",
                 "discordbot-backup.service", "discordbot-update.service", "discordbot-manual.service",
                 "discordbot-backup.timer", "discordbot-update.timer", "discordbot-manual.timer")
        for unit in units:
            state = runner.read(["systemctl", "show", unit, "--property=ActiveState", "--value"], store.root, 10)
            pid = runner.read(["systemctl", "show", unit, "--property=MainPID", "--value"], store.root, 10)
            if state != "inactive" or (not unit.endswith(".timer") and pid != "0"):
                raise ConflictError("Every writer and operation consumer must be stopped")
        audit.write("cutover_activation", target, "started", "operator_approved_stopped")
        # Any failure after this point is uncertain. No automatic retry/rollback/start.
        store.activate(target)
        if store.current() != target:
            raise DataIntegrityError("Activation outcome requires reconciliation")
        audit.write("cutover_activation", target, "ok", "pointer_only_services_stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-current", required=True)
    parser.add_argument("--approve-cutover-activation", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", args.target):
        return 1
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path("/opt/discordbot/releases") / args.target / "app/src"))
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.build import CommandRunner
    from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore
    try:
        activate(ReleaseStore(Path("/opt/discordbot")), CommandRunner(),
                 Audit(Path("/var/lib/discordbot/audit")), ExclusiveLock(Path("/var/lib/discordbot/operations.lock")),
                 args.target, args.expected_current, args.approve_cutover_activation)
    except Exception:
        print("Activation stopped or uncertain. Keep services stopped and inspect current/audit before any retry.")
        return 1
    print("Reviewed code pointer activated; services remain stopped, database not promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
