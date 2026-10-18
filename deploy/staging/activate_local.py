"""Interactive-sudo installation of real Watch plus an explicitly synthetic peer.

No external credentials, DNS edits, timer enabling or production Discord launch.
Writes only fixed, safe progress fields readable from the operator work directory.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path


WORK = Path("/home/os/discordbot-phase9")
SOURCE = Path("/var/lib/discordbot/staging-source")
TOOLS = Path("/var/lib/discordbot/staging-tools")
RESULT = WORK / "activation-progress.json"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "PYTHON_DOTENV_DISABLED": "1",
       "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": "/dev/null"}


def progress(stage: str, **fields) -> None:
    value = {"stage": stage, "time": time.time(), **fields}
    temporary = RESULT.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o644)
    os.replace(temporary, RESULT)
    print(json.dumps(value), flush=True)


def command(args, timeout=120):
    return subprocess.run(args, check=True, capture_output=True, text=True, env=ENV, timeout=timeout)


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo is required")
    if not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("install_local.py has not completed")
    progress("installation_preparation_verified")
    TOOLS.mkdir(mode=0o755, exist_ok=True)
    for name in ("build_initial.py", "local_discord.py", "filesystem_probe.py"):
        target = TOOLS / name
        if target.exists():
            if target.is_symlink() or target.read_bytes() != (WORK / name).read_bytes():
                raise RuntimeError("Existing staging tools require reconciliation")
            continue
        shutil.copyfile(WORK / name, target)
        target.chmod(0o644)
    progress("building_initial_release")
    built = command(["runuser", "-u", "discordbot-deploy", "--", "/var/lib/discordbot/bootstrap/bin/python",
                     "-I", "-B", str(TOOLS / "build_initial.py")], 900)
    progress("initial_release_ready", result=json.loads(built.stdout))
    unit_directory = Path("/etc/systemd/system")
    for source in (SOURCE / "deploy/systemd").iterdir():
        target = unit_directory / source.name
        if target.exists() or target.is_symlink():
            raise RuntimeError("Existing systemd asset requires reconciliation")
        shutil.copyfile(source, target)
        target.chmod(0o644)
    fixture = (SOURCE / "deploy/systemd/discord-bot.service").read_text()
    lines = []
    for line in fixture.splitlines():
        if line.startswith("LoadCredential="):
            continue
        if line.startswith("Description="):
            line = "Description=PHASE 9 SYNTHETIC local Gateway substitute; no external login"
        if line.startswith("ExecStart="):
            line = ("ExecStart=/opt/discordbot/current/.venv/bin/python -I "
                    "/var/lib/discordbot/staging-tools/local_discord.py --synthetic-local-only")
        lines.append(line)
    target = unit_directory / "discordbot-staging-discord.service"
    if target.exists():
        raise RuntimeError("Existing fixture unit requires reconciliation")
    target.write_text("\n".join(lines) + "\n")
    target.chmod(0o644)
    rule = Path("/etc/polkit-1/rules.d/50-discordbot.rules")
    if rule.exists():
        raise RuntimeError("Existing polkit rule requires reconciliation")
    shutil.copyfile(SOURCE / "deploy/polkit/50-discordbot.rules", rule)
    rule.chmod(0o644)
    verified = command(["systemd-analyze", "verify", *[str(p) for p in (SOURCE / "deploy/systemd").iterdir()], str(target)])
    progress("units_verified", diagnostics_empty=not bool(verified.stderr.strip()))
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "start", "watch-web", "discordbot-staging-discord"])
    progress("local_services_started", production_discord_started=False, timers_enabled=False)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        previous = json.loads(RESULT.read_text()) if RESULT.exists() else {}
        progress("failed", failed_stage=previous.get("stage"), error_type=type(error).__name__)
        raise
