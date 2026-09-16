"""Explicit 10A offline build/scoped credential check. Never activates or logs in."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile

WORK = Path("/home/os/discordbot-phase10")
ROOT = Path("/var/lib/discordbot")
CONFIG = Path("/etc/discordbot/production-candidate/config.json")
SCOPES = {"discord-bot": ("discord_token", "gemini_key", "control_key"),
          "watch-web": ("capability_key", "control_key"), "operations": ("db_key",)}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path: Path, value: dict, mode: int = 0o644) -> None:
    temporary = path.with_suffix(".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("Linked evidence refused")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    temporary.replace(path)


def checked(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Never echo subprocess diagnostics from credential-bearing operations.
        raise RuntimeError("Subprocess failed")
    return result.stdout


def safe_archive(archive: zipfile.ZipFile, commit: str) -> None:
    if archive.comment.decode().strip() != commit:
        raise ValueError("Source identity mismatch")
    for item in archive.infolist():
        path = Path(item.filename)
        mode = item.external_attr >> 16
        if (path.is_absolute() or ".." in path.parts or not path.parts
                or path.parts[0] not in {"src", "tests", "deploy", "pyproject.toml", "requirements.txt", "requirements-dev.txt"}
                or stat.S_ISLNK(mode) or path.suffix.lower() in {".db", ".sql", ".enc", ".pyc", ".log"}
                or path.name == ".env"):
            raise ValueError("Source inventory refused")


def build_worker(run: Path, commit: str) -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(run / "source/src"))
    from discordbot.operations.adapters.build import Builder, CommandRunner
    from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore
    store = ReleaseStore(Path("/opt/discordbot"))
    builder = Builder(store, CommandRunner(), run / "source", ROOT / "wheels", python="/usr/bin/python3.12")
    start = time.monotonic()
    with ExclusiveLock(ROOT / "operations.lock").acquire():
        before = store.current()
        release = builder.build(commit)
        path = store.path(release)
        builder.runner.run([str(path / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider",
                            "tests/integration/operations", "--confcutdir=tests/integration/operations", "-q",
                            "-W", "error::RuntimeWarning", "-W", "error::pytest.PytestUnraisableExceptionWarning",
                            "-o", "xfail_strict=true"], path / "app", 300)
        builder.publish(release)
        manifest = store.validate(release)
        if store.current() != before:
            raise ValueError("Current unexpectedly changed")
    record(run / "build-result.json", {"release": release, "commit": commit, "previous": before,
           "dependency_hash": manifest["dependency_hash"], "schema": [manifest["schema_min"], manifest["schema_max"]],
           "operations_tests": "pass", "activated": False, "seconds": round(time.monotonic() - start, 3)})


def credential_worker(run: Path, service: str, release: str) -> None:
    sys.dont_write_bytecode = True
    source = Path("/opt/discordbot/releases") / release / "app"
    sys.path.insert(0, str(source / "src"))
    spec = importlib.util.spec_from_file_location("candidate_preflight", source / "deploy/production/preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
    result = module.check(CONFIG, credentials, service, True)
    metadata = {}
    for name in SCOPES[service]:
        info = (credentials / name).stat()
        metadata[name] = {"uid": info.st_uid, "gid": info.st_gid, "mode": oct(stat.S_IMODE(info.st_mode))}
    denied = not any(os.access(CONFIG.parent / "secrets" / name, os.R_OK)
                     for name in {item for items in SCOPES.values() for item in items})
    if not denied:
        raise ValueError("Source secret accessible outside credential mount")
    result.update(metadata=metadata, direct_source_access="denied", effective_uid=os.geteuid())
    print(json.dumps(result))


def parent(run: Path, commit: str, archive_sha256: str) -> None:
    import grp
    import pwd
    if os.geteuid() != 0:
        raise ValueError("Interactive sudo required")
    progress = WORK / "verification-progress.json"
    stage = "metadata"
    evidence = {"started_unix": time.time(), "commit": commit, "production_started": False,
                "canonical_promoted": False, "activated": False}
    def save():
        record(progress, dict(evidence, stage=stage))
    try:
        save()
        if not (ROOT / "STAGING_SYNTHETIC_ONLY").is_file():
            raise ValueError("Synthetic host boundary missing")
        if checked(["systemctl", "show", "discord-bot", "-p", "ActiveState", "--value"]).strip() != "inactive":
            raise ValueError("Production is active")
        if (CONFIG.parent / ".setup-incomplete").exists():
            raise ValueError("Setup is incomplete")
        gid = grp.getgrnam("discordbot").gr_gid
        source_secrets = CONFIG.parent / "secrets"
        expected = [(CONFIG.parent, 0o750, gid), (CONFIG, 0o640, gid), (source_secrets, 0o700, 0)]
        expected += [(source_secrets / name, 0o600, 0) for name in {n for names in SCOPES.values() for n in names}]
        for path, mode, group in expected:
            info = path.lstat()
            if (path.is_symlink() or stat.S_IMODE(info.st_mode) != mode or info.st_uid != 0 or info.st_gid != group
                    or (path in (CONFIG.parent, source_secrets) and not stat.S_ISDIR(info.st_mode))
                    or (path not in (CONFIG.parent, source_secrets) and not stat.S_ISREG(info.st_mode))):
                raise ValueError("Candidate ownership or permissions invalid")
        if set(p.name for p in source_secrets.iterdir()) != {n for names in SCOPES.values() for n in names}:
            raise ValueError("Credential inventory differs")
        evidence["source_metadata"] = "pass"
        evidence["staging_config_sha256_before"] = digest(Path("/etc/discordbot/config.json"))
        evidence["candidate_config_sha256"] = digest(CONFIG)
        before = Path("/opt/discordbot/current").resolve(strict=True)
        archive = WORK / ("source-" + commit + ".zip")
        if digest(archive) != archive_sha256:
            raise ValueError("Archive checksum differs")
        stage = "source_preparation"
        save()
        run.mkdir(mode=0o750)
        os.chown(run, 0, gid)
        run.chmod(0o750)
        source = run / "source"
        source.mkdir(mode=0o750)
        with zipfile.ZipFile(archive) as exported:
            safe_archive(exported, commit)
            exported.extractall(source)
        uid = pwd.getpwnam("discordbot-deploy").pw_uid
        for path in (source, *source.rglob("*")):
            os.chown(path, uid, gid)
            path.chmod(0o750 if path.is_dir() else 0o640)
        helper = run / "verify_candidate.py"
        shutil.copyfile(__file__, helper)
        helper.chmod(0o644)
        # Only build output is deploy-writable. Source secret directories remain root-exclusive.
        os.chown(run, uid, gid)
        stage = "offline_build"
        save()
        command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-phase10-build",
                   "-p", "User=discordbot-deploy", "-p", "Group=discordbot", "-p", "UMask=0027",
                   "-p", "PrivateNetwork=yes", "-p", "ProtectSystem=strict", "-p", "ProtectHome=yes",
                   "-p", "NoNewPrivileges=yes", "-p", "RuntimeMaxSec=1200", "-p", "PrivateTmp=yes",
                   "-p", "ReadWritePaths=/opt/discordbot " + str(run) + " " + str(ROOT / "operations.lock"),
                   str(before / ".venv/bin/python"), "-I", "-B", str(helper), "--worker", "build",
                   "--commit", commit, "--run", str(run)]
        checked(command, 1250)
        built = json.loads((run / "build-result.json").read_text())
        evidence["build"] = built
        evidence["credentials"] = {}
        release = built["release"]
        python = Path("/opt/discordbot/releases") / release / ".venv/bin/python"
        for service, names in SCOPES.items():
            stage = "credential_" + service
            save()
            command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-phase10-check-" + service,
                       "-p", "User=" + ("discordbot-deploy" if service == "operations" else "discordbot"),
                       "-p", "Group=discordbot", "-p", "PrivateNetwork=yes", "-p", "ProtectSystem=strict",
                       "-p", "ProtectHome=yes", "-p", "NoNewPrivileges=yes", "-p", "RuntimeMaxSec=30"]
            for name in names:
                command += ["-p", "LoadCredential=" + name + ":" + str(source_secrets / name)]
            command += [str(python), "-I", "-B", str(helper), "--worker", service,
                        "--run", str(run), "--commit", commit, "--release", release]
            evidence["credentials"][service] = json.loads(checked(command, 45))
        evidence["staging_config_unchanged"] = digest(Path("/etc/discordbot/config.json")) == evidence["staging_config_sha256_before"]
        evidence["current_unchanged"] = Path("/opt/discordbot/current").resolve(strict=True) == before
        if not evidence["staging_config_unchanged"] or not evidence["current_unchanged"]:
            raise ValueError("Staging state changed")
        stage = "verified_not_activated"
        save()
        print("Candidate build and scoped credentials verified. No production login or activation.")
    except BaseException as error:
        evidence["failed_stage"] = stage
        evidence["error_type"] = type(error).__name__
        stage = "failed"
        save()
        print("Candidate verification stopped. See safe verification-progress.json; secrets not displayed.")
        raise SystemExit(1) from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--worker", choices=("build", *SCOPES))
    parser.add_argument("--release")
    args = parser.parse_args()
    if (not re.fullmatch(r"[0-9a-f]{40}", args.commit)
            or args.run != ROOT / ("phase10-readiness-" + args.commit[:12])):
        raise SystemExit("Reviewed commit and fixed isolated run required")
    if args.worker == "build":
        build_worker(args.run, args.commit)
    elif args.worker:
        if not args.release or not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", args.release):
            raise SystemExit("Reviewed release required")
        credential_worker(args.run, args.worker, args.release)
    else:
        if not args.archive_sha256 or not re.fullmatch(r"[0-9a-f]{64}", args.archive_sha256):
            raise SystemExit("Reviewed archive checksum required")
        parent(args.run, args.commit, args.archive_sha256)


if __name__ == "__main__":
    main()
