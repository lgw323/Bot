"""Operator-authenticated staging release rehearsal; no external Gateway or data."""

import argparse
import grp
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import time
import zipfile
from pathlib import Path


WORK = Path("/home/os/discordbot-phase9")
ROOT = Path("/var/lib/discordbot")


def record(stage, **fields):
    path = WORK / "release-rehearsal-progress.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"stage": stage, "time": time.time(), **fields}, indent=2))
    temporary.chmod(0o644)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--resume-prepared", action="store_true")
    parser.add_argument("--fault", choices=("none", "smoke"), default="none")
    parser.add_argument("--replace-helper-sha256")
    args = parser.parse_args()
    if len(args.commit) != 40 or any(c not in "0123456789abcdef" for c in args.commit):
        raise ValueError("Explicit full commit required")
    if os.geteuid() != 0 or not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file():
        raise SystemExit("Interactive sudo and explicit synthetic staging installation required")
    source = ROOT / "staging-candidates" / args.commit
    if source.exists() and not args.resume_prepared:
        raise RuntimeError("Existing source candidate requires reconciliation")
    if args.resume_prepared and (not source.is_dir() or source.is_symlink()):
        raise RuntimeError("Prepared source is missing or linked")
    if not args.resume_prepared:
        source.mkdir(parents=True, mode=0o750)
    archive_path = WORK / ("source-" + args.commit[:7] + ".zip")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.comment.decode().strip() != args.commit:
            raise RuntimeError("Archive revision differs")
        for item in archive.infolist():
            path = source / item.filename
            if not path.resolve().is_relative_to(source) or path.suffix in {".db", ".sql", ".enc"} or path.name == ".env":
                raise RuntimeError("Archive scope invalid")
        if args.resume_prepared:
            expected = {item.filename for item in archive.infolist() if not item.is_dir()}
            actual = {str(path.relative_to(source)).replace(os.sep, "/")
                      for path in source.rglob("*") if path.is_file()}
            if actual != expected or any(path.is_symlink() for path in source.rglob("*")):
                raise RuntimeError("Prepared source inventory differs")
            for name in expected:
                if (source / name).read_bytes() != archive.read(name):
                    raise RuntimeError("Prepared source content differs")
        else:
            archive.extractall(source)
    uid = pwd.getpwnam("discordbot-deploy").pw_uid
    gid = grp.getgrnam("discordbot").gr_gid
    for path in (source.parent, source, *source.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("Unexpected source link")
        os.chown(path, uid, gid)
        path.chmod(0o750 if path.is_dir() else 0o640)
    tool = ROOT / "staging-tools/stage_release.py"
    if tool.exists() and tool.read_bytes() != (WORK / "stage_release.py").read_bytes():
        if tool.is_symlink() or hashlib.sha256(tool.read_bytes()).hexdigest() != args.replace_helper_sha256:
            raise RuntimeError("Existing transaction helper differs")
        shutil.copyfile(WORK / "stage_release.py", tool)
        tool.chmod(0o644)
    if not tool.exists():
        shutil.copyfile(WORK / "stage_release.py", tool)
        tool.chmod(0o644)
    # Additional TEST-ONLY unit authorization; never sudo or unrelated units.
    rule = Path("/etc/polkit-1/rules.d/51-discordbot-staging.rules")
    text = '''// PHASE 9 synthetic fixture only; remove after staging.
polkit.addRule(function(action, subject) {
    if (action.id === "org.freedesktop.systemd1.manage-units" &&
        subject.user === "discordbot-deploy" &&
        action.lookup("unit") === "discordbot-staging-discord.service" &&
        ["start", "stop"].indexOf(action.lookup("verb")) !== -1) {
        return polkit.Result.YES;
    }
});
'''
    if rule.exists() and rule.read_text() != text:
        raise RuntimeError("Existing staging polkit rule differs")
    if not rule.exists():
        rule.write_text(text)
        rule.chmod(0o644)
    # The initial failure happened before runtime admission (unreadable manifest).
    # Clear only those named units' start-limit state before the reviewed retry.
    for unit in ("watch-web", "discordbot-staging-discord"):
        state = subprocess.run(["systemctl", "show", unit, "--property=ActiveState", "--value"],
                               check=True, capture_output=True, text=True, timeout=15)
        if state.stdout.strip() == "failed":
            subprocess.run(["systemctl", "reset-failed", unit], check=True,
                           capture_output=True, text=True, timeout=15)
    record("transaction_running", commit=args.commit, archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
    command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-stage-release",
               "--property=User=discordbot-deploy", "--property=Group=discordbot",
               "--property=LoadCredential=db_key:/etc/discordbot/secrets/db_key",
               "--property=RuntimeMaxSec=1800", "--property=TimeoutStopSec=300",
               "/var/lib/discordbot/bootstrap/bin/python", "-I", "-B", str(tool),
               "--source", str(source), "--commit", args.commit,
               "--credentials", "/run/credentials/discordbot-stage-release.service", "--fault", args.fault]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1900)
    record("transaction_finished", returncode=result.returncode, result=result.stdout[-5000:],
           diagnostic=result.stderr[-3000:])


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        record("failed", error_type=type(error).__name__,
               returncode=getattr(error, "returncode", None))
        raise
