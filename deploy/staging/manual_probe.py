"""Synthetic manual inbox rehearsal with only the external Discord unit substituted."""

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


def worker() -> None:
    sys.dont_write_bytecode = True
    release = Path("/opt/discordbot/current").resolve(strict=True)
    sys.path.insert(0, str(release / "app/src"))
    from discordbot.operations.adapters import cli
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.build import CommandRunner
    from discordbot.operations.adapters.filesystem import ExclusiveLock, read_json
    from discordbot.operations.adapters.manual import RequestInbox, write_request
    from discordbot.platform.executors import BoundedExecutor

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

    cli.CommandRunner = FixtureRunner  # Test-only process, never changes the installed CLI.
    request = ROOT / "state/manual-request.json"
    if request.exists():
        raise RuntimeError("Existing manual inbox requires reconciliation")
    evidence = {"synthetic_only": True, "release": release.name}

    async def accept():
        executor = BoundedExecutor(workers=1, queue_capacity=2, name="staging-manual")
        try:
            inbox = RequestInbox(ROOT / "state", ROOT / "operations.lock", executor, Audit(ROOT / "audit"), release.name)
            with ExclusiveLock(ROOT / "operations.lock").acquire():
                evidence["overlap"] = await inbox.accept("restart", "phase9-lock-race")
            evidence["first"] = await inbox.accept("restart", "phase9-manual-restart")
            evidence["duplicate_pending"] = await inbox.accept("restart", "phase9-manual-restart")
        finally:
            await executor.close(grace_seconds=5)

    asyncio.run(accept())
    args = ["manual", "--config", "/etc/discordbot/config.json", "--credentials", os.environ["CREDENTIALS_DIRECTORY"]]
    start = time.monotonic()
    evidence["restart_returncode"] = cli.main(args)
    evidence["restart_seconds"] = round(time.monotonic()-start, 3)
    evidence["completed_result"] = read_json(request)["result"]
    if evidence["restart_returncode"] != 0 or evidence["completed_result"] != "ok":
        raise RuntimeError("Restart failed; preserve uncertain inbox for reconciliation")
    evidence["completed_replay_returncode"] = cli.main(args)
    value = read_json(request)
    value["result"] = "in_progress"
    write_request(request, value)
    evidence["interrupted_replay_returncode"] = cli.main(args)
    evidence["interrupted_preserved"] = read_json(request)["result"] == "in_progress"
    # This injected state had no operation in flight. Record that explicit reconciliation,
    # preserving the receipt/history instead of leaving an uncertain pending request.
    value["result"] = "staging_reconciled"
    write_request(request, value)
    if not (evidence["first"] == "accepted" and evidence["overlap"] == "already_running"
            and evidence["duplicate_pending"] == "already_running" and evidence["restart_returncode"] == 0
            and evidence["completed_result"] == "ok" and evidence["interrupted_preserved"]):
        raise RuntimeError("Manual drill failed")
    (ROOT / "state/manual-drill-result.json").write_text(json.dumps(evidence))


def main() -> None:
    if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Synthetic staging required")
    if "--worker" in sys.argv:
        worker()
        return
    if os.geteuid() != 0:
        raise RuntimeError("Interactive sudo required")
    tool = ROOT / "staging-tools/manual_probe.py"
    if tool.exists():
        raise RuntimeError("Existing helper requires reconciliation")
    shutil.copyfile(Path(__file__), tool)
    tool.chmod(0o644)
    command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-manual-probe",
               "--property=User=discordbot-deploy", "--property=Group=discordbot", "--property=UMask=0077",
               "--property=LoadCredential=db_key:/etc/discordbot/secrets/db_key", "--property=RuntimeMaxSec=600",
               "/opt/discordbot/current/.venv/bin/python", "-I", "-B", str(tool), "--worker"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=650)
    evidence = {"returncode": result.returncode, "diagnostic": result.stderr[-2000:]}
    if result.returncode == 0:
        evidence["drill"] = json.loads((ROOT / "state/manual-drill-result.json").read_text())
        # The installed unit must observe the reconciled receipt and perform no restart.
        actual = subprocess.run(["systemctl", "start", "discordbot-manual"], capture_output=True, text=True, timeout=100)
        evidence["installed_service_noop_returncode"] = actual.returncode
    path = WORK / "manual-result.json"
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)
    if result.returncode == 0:
        subprocess.run(["python3", str(WORK / "security_probe.py")], check=True, timeout=120)


if __name__ == "__main__":
    main()
