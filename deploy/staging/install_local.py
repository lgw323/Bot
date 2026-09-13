"""Install the reviewed Phase 8 archive for synthetic, loopback-only PHASE 9 work.

Requires interactive sudo and provision_host.py completion. Never creates Discord/
Gemini credentials, contacts an API, enables timers, or configures a public route.
"""

from __future__ import annotations

import base64
import grp
import json
import os
import pwd
import shutil
import subprocess
import zipfile
from pathlib import Path


WORK = Path("/home/os/discordbot-phase9")
ROOT = Path("/var/lib/discordbot")
SOURCE = ROOT / "staging-source"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "PYTHON_DOTENV_DISABLED": "1",
       "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": "/dev/null",
       "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


def run(args: list[str], timeout: int = 90) -> None:
    subprocess.run(args, check=True, timeout=timeout, env=ENV)


def main() -> None:
    if os.geteuid() != 0 or not ROOT.is_dir():
        raise SystemExit("Requires interactive sudo after clean host preparation")
    for path in (SOURCE, ROOT / "bootstrap", Path("/opt/discordbot/current"), Path("/etc/discordbot/config.json")):
        if path.exists() or path.is_symlink():
            raise SystemExit("Existing staging installation: reconcile before retry")
    uid = pwd.getpwnam("discordbot-deploy").pw_uid
    gid = grp.getgrnam("discordbot").gr_gid
    SOURCE.mkdir(mode=0o750)
    with zipfile.ZipFile(WORK / "source-7d596ad.zip") as archive:
        commit = archive.comment.decode().strip()
        if commit != "7d596ade8c721931437560ad9e6828762018972c":
            raise SystemExit("Source revision differs from reviewed Phase 8 baseline")
        for item in archive.infolist():
            target = SOURCE / item.filename
            if (not target.resolve().is_relative_to(SOURCE) or target.suffix in {".db", ".sql", ".enc"}
                    or target.name == ".env"):
                raise SystemExit("Source archive scope rejected")
        archive.extractall(SOURCE)
    for path in (SOURCE, *SOURCE.rglob("*")):
        if path.is_symlink():
            raise SystemExit("Unexpected source link")
        os.chown(path, uid, gid)
        path.chmod(0o750 if path.is_dir() else 0o640)
    for source in (WORK / "wheels").iterdir():
        if source.is_symlink() or not source.is_file():
            raise SystemExit("Wheel source scope rejected")
        target = ROOT / "wheels" / source.name
        if target.exists():
            raise SystemExit("Existing wheel must not be replaced implicitly")
        shutil.copyfile(source, target)
        os.chown(target, uid, gid)
        target.chmod(0o640)
    run(["runuser", "-u", "discordbot-deploy", "--", "python3.12", "-m", "venv", "--copies", str(ROOT / "bootstrap")])
    python = str(ROOT / "bootstrap/bin/python")
    run(["runuser", "-u", "discordbot-deploy", "--", python, "-m", "pip", "install", "--no-cache-dir",
         "--no-index", "--no-deps", "--require-hashes", "--only-binary=:all:", "--find-links", str(ROOT / "wheels"),
         "-r", str(ROOT / "wheels/requirements.lock")], 600)
    run(["runuser", "-u", "discordbot-deploy", "--", python, "-m", "pip", "check"])
    # Internal cryptographic keys are freshly generated synthetic keys. They are
    # never external application credentials and are never printed.
    for name in ("db_key", "control_key", "capability_key"):
        path = Path("/etc/discordbot/secrets") / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(base64.urlsafe_b64encode(os.urandom(32)))
            stream.flush()
            os.fsync(stream.fileno())
    config = json.loads((SOURCE / "deploy/config.example.json").read_text())
    config["key_id"] = "phase9-synthetic-only"
    path = Path("/etc/discordbot/config.json")
    path.write_text(json.dumps(config, indent=2))
    os.chown(path, 0, gid)
    path.chmod(0o640)
    marker = ROOT / "STAGING_SYNTHETIC_ONLY"
    marker.write_text("No approved Discord/Gemini credentials or public hostname; local tests only.\n")
    marker.chmod(0o644)
    print(json.dumps({"staging_install_preparation": "complete", "external_credentials": False,
                      "services_started": False, "timers_enabled": False}), flush=True)


if __name__ == "__main__":
    main()
