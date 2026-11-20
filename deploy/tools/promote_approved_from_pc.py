"""Run the reviewed Pi release procedure from an operator's Windows terminal."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


LAUNCHER = "promote_approved_from_pc.py"
PROMOTER = "promote_approved_fix.py"
WORKER = "prepare_approved_fix.py"
BUNDLE = "candidate.bundle"
FILES = (LAUNCHER, PROMOTER, WORKER, BUNDLE)
MODES = {"prepare": ("prepare",), "apply": ("apply",),
         "promote": ("prepare", "apply"), "rollback": ("rollback",)}
TERMINAL = {"prepare": "prepared", "apply": "deployed", "rollback": "rolled_back"}
STAGES = {"worker", "prepared", "preserving_backup", "pause_timers", "stop_pair",
          "recovering_previous_release", "previous_release_recovered", "uncertain_timers_disabled",
          "deployed", "rolled_back", "blocked", "queued", "starting", "interrupted",
          "upload_verification", "manager_submission"}
ACTIONS = {"build", "test", "publish", "install", "verify", "checkpoint", "quiescent", "switch",
           "submit", "start", "stop", "enable", "disable", "show"}
COMPONENTS = {"bootstrap", "host_supervisor", "systemd_manager", "native_worker", "service_manager"}
PROPERTIES = {"Type", "Restart", "RuntimeMaxSec", "TimeoutStopSec", "UMask", "StandardOutput", "StandardError",
              "User", "Group", "NoNewPrivileges", "ProtectSystem", "ProtectHome", "PrivateNetwork", "PrivateTmp",
              "KillMode", "InaccessiblePaths", "TemporaryFileSystem", "BindReadOnlyPaths", "BindPaths",
              "ReadWritePaths", "ReadOnlyPaths", "LoadCredential"}
TEST_NODE = re.compile(r"tests/integration/(?:music|operations)/test_[a-zA-Z0-9_]{1,96}\.py"
                       r"(?:::[a-zA-Z][a-zA-Z0-9_]{0,95}){0,2}")
MODULE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
TEST_ERRORS = frozenset("""
    AssertionError ImportError ModuleNotFoundError PermissionError FileNotFoundError OSError RuntimeError TypeError
    ValueError AttributeError KeyError TimeoutError ConnectionError CalledProcessError UnicodeDecodeError
    UnicodeEncodeError OperationalError DataIntegrityError ExternalTemporaryError Failed
""".split())
COUNT_KEYS = {"passed", "failed", "errors", "skipped", "xfailed", "xpassed", "deselected", "warnings"}
# All maximum-size allowlisted test fields together fit in a single receipt.
RECEIPT_LIMIT = 16384
REASONS = frozenset("""
    executable_not_found mount_namespace_failed unit_property_rejected invalid_property read_only permission_denied
    disk_full missing_path systemd_run_failed systemctl_failed python3_failed git_failed worker_failed operator_failure
    open_upload_failed upload_owner_mismatch upload_file_verification_failed root_staging_failed
    manager_executable_unavailable manager_submit_rejected manager_unit_exists manager_bus_unavailable
    manager_submission_unconfirmed supervisor_failed phase_not_verified unclassified_host_failure
    active_release_changed cannot_rearm_mixed_sources existing_candidate_without_test_receipt final_source_mismatch
    input_bundle_does_not_match_approval installed_manifest_changed insufficient_build_space invalid_build_receipt
    invalid_lock_inode invalid_operator_arguments missing_build_stage non_atomic_install_volume old_release_changed
    operations_job_busy pair_not_ready pair_stop_uncertain pending_or_unreadable_inbox prepared_receipt_changed
    preserving_backup_not_installed preserving_backup_unconfirmed previous_inputs_differ previous_transaction_needs_rollback
    release_changed_before_cutover release_or_approved_branch_moved source_switch_unconfirmed timer_restore_unconfirmed
    unexpected_active_directory unexpected_active_manifest unexpected_approved_branch unexpected_bundle_size
    unexpected_previous_source unexpected_timer_baseline unknown_recovery_identity unrecognized_active_release
    untrusted_operator_path untrusted_parent wheel_lock_changed bundle_commit bundle_ref candidate_already_installed
    candidate_identity checkpoint_source_changed checkpoint_unverified deployment_contract_changed invalid_checkpoint_source
    invalid_commit manifest_mismatch native_tests_failed pointer_unconfirmed release_count_cap source_blob_mismatch
    source_inventory_mismatch staged_candidate_exists unexpected_database unexpected_payload_member wrong_test_fixture
    wrong_worker_uid OSError PermissionError FileNotFoundError FileExistsError TimeoutError TimeoutExpired
    CalledProcessError ValueError KeyError RuntimeError DataIntegrityError ValidationError ConflictError CapacityError
""".split())
BASELINE = "22d53d291706d07e6e5f0d5b610b974123ee49cd"

# This small program is passed in the reviewed sudo command. Every executable
# copied from operator staging is checked before the system service can start.
BOOTSTRAP = r"""
import hashlib,json,os,pathlib,re,shutil,stat,subprocess,sys
stage, job, mode, previous, commit, digest, raw = sys.argv[1:]
manifest=json.loads(raw)
names=('promote_approved_from_pc.py','promote_approved_fix.py','prepare_approved_fix.py','candidate.bundle')
if (os.geteuid()!=0 or int(os.environ['SUDO_UID'])==0 or not re.fullmatch('[a-f0-9]{32}',job)
        or not re.fullmatch('/tmp/discordbot-upload[.][a-zA-Z0-9]{10}',stage)
        or mode not in ('prepare','promote','apply','rollback')
        or not re.fullmatch('[a-f0-9]{40}',previous) or previous==commit
        or not re.fullmatch('[a-f0-9]{40}',commit) or not re.fullmatch('[a-f0-9]{64}',digest)
        or set(manifest)!=set(names) or manifest['candidate.bundle'][1]!=digest):
    sys.exit('Invalid release transfer')
os.umask(0o077)
work=pathlib.Path('/var/tmp')/('discordbot-promotion-'+job)
status=pathlib.Path('/run')/('discordbot-promotion-'+job)
status.mkdir(mode=0o700)
status.chmod(0o711)
handle=None
progress='upload_verification'
reason='open_upload_failed'
details={}
submitted=False
owned_work=False
try:
    handle=os.open(stage,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    directory=os.fstat(handle)
    if directory.st_uid!=int(os.environ['SUDO_UID']) or stat.S_IMODE(directory.st_mode)!=0o700:
        reason='upload_owner_mismatch'
        sys.exit('Invalid upload directory')
    reason='root_staging_failed'
    work.mkdir(mode=0o700)
    owned_work=True
    reason='upload_file_verification_failed'
    for name in names:
        size,expected=manifest[name]
        with os.fdopen(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=handle),'rb') as src:
            meta=os.fstat(src.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=directory.st_uid or not 0<size==meta.st_size<=512*1024*1024:
                sys.exit('Invalid uploaded file')
            verifier=hashlib.sha256()
            with (work/name).open('xb') as dest:
                remaining=size
                while remaining:
                    block=src.read(min(remaining,1024*1024))
                    if not block: sys.exit('Upload truncated')
                    dest.write(block)
                    verifier.update(block)
                    remaining-=len(block)
                if src.read(1) or verifier.hexdigest()!=expected:
                    sys.exit('Upload changed')
    progress='manager_submission'
    reason='manager_executable_unavailable'
    run=['/usr/bin/systemd-run','--no-ask-password','--quiet','--collect',
         '--unit=discordbot-promotion-'+job,'--property=Type=exec','--property=Restart=no',
         '--property=RuntimeMaxSec=9000','--property=TimeoutStopSec=90',
         '--property=UMask=0077','--property=StandardOutput=null','--property=StandardError=null',
         '/usr/bin/python3','-I','-B',str(work/names[0]),'--host-job',job,mode,previous,commit,digest]
    launch=subprocess.run(run,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60,
                          env=dict(LC_ALL='C',PATH='/usr/sbin:/usr/bin:/sbin:/bin',HOME='/root'))
    if launch.returncode:
        diagnostic=launch.stderr[:8192].lower()
        reason='manager_submit_rejected'
        for pattern,code in ((b'failed to find executable','executable_not_found'),
                (b'failed to parse','invalid_property'),(b'failed to set unit properties','unit_property_rejected'),
                (b'already exists','manager_unit_exists'),(b'permission denied','permission_denied'),
                (b'failed to connect to bus','manager_bus_unavailable')):
            if pattern in diagnostic:
                reason=code
                break
        for key in ('Type','Restart','RuntimeMaxSec','TimeoutStopSec','UMask','StandardOutput','StandardError'):
            if re.search(rb'\b'+key.encode()+rb'\b',launch.stderr[:8192]):
                details['property']=key
                break
        details['exit_code']=launch.returncode
        raise RuntimeError(reason)
    submitted=True
except (OSError,ValueError,RuntimeError,SystemExit,subprocess.TimeoutExpired) as error:
    uncertain=isinstance(error,subprocess.TimeoutExpired)
    row=dict(job=job,mode=mode,commit=commit,done=not uncertain,stage='interrupted' if uncertain else 'blocked',
             failed_at=progress,reason='manager_submission_unconfirmed' if uncertain else reason,**details)
    row['component']='systemd_manager' if progress=='manager_submission' else 'bootstrap'
    if progress=='manager_submission':
        row.update(action='submit',unit='discordbot-promotion-'+job)
    if not uncertain:
        row['success']=False
    # Never overwrite a receipt owned by a job which actually started.
    with (status/'bootstrap.tmp').open('x',encoding='ascii') as receipt:
        json.dump(row,receipt)
        receipt.flush()
        os.fchmod(receipt.fileno(),0o644)
        os.fsync(receipt.fileno())
    try:os.link(status/'bootstrap.tmp',status/'receipt.json')
    except FileExistsError:pass
    finally:(status/'bootstrap.tmp').unlink()
finally:
    if handle is not None:os.close(handle)
    # A manager timeout may have dispatched the unit; never remove its inputs
    # after an ambiguous submission. The running job owns those files.
    if owned_work and not submitted and 'run' not in locals():
        shutil.rmtree(work)
"""


def observation_dir(job: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job):
        raise ValueError("Invalid job identifier")
    return Path("/run") / ("discordbot-promotion-" + job)


def write_status(folder: Path, report: dict[str, object]) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=folder, delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(report, stream, sort_keys=True)
        stream.flush()
        os.fchmod(stream.fileno(), 0o644)
        os.fsync(stream.fileno())
    try:
        os.replace(tmp, folder / "receipt.json")
    finally:
        tmp.unlink(missing_ok=True)


def diagnostic_fields(note: dict) -> dict:
    result = {}
    for field, choices in (("action", ACTIONS), ("component", COMPONENTS),
                           ("property", PROPERTIES), ("failed_at", STAGES)):
        value = note.get(field)
        if isinstance(value, str) and value in choices:
            result[field] = value
    if isinstance(note.get("unit"), str) and re.fullmatch(
            r"discordbot-promotion-[0-9a-f]{32}(?:\.service)?", note["unit"]):
        result["unit"] = note["unit"]
    if type(note.get("exit_code")) is int and 0 <= note["exit_code"] <= 255:
        result["exit_code"] = note["exit_code"]
    if type(note.get("reason")) is str:
        result["reason"] = note["reason"] if note["reason"] in REASONS else "unclassified_host_failure"
    if note.get("stage") == "blocked":
        for field, allowed, maximum in (
            ("failed_tests", TEST_NODE.fullmatch, 16),
            ("error_types", TEST_ERRORS.__contains__, 8),
            ("missing_modules", lambda name: len(name) <= 96 and MODULE_NAME.fullmatch(name), 8),
        ):
            values = note.get(field)
            if isinstance(values, list):
                selected = list(dict.fromkeys(v for v in values if isinstance(v, str) and allowed(v)))[:maximum]
                if selected:
                    result[field] = selected
        counts = note.get("pytest_counts")
        if isinstance(counts, dict):
            selected_counts = {k: v for k, v in counts.items() if k in COUNT_KEYS and type(v) is int and 0 <= v <= 10000}
            if selected_counts:
                result["pytest_counts"] = selected_counts
    return result


def host_job(job: str, mode: str, previous: str, commit: str, digest: str) -> int:
    folder = observation_dir(job)
    work = Path("/var/tmp") / ("discordbot-promotion-" + job)
    if (os.geteuid() != 0 or Path(__file__).resolve() != work / LAUNCHER
            or mode not in MODES or not re.fullmatch(r"[a-f0-9]{40}", previous) or previous == commit
            or not re.fullmatch(r"[a-f0-9]{40}", commit)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        return 1
    for path, permissions in ((work, 0o700), (folder, 0o711)):
        meta = path.lstat()
        if meta.st_uid != 0 or not stat.S_ISDIR(meta.st_mode) or stat.S_IMODE(meta.st_mode) != permissions:
            return 1
    report: dict[str, object] = {"job": job, "mode": mode, "commit": commit, "stage": "starting", "done": False}
    success = False
    try:
        write_status(folder, report)
        for phase in MODES[mode]:
            report.pop("action", None)
            report.update(phase=phase, stage="starting")
            write_status(folder, report)
            args = ["/usr/bin/python3", "-I", "-B", str(work / PROMOTER), phase, "--bundle", str(work / BUNDLE),
                    "--previous", previous, "--commit", commit, "--sha256", digest]
            expected_commit = previous if phase == "rollback" else commit
            verified = False
            with subprocess.Popen(args, cwd=work, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env={"HOME": "/root", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                  "LC_ALL": "C"}) as child:
                assert child.stdout is not None
                for line in child.stdout:
                    if len(line) > RECEIPT_LIMIT:
                        continue
                    try:
                        note = json.loads(line)
                    except (UnicodeError, ValueError, RecursionError):
                        continue
                    if not isinstance(note, dict) or type(note.get("stage")) is not str or note["stage"] not in STAGES:
                        continue
                    if note["stage"] == "blocked":
                        report["failed_at"] = report["stage"]
                    elif note["stage"] != "worker":
                        report.pop("action", None)
                    report["stage"] = note["stage"]
                    report.update(diagnostic_fields(note))
                    verified = note["stage"] == TERMINAL[phase] and note.get("commit") == expected_commit
                    write_status(folder, report)
                report["exit"] = child.wait()
            if report["exit"] != 0 or not verified:
                if "reason" not in report:
                    report["reason"] = "phase_not_verified"
                return 1
        success = True
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        report.update(failed_at=report["stage"], component="host_supervisor", reason="supervisor_failed")
        return 1
    finally:
        report.update(done=True, success=success)
        write_status(folder, report)
        # The source bundle and root scripts are no longer needed by the job.
        for name in FILES:
            (work / name).unlink(missing_ok=True)
        work.rmdir()


def ssh_args(args: argparse.Namespace) -> list[str]:
    user, delimiter, address = args.host.partition("@")
    if not delimiter or not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise ValueError("Expected USER@IP")
    ipaddress.ip_address(address)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", args.host_key_alias):
        raise ValueError("Invalid host key alias")
    known_hosts = args.known_hosts.resolve(strict=True).as_posix()
    if any(char in known_hosts for char in ('"', '%', '$', '\n', '\r')):
        raise ValueError("Unsupported known-hosts path")
    ssh = Path(os.environ["SystemRoot"]) / "System32/OpenSSH/ssh.exe"
    return [str(ssh), "-F", "none", "-i", str(args.identity.resolve(strict=True)), "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
            "-o", "VerifyHostKeyDNS=no", "-o", "GlobalKnownHostsFile=none", "-o", "ForwardAgent=no",
            "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=8",
            "-o", f'UserKnownHostsFile="{known_hosts}"', "-o", "HostKeyAlias=" + args.host_key_alias]


def read_remote(ssh: list[str], host: str, args: list[str]) -> str:
    result = subprocess.run([*ssh, "-T", host, shlex.join(args)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=25, check=True)
    if len(result.stdout) > RECEIPT_LIMIT:
        raise ValueError("Unexpected remote output size")
    return result.stdout.decode("ascii").strip()


def submit(args: argparse.Namespace, ssh: list[str], job: str, inventory: dict, files: dict[str, Path]) -> None:
    if not sys.stdin.isatty():
        raise ValueError("Run in an interactive Windows terminal")
    stage = read_remote(ssh, args.host, ["/usr/bin/mktemp", "-d", "/tmp/discordbot-upload.XXXXXXXXXX"])
    if not re.fullmatch(r"/tmp/discordbot-upload\.[A-Za-z0-9]{10}", stage):
        raise ValueError("Invalid staging path")
    try:
        for name, path in files.items():
            cmd = "umask 077 && set -C && /usr/bin/cat > " + shlex.quote(stage + "/" + name)
            with path.open("rb") as src:
                subprocess.run([*ssh, "-T", args.host, cmd], stdin=src, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=450)
        command = ["/usr/bin/sudo", "-p", "[Pi release] sudo password: ", "--", "/usr/bin/python3", "-I", "-B", "-c",
                   BOOTSTRAP, stage, job, args.mode, args.previous, args.commit, inventory[BUNDLE][1],
                   json.dumps(inventory, separators=(",", ":"))]
        print("Enter the Pi sudo password in this terminal if prompted.", flush=True)
        subprocess.run([*ssh, "-tt", args.host, shlex.join(command)], check=True)
    finally:
        cleanup = shlex.join(["/usr/bin/rm", "-f", "--", *(stage + "/" + name for name in FILES)])
        cleanup += " && " + shlex.join(["/usr/bin/rmdir", "--", stage])
        try:
            subprocess.run([*ssh, "-T", args.host, cleanup], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True, timeout=25)
        except (OSError, subprocess.SubprocessError):
            print("Temporary operator upload cleanup could not be confirmed.", file=sys.stderr)


def validated_receipt(raw: str, job: str) -> dict:
    note = json.loads(raw)
    if (type(note) is not dict or note.get("job") != job or type(note.get("mode")) is not str
            or note["mode"] not in MODES or type(note.get("commit")) is not str
            or not re.fullmatch(r"[a-f0-9]{40}", note["commit"])
            or type(note.get("stage")) is not str or note["stage"] not in STAGES or type(note.get("done")) is not bool):
        raise ValueError("Invalid receipt")
    result = {key: note[key] for key in ("job", "mode", "commit", "stage", "done")}
    if note.get("phase") in ("prepare", "apply", "rollback"):
        result["phase"] = note["phase"]
    result.update(diagnostic_fields(note))
    if type(note.get("exit")) is int and -255 <= note["exit"] <= 255:
        result["exit"] = note["exit"]
    if note["done"]:
        if type(note.get("success")) is not bool:
            raise ValueError("Missing terminal status")
        result["success"] = note["success"]
    return result


def observe(args: argparse.Namespace, ssh: list[str], job: str) -> dict:
    path = observation_dir(job).as_posix() + "/receipt.json"
    last = None
    deadline = time.monotonic() + 9130
    missing = 0
    while time.monotonic() < deadline:
        try:
            receipt = validated_receipt(read_remote(ssh, args.host, ["/usr/bin/head", "-c", str(RECEIPT_LIMIT + 1), "--", path]), job)
        except (OSError, ValueError, subprocess.SubprocessError):
            missing += 1
            if missing >= 5:
                raise RuntimeError("observation_unavailable")
        else:
            missing = 0
            if receipt != last:
                print(json.dumps(receipt, sort_keys=True), flush=True)
                last = receipt
            if receipt["done"]:
                return receipt
            state = read_remote(ssh, args.host, ["/usr/bin/systemctl", "show", "--property=ActiveState", "--value",
                                                "discordbot-promotion-" + job + ".service"])
            if state in {"inactive", "failed"}:
                # The terminal receipt and systemd state are two different reads.
                final = validated_receipt(read_remote(ssh, args.host, ["/usr/bin/head", "-c", str(RECEIPT_LIMIT + 1), "--", path]), job)
                if final["done"]:
                    return final
                if final.get("failed_at") == "manager_submission":
                    return final  # Preserve an ambiguous submit; never infer success.
                raise RuntimeError("service_ended_without_terminal_receipt")
        time.sleep(8)
    raise RuntimeError("observation_deadline")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(*MODES, "observe"))
    parser.add_argument("--host", required=True, metavar="USER@IP")
    parser.add_argument("--host-key-alias", required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--previous", help="exact approved predecessor commit (defaults to the November release)")
    parser.add_argument("--sha256", help="reviewed bundle digest, verified before upload")
    parser.add_argument("--job", help="job identifier printed by the submitting terminal")
    parser.add_argument("--receipt", type=Path, help="exclusive local result file")
    args = parser.parse_args()
    if args.mode == "observe":
        if not args.job or not re.fullmatch(r"[a-f0-9]{32}", args.job) or args.bundle or args.commit or args.previous or args.sha256:
            parser.error("observe requires --job")
        job = args.job
    else:
        args.previous = args.previous or BASELINE
        if (args.bundle is None or not re.fullmatch(r"[a-f0-9]{40}", args.commit or "") or args.job
                or not re.fullmatch(r"[a-f0-9]{40}", args.previous) or args.previous == args.commit
                or args.sha256 and not re.fullmatch(r"[a-f0-9]{64}", args.sha256)):
            parser.error("a new job requires --bundle and a full --commit")
        job = uuid4().hex
    local = args.receipt.open("x", encoding="ascii") if args.receipt else None
    report = {"job": job, "mode": args.mode, "stage": "starting", "done": False}
    try:
        print(json.dumps(report), flush=True)
        if local:
            local.write(json.dumps(report) + "\n")
            local.flush()
        ssh = ssh_args(args)
        if args.mode != "observe":
            folder = Path(__file__).resolve().parent
            paths = {name: folder / name for name in FILES}
            paths[BUNDLE] = args.bundle
            inventory = {}
            for name, path in paths.items():
                with path.open("rb") as src:
                    size = os.fstat(src.fileno()).st_size
                    if not 0 < size <= 512 * 1024 * 1024:
                        raise ValueError("Release file size outside limit")
                    inventory[name] = [size, hashlib.file_digest(src, "sha256").hexdigest()]
            if args.sha256 and args.sha256 != inventory[BUNDLE][1]:
                raise ValueError("Reviewed bundle digest mismatch")
            submit(args, ssh, job, inventory, paths)
        report = observe(args, ssh, job)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        report.update(stage="interrupted", reason=type(error).__name__)
        print("Use observe --job " + job + " with the same pinned host settings to check a submitted job.", flush=True)
    finally:
        print(json.dumps(report, sort_keys=True), flush=True)
        if local:
            with local:
                local.seek(0)
                local.truncate()
                local.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report.get("done") and report.get("success") else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["--host-job"]:
        raise SystemExit(host_job(*sys.argv[2:]))
    raise SystemExit(main())
