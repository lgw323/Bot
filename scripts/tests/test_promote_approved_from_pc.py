"""Operator-PC release transfer tests. SSH, sudo and systemd are never invoked."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("approved_pc", ROOT / "deploy/tools/promote_approved_from_pc.py")
pc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pc)
JOB = "a" * 32
COMMIT = "b" * 40
PREVIOUS = "c" * 40
STAGING = "/tmp/discordbot-upload.AB01234567"


@pytest.fixture
def workstation(tmp_path, monkeypatch):
    # The launcher must read only fixture transport files and the supplied key paths.
    folder = tmp_path / "operator tools"
    folder.mkdir()
    for name in pc.FILES:
        (folder / name).write_bytes(("fixture " + name).encode())
    monkeypatch.setattr(pc, "__file__", str(folder / pc.LAUNCHER))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    for name in ("known hosts", "identity"):
        (tmp_path / name).write_text("fixture", encoding="ascii")
    monkeypatch.setattr(pc, "uuid4", lambda: SimpleNamespace(hex=JOB))
    settings = ["--host", "fixture@192.0.2.8", "--host-key-alias", "fixture-pi",
                "--known-hosts", str(tmp_path / "known hosts"), "--identity", str(tmp_path / "identity")]
    return folder, settings, tmp_path / "result.json"


def invoke(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [pc.LAUNCHER, *args])
    return pc.main()


def complete(stage="deployed"):
    return dict(job=JOB, mode="promote", commit=COMMIT, phase="apply", stage=stage,
                done=True, success=True, exit=0)


def test_release_upload_uses_pinned_ssh_one_interactive_sudo_and_sanitized_receipt(workstation, monkeypatch):
    folder, settings, receipt = workstation
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    uploaded = {}
    interactive = []
    cleanup = []
    def run(argv, **kwargs):
        command = argv[-1]
        assert "fixture@192.0.2.8" == argv[-2]
        assert "StrictHostKeyChecking=yes" in argv and "GlobalKnownHostsFile=none" in argv
        assert "HostKeyAlias=fixture-pi" in argv and "ForwardAgent=no" in argv
        if "-tt" in argv:
            assert "stdin" not in kwargs
            interactive.append(shlex.split(command))
        elif "/usr/bin/mktemp" in command:
            return subprocess.CompletedProcess(argv, 0, (STAGING + "\n").encode())
        elif "/usr/bin/cat >" in command:
            name = shlex.split(command)[-1].removeprefix(STAGING + "/")
            uploaded[name] = kwargs["stdin"].read()
        elif "/usr/bin/head" in command:
            return subprocess.CompletedProcess(argv, 0, json.dumps(dict(complete(), private="discard")).encode())
        elif "/usr/bin/rmdir" in command:
            cleanup.append(command)
        else:
            pytest.fail("unexpected transport operation")
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", run)
    expected_hash = hashlib.sha256((folder / pc.BUNDLE).read_bytes()).hexdigest()
    result = invoke(monkeypatch, "promote", *settings, "--commit", COMMIT, "--previous", PREVIOUS,
                    "--bundle", str(folder / pc.BUNDLE), "--sha256", expected_hash, "--receipt", str(receipt))
    assert result == 0 and json.loads(receipt.read_bytes()) == complete()
    assert set(uploaded) == set(pc.FILES) and len(cleanup) == 1
    assert len(interactive) == 1
    cmd = interactive[0]
    assert cmd[:8] == ["/usr/bin/sudo", "-p", "[Pi release] sudo password: ", "--", "/usr/bin/python3", "-I", "-B", "-c"]
    compile(cmd[8], "<reviewed Pi bootstrap>", "exec")
    assert cmd[9:-1] == [STAGING, JOB, "promote", PREVIOUS, COMMIT, expected_hash]
    assert json.loads(cmd[-1]) == {name: [len(data), hashlib.sha256(data).hexdigest()]
                                    for name, data in uploaded.items()}


def test_observe_requires_no_upload_or_sudo_and_handles_terminal_receipt_race(workstation, monkeypatch):
    _, settings, receipt = workstation
    responses = iter(({"job": JOB, "mode": "promote", "commit": COMMIT, "stage": "stop_pair", "done": False},
                      "inactive", complete()))
    calls = []
    def read(ssh, host, args):
        calls.append(args[0])
        value = next(responses)
        return value if isinstance(value, str) else json.dumps(value)
    monkeypatch.setattr(pc, "read_remote", read)
    monkeypatch.setattr(pc, "submit", lambda *args: pytest.fail("observation submitted a job"))
    assert invoke(monkeypatch, "observe", *settings, "--job", JOB, "--receipt", str(receipt)) == 0
    assert calls == ["/usr/bin/head", "/usr/bin/systemctl", "/usr/bin/head"]
    assert json.loads(receipt.read_bytes()) == complete()


def test_hash_mismatch_and_existing_receipt_prevent_new_submission(workstation, monkeypatch):
    folder, settings, receipt = workstation
    monkeypatch.setattr(pc, "submit", lambda *args: pytest.fail("invalid input reached SSH"))
    args = ["promote", *settings, "--bundle", str(folder / pc.BUNDLE), "--commit", COMMIT,
            "--sha256", "0" * 64, "--receipt", str(receipt)]
    assert invoke(monkeypatch, *args) == 1
    first = receipt.read_bytes()
    assert json.loads(first)["done"] is False
    with pytest.raises(FileExistsError):
        invoke(monkeypatch, *args)
    assert receipt.read_bytes() == first


@pytest.mark.parametrize("change", [{"job": "x"}, {"stage": "unexpected"}, {"commit": int("1" * 40)},
                                     {"success": 1}, {"done": "yes"}])
def test_invalid_remote_receipt_is_never_success(change):
    with pytest.raises(ValueError):
        pc.validated_receipt(json.dumps({**complete(), **change}), JOB)


@pytest.mark.parametrize("prepare_outcome,apply_outcome,expected", [
    ("prepared", "deployed", 0),
    ("blocked", "deployed", 1),
    ("prepared", "blocked", 1),
    ("wrong_commit", "deployed", 1),
])
def test_host_worker_proves_prepare_before_apply(tmp_path, monkeypatch, prepare_outcome, apply_outcome, expected):
    # Model the two root-owned directories; the only subprocess is an in-memory double.
    base = tmp_path / "work"
    work = base / ("discordbot-promotion-" + JOB)
    work.mkdir(parents=True)
    observation = tmp_path / "observation"
    observation.mkdir()
    launcher = work / pc.LAUNCHER
    launcher.touch()
    monkeypatch.setattr(pc, "__file__", str(launcher))
    monkeypatch.setattr(pc, "Path", lambda raw: base if raw == "/var/tmp" else Path(raw))
    monkeypatch.setattr(pc, "observation_dir", lambda job: observation)
    monkeypatch.setattr(pc.os, "geteuid", lambda: 0, raising=False)
    original_stat = Path.lstat
    def fake_stat(path):
        if path in (work, observation):
            return SimpleNamespace(st_uid=0, st_mode=pc.stat.S_IFDIR | (0o700 if path == work else 0o711))
        return original_stat(path)
    monkeypatch.setattr(Path, "lstat", fake_stat)
    reports = []
    monkeypatch.setattr(pc, "write_status", lambda target, row: reports.append(dict(row)))
    phases = []
    class Child:
        def __init__(self, argv, **kwargs):
            phase = argv[4]
            phases.append(phase)
            stage = prepare_outcome if phase == "prepare" else apply_outcome
            assert argv[argv.index("--previous") + 1] == PREVIOUS
            assert argv[argv.index("--commit") + 1] == COMMIT
            note = ({"stage": "blocked", "reason": "executable_not_found", "exit_code": 1, "component": "systemd_manager"} if stage == "blocked" else
                    {"stage": "prepared", "commit": PREVIOUS} if stage == "wrong_commit" else
                    {"stage": stage, "commit": COMMIT})
            if stage == "blocked":
                note.update(action="test", failed_tests=["tests/integration/music/test_lookup.py::test_request"],
                            error_types=["ModuleNotFoundError"], missing_modules=["discord"],
                            pytest_counts={"passed": 62, "failed": 1})
            self.code = int(stage == "blocked")
            self.stdout = io.BytesIO(b'{"stage":"worker","action":"build"}\n' + json.dumps(note).encode() + b"\n")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def wait(self):
            return self.code
    monkeypatch.setattr(subprocess, "Popen", Child)
    assert pc.host_job(JOB, "promote", PREVIOUS, COMMIT, "d" * 64) == expected
    assert phases == (["prepare", "apply"] if prepare_outcome == "prepared" else ["prepare"])
    assert reports[-1]["done"] and reports[-1]["success"] is (expected == 0)
    if "blocked" in (prepare_outcome, apply_outcome):
        record = pc.validated_receipt(json.dumps(reports[-1]), JOB)
        assert (record["failed_at"], record["action"], record["reason"], record["exit_code"], record["component"]) == (
            "worker", "test", "executable_not_found", 1, "systemd_manager")
        assert record["failed_tests"] == ["tests/integration/music/test_lookup.py::test_request"]
        assert record["error_types"] == ["ModuleNotFoundError"] and record["missing_modules"] == ["discord"]
        assert record["pytest_counts"] == {"passed": 62, "failed": 1}



def test_detailed_host_failure_is_retained_and_unrecognized_fields_are_discarded():
    unit = "discordbot-promotion-" + JOB
    safe = dict(failed_at="worker", stage="blocked", reason="executable_not_found", action="build",
                component="systemd_manager", exit_code=1, unit=unit, property="BindReadOnlyPaths")
    receipt = {**complete(), **safe, "success": False, "stderr": "/private/example", "argv": ["secret"]}
    result = pc.validated_receipt(json.dumps(receipt), JOB)
    assert {field: result[field] for field in safe} == safe
    assert "stderr" not in result and "argv" not in result
    receipt.update(action="private", component="private", property="unknown", reason="pretend_secret", unit="other.service",
                   exit_code=True)
    result = pc.validated_receipt(json.dumps(receipt), JOB)
    assert result["reason"] == "unclassified_host_failure"
    assert not ({"action", "component", "property", "unit", "exit_code"} & result.keys())


@pytest.mark.parametrize("returncode,stderr,timed_out,reason", [
    (1, b"Failed to set unit properties: invalid RuntimeMaxSec /private/path", False, "unit_property_rejected"),
    (1, b"Failed to find executable /private/path", False, "executable_not_found"),
    (0, b"", True, "manager_submission_unconfirmed"),
])
def test_root_bootstrap_manager_failure_survives_without_child_unit(tmp_path, returncode, stderr, timed_out, reason):
    import builtins
    import os
    import stat

    stage = tmp_path / "upload"
    stage.mkdir()
    work_parent = tmp_path / "var-tmp"
    status_parent = tmp_path / "run"
    work_parent.mkdir()
    status_parent.mkdir()
    contents = b"fixture"
    inventory = {name: [len(contents), hashlib.sha256(contents).hexdigest()] for name in pc.FILES}
    for name in inventory:
        (stage / name).write_bytes(contents)
    uid = 123
    directory_fd = -55
    def opened(name, flags, *, dir_fd=None):
        if name == STAGING:
            return directory_fd
        assert dir_fd == directory_fd
        return os.open(stage / name, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    def metadata(fd):
        if fd == directory_fd:
            return SimpleNamespace(st_uid=uid, st_mode=stat.S_IFDIR | 0o700)
        real = os.fstat(fd)
        return SimpleNamespace(st_uid=uid, st_mode=stat.S_IFREG | 0o600, st_size=real.st_size)
    fake_os = SimpleNamespace(open=opened, close=lambda fd: None if fd == directory_fd else os.close(fd),
        fstat=metadata, fdopen=os.fdopen, replace=os.replace, link=os.link, fsync=os.fsync, fchmod=lambda *args: None,
        umask=lambda mode: None, geteuid=lambda: 0, environ={"SUDO_UID": str(uid)},
        O_DIRECTORY=0, O_RDONLY=0, O_NOFOLLOW=0, O_NONBLOCK=0)
    def manager(argv, **kwargs):
        assert argv[0] == "/usr/bin/systemd-run"
        if timed_out:
            raise subprocess.TimeoutExpired(argv, 60)
        return subprocess.CompletedProcess(argv, returncode, stderr=stderr)
    fake_subprocess = SimpleNamespace(run=manager, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL,
                                      TimeoutExpired=subprocess.TimeoutExpired)
    args = ["bootstrap", STAGING, JOB, "promote", PREVIOUS, COMMIT, inventory[pc.BUNDLE][1], json.dumps(inventory)]
    replacements = {"os": fake_os, "sys": SimpleNamespace(argv=args, exit=sys.exit), "subprocess": fake_subprocess,
                    "pathlib": SimpleNamespace(Path=lambda path: {"/var/tmp": work_parent, "/run": status_parent}[path])}
    def import_fixture(name, *args, **kwargs):
        if name in replacements:
            return replacements[name]
        return builtins.__import__(name, *args, **kwargs)
    exec(compile(pc.BOOTSTRAP, "<reviewed-fixture>", "exec"), {"__builtins__": {**vars(builtins), "__import__": import_fixture}})
    receipt = pc.validated_receipt((status_parent / ("discordbot-promotion-" + JOB) / "receipt.json").read_text(), JOB)
    assert receipt["failed_at"] == "manager_submission" and receipt["action"] == "submit"
    assert receipt["reason"] == reason and receipt["component"] == "systemd_manager"
    assert receipt["done"] is (not timed_out)
    assert receipt.get("property") == ("RuntimeMaxSec" if "properties" in stderr.decode() else None)
    assert "/private" not in json.dumps(receipt)


def test_native_test_diagnostics_survive_worker_and_observation_limits():
    # A valid batch deliberately exceeds both of the previous 2 KiB / 4 KiB gates.
    nodes = ["tests/integration/operations/test_" + "a" * 90 + str(i) + ".py::" + "C" * 95 +
             "::test_" + "y" * 90 for i in range(17)]
    note = {**complete(), "stage": "blocked", "reason": "native_tests_failed", "action": "test",
            "failed_tests": ["tests/integration/music/test_music.py::test_name[private-param]", *nodes],
            "missing_modules": ["private input", "../token", "discord.ui", "discord.ui", "a" * 97],
            "error_types": ["Traceback", {"bad": True}, "ImportError", "AssertionError", "OSError", "RuntimeError",
                            "TimeoutError", "TypeError", "KeyError", "Failed", "FileNotFoundError"],
            "pytest_counts": {"failed": 12, "passed": 31, "errors": True, "skipped": -1, "warnings": 10001, "unknown": 10}}
    assert 4096 < len(json.dumps(note)) < pc.RECEIPT_LIMIT
    local = pc.validated_receipt(json.dumps(note), JOB)
    assert local["failed_tests"] == nodes[:16]
    assert local["missing_modules"] == ["discord.ui"]
    assert len(local["error_types"]) == 8 and local["error_types"][0] == "ImportError"
    assert local["pytest_counts"] == {"failed": 12, "passed": 31}
    assert not ({"failed_tests", "missing_modules", "error_types", "pytest_counts"} &
                pc.diagnostic_fields({**note, "stage": "prepared"}).keys())
