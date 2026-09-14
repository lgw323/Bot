"""Read-only metadata/access checks inside the actual staging service mount namespace."""

import json
import os
import pwd
import signal
import subprocess
from pathlib import Path


def main() -> None:
    root = Path("/var/lib/discordbot")
    if os.geteuid() != 0 or not (root / "STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Interactive sudo and synthetic staging required")
    pid = subprocess.run(["systemctl", "show", "watch-web", "--property=MainPID", "--value"],
                         check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if not pid.isdigit() or pid == "0":
        raise RuntimeError("Watch must be running")
    checks = """
import json,os
paths={
'release_write':('/opt/discordbot/current/manifest.json',os.W_OK),
'data_write':('/var/lib/discordbot/data',os.W_OK),
'config_write':('/etc/discordbot/config.json',os.W_OK),
'watch_capability_read':('/run/credentials/watch-web.service/capability_key',os.R_OK),
'watch_control_read':('/run/credentials/watch-web.service/control_key',os.R_OK),
'watch_db_key_read':('/run/credentials/watch-web.service/db_key',os.R_OK),
'source_secret_read':('/etc/discordbot/secrets/db_key',os.R_OK)}
print(json.dumps({name:os.access(path,mode) for name,(path,mode) in paths.items()}))
"""
    result = subprocess.run(["nsenter", "--target", pid, "--mount", "--", "runuser", "-u", "discordbot", "--",
                             "/usr/bin/python3", "-c", checks], check=True, capture_output=True, text=True, timeout=20)
    access = json.loads(result.stdout)
    expected = dict(release_write=False, data_write=True, config_write=False, watch_capability_read=True,
                    watch_control_read=True, watch_db_key_read=False, source_secret_read=False)
    if access != expected:
        raise RuntimeError("Actual service access differs from scoped policy")
    metadata = {}
    for path in (root / "data/bot_database.db", root / "data/bot_database.db-wal",
                 root / "data/bot_database.db-shm", root / "operations.lock"):
        if path.exists():
            info = path.stat()
            metadata[path.name] = dict(mode=oct(info.st_mode & 0o7777), uid=info.st_uid, gid=info.st_gid)
    credential_root = Path("/proc") / pid / "root/run/credentials/watch-web.service"
    names = sorted(path.name for path in credential_root.iterdir())
    if names != ["capability_key", "control_key"]:
        raise RuntimeError("Watch credential scope differs")
    decisions = {}
    for user in ("discordbot", "discordbot-deploy"):
        # Modern polkit allows action details only from a trusted caller. Root performs
        # the read-only query for an explicit unprivileged subject, not for root itself.
        child = subprocess.Popen(["runuser", "-u", user, "--", "/usr/bin/python3", "-c",
                                  "import os,time; print(os.getpid(),flush=True); time.sleep(30)"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subject = int(child.stdout.readline().strip())
        try:
            start = Path(f"/proc/{subject}/stat").read_text().split(")", 1)[1].split()[19]
            identity = f"{subject},{start},{pwd.getpwnam(user).pw_uid}"
            decisions[user] = {}
            for unit in ("watch-web.service", "ssh.service"):
                result = subprocess.run(["pkcheck", "--action-id", "org.freedesktop.systemd1.manage-units",
                                         "--process", identity, "--detail", "unit", unit, "--detail", "verb", "stop"],
                                        capture_output=True, text=True, timeout=10)
                decisions[user][unit] = result.returncode
        finally:
            os.kill(subject, signal.SIGTERM)
            child.communicate(timeout=10)
    journal = subprocess.run(["journalctl", "-u", "watch-web", "-u", "discordbot-staging-discord", "-b", "-n", "500", "-o", "json", "--no-pager"],
                             check=True, capture_output=True, text=True, timeout=20)
    messages = [json.loads(line).get("MESSAGE", "") for line in journal.stdout.splitlines()]
    # Bounded marker scan is evidence only, never a claim to prove absence of every possible secret.
    markers = ("Authorization: Bearer ", "DISCORD_TOKEN=", "GEMINI_API_KEY=", "BEGIN PRIVATE KEY")
    evidence = dict(access=access, metadata=metadata, watch_credential_names=names,
                    polkit_decisions=decisions, journal_messages_scanned=len(messages),
                    obvious_secret_markers_found=any(marker in message for marker in markers for message in messages))
    path = Path("/home/os/discordbot-phase9/security-result.json")
    path.write_text(json.dumps(evidence, indent=2))
    path.chmod(0o644)


if __name__ == "__main__":
    main()
