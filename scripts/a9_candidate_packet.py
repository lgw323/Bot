"""Identity/coverage envelope for the single local candidate measurement packet.

Called from the existing offline pytest runner; no CLI/env config or destination.
Source is allowlisted workspace text, never an installed/ARM64 artifact claim.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import base64
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Callable

from scripts.a9_candidate_adapter import SCENARIO
from scripts.a9_local_harness import Config, run

ROOT = Path(__file__).resolve().parents[1]
MAX_PACKET_BYTES = 262144
WORKER_SECONDS = 10.0
COVERAGE = {
    "covered": ["DataRecovery.bootstrap synthetic new DB", "SqliteDatabase start/read/write/stop",
        "EngagementService start/message/profile/register_birthday/notify_guild/stop",
        "SqliteEngagementEvents transactions/dedupe", "SqliteEngagementRepository read/write",
        "actual SQLITE_BUSY with safe explicit retry", "rollback and precommit cancellation"],
    "fake": ["event inputs and wall/voice clock", "birthday delivery (10ms asyncio delay)"],
    "omitted": ["full composition root and Discord command ACK/transport", "engagement voice",
        "music actors/audio/provider/state restore", "Watch ASGI/WS/browser/lifecycle",
        "summary/Gemini", "backup/restore/retention/remote publication",
        "event loop lag/CPU/RSS/FD/disk throughput", "representative concurrency/capacity/24h",
        "Pi/ARM64 ABI and installed artifact/service validation"],
    "metrics": {"operation": "real perf_counter elapsed including verification suboperations",
        "worker": "candidate observations: queue before execution; execution includes SQLite lock wait",
        "sql_lock_wait": "not separately instrumented; do not interpret execution as pure SQL time",
        "percentiles": "nearest rank; successful operation samples only; n=1 per successful step",
        "failure_samples": "retained separately, including actual failed worker/awaiter outcomes"},
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _receipt_digest(packet: dict[str, Any]) -> str:
    # Local integrity only: not authentication against a writer replacing all records.
    return digest({key: value for key, value in packet.items() if key != "receipt_sha256"})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("packet identity has duplicate JSON entries")
        result[key] = value
    return result


def _validate_receipt(packet: dict[str, Any], source: dict[str, Any], *, exited: bool) -> None:
    """Check the same receipt contract at worker return and saved-packet reuse.

    Required entrypoints follow the execution protocol, not one fixture's import
    count. The checksum binds the entire measured module set (including optional
    imports) and packet contents; canonical paths/hashes bind entries to source.
    """
    try:
        execution = packet["execution"]
        modules = execution["modules"]
        files = source["files"]
        required = {"scripts.a9_candidate_packet", "scripts.a9_candidate_adapter",
                    "scripts.a9_local_harness"}
        if (type(packet["schema"]) is not int or packet["schema"] != 2
                or packet["receipt_sha256"] != _receipt_digest(packet)
                or packet["source"] != source
                or source["export_sha256"] != digest(files)
                or packet["config_sha256"] != digest(packet["config"])
                or packet["scenario_sha256"] != digest(packet["scenario"])
                or set(execution) != {"mode", "modules", "export_sha256", "bootstrap_sha256",
                    "interpreter", "dependency_identity", "worker_exit_verified", "parent_pipe_guard"}
                or execution["mode"] != "fresh isolated interpreter; verified in-memory source compilation"
                or execution["dependency_identity"] != "worker-installed distribution versions; wheel/ABI hashes not verified"
                or type(modules) is not dict or not required <= modules.keys()
                or execution["export_sha256"] != source["export_sha256"]
                or execution["bootstrap_sha256"] != hashlib.sha256(WORKER_BOOTSTRAP.encode()).hexdigest()
                or execution["worker_exit_verified"] is not exited
                or execution["parent_pipe_guard"] is not True):
            raise ValueError("packet identity receipt mismatch")
        interpreter = execution["interpreter"]
        fingerprint = interpreter["executable_sha256"]
        if (set(interpreter) != {"implementation", "version", "executable_sha256", "isolated", "bytecode_writes_disabled"}
                or type(interpreter["isolated"]) is not int or interpreter["isolated"] != 1
                or interpreter["bytecode_writes_disabled"] is not True
                or not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in fingerprint)
                or not all(isinstance(interpreter[key], str) and interpreter[key]
                           for key in ("implementation", "version"))):
            raise ValueError("packet identity interpreter schema mismatch")
        paths = set()
        for name, item in modules.items():
            if (not isinstance(name, str) or not all(part.isidentifier() for part in name.split("."))
                    or not (name.startswith("scripts.") or name == "discordbot" or name.startswith("discordbot."))
                    or type(item) is not dict or set(item) != {"path", "sha256"}):
                raise ValueError("packet identity module schema mismatch")
            stem = ("src/" if name.startswith("discordbot") else "") + name.replace(".", "/")
            # Match the frozen loader's package-first resolution exactly.
            relative = next((p for p in (stem + "/__init__.py", stem + ".py") if p in files), None)
            if (relative is None or item["path"] != relative or relative in paths
                    or item["sha256"] != files[relative]):
                raise ValueError("packet identity module source mismatch")
            paths.add(relative)
            parent = name.rpartition(".")[0]
            if parent and parent != "scripts" and parent not in modules:
                raise ValueError("packet identity missing package provenance")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("packet identity receipt schema mismatch") from error


def safe_hash(relative: str) -> str:
    path = ROOT / relative
    if not path.resolve().is_relative_to(ROOT) or any(
        item.is_symlink() or item.is_junction() for item in (path, *path.parents) if item != ROOT.parent
    ):
        raise ValueError("source must be regular workspace content")
    if path.suffix not in {".py", ".html", ".toml", ".txt", ".pins"} or path.stat().st_size > 1048576:
        raise ValueError("source export allowlist rejected")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity() -> dict[str, Any]:
    paths = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "src/discordbot").rglob("*")
                   if p.suffix in {".py", ".html"})
    paths += ["scripts/a9_local_harness.py", "scripts/a9_candidate_adapter.py",
              "scripts/a9_candidate_packet.py", "tests/integration/operations/test_a9_candidate_packet.py",
              "docs/rebuild/final-audit/a8r4-test-runner.py", "conftest.py", "tests/conftest.py",
              "pyproject.toml", "requirements.txt", "requirements-dev.txt", "deploy/dependencies.pins"]
    files = {p: safe_hash(p) for p in sorted(paths)}
    pins = {}
    for line in (ROOT / "deploy/dependencies.pins").read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.split("==", 1)
            try:
                installed = metadata.version(name)
            except metadata.PackageNotFoundError:
                installed = None
            pins[name] = {"pin": version, "installed": installed, "matches": version == installed}
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                           timeout=2).strip(),
        "export_kind": "verified frozen allowlisted bytes; working-tree origin, not Git HEAD or built artifact",
        "files": files, "export_sha256": digest(files), "dependency_pins": pins,
        "lock": {"path": "deploy/dependencies.pins", "sha256": files["deploy/dependencies.pins"],
                 "artifact_hash_lock": "absent from this packet"},
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
        "arm64_artifacts": "NOT_VERIFIED", "arm64_abi": "NOT_VERIFIED"}


def _measure(before: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Worker-only measurement; all application imports come from frozen bytes."""
    config = Config(run_id, "fake://a9/" + run_id,
        Path(tempfile.gettempdir()).resolve() / ("a9-campaign-" + run_id), ticks=1, max_seconds=5)
    # Identity contains only fixed safe settings; no actual temp home or env values.
    safe_config = asdict(config)
    safe_config["temp_root"] = "<canonical-os-temp>/a9-campaign-<run-id>"
    safe_config["run_id"], safe_config["target_identity"] = "<run-id>", "fake://a9/<run-id>"
    safe_config["execution_adapter"] = "closed candidate engagement/sqlite adapter"
    result = run(config, candidate=True)
    packet = {"schema": 2, "microphase": "PASS" if result["status"] == "complete" else "PARTIAL",
        "a9": "BLOCKED", "source": before,
        "config": safe_config, "config_sha256": digest(safe_config),
        "scenario": SCENARIO, "scenario_sha256": digest(SCENARIO),
        "data_identity": {"origin": "new empty DataRecovery.bootstrap plus fixed synthetic scenario",
                          "input_sha256": digest(SCENARIO), "real_data": False},
        "coverage": COVERAGE,
        "clock_resolution_seconds": {name: time.get_clock_info(name).resolution
                                     for name in ("monotonic", "perf_counter")},
        "guards": {"execution_seconds": 5, "cleanup_grace_seconds": 1,
                   "max_operations": 8, "max_observations": 128, "max_packet_bytes": MAX_PACKET_BYTES,
                   "kernel_hang_guard": False, "OS_resource_quota": False},
        "result": result}
    if len(json.dumps(packet).encode()) > MAX_PACKET_BYTES:
        raise ValueError("packet output budget exceeded")
    return packet


# This exact string is executed by -I -B -c and separately hashed in the receipt.
# Candidate modules are compiled from verified memory, never from sys.path/pycache.
WORKER_BOOTSTRAP = r'''
import base64, hashlib, importlib.abc, importlib.util, json, os, pathlib, sys, threading
from importlib import metadata
wire = sys.stdout
def parent_guard():
    os.read(sys.stdin.fileno(), 1)
    os._exit(90)  # Parent pipe closed: terminate all worker threads, no orphan.
threading.Thread(target=parent_guard, daemon=True, name="a9-parent-guard").start()
request = json.loads(pathlib.Path(sys.argv[1]).read_bytes())
root = pathlib.Path(request["root"])
sources = {p: base64.b64decode(v, validate=True) for p, v in request["bytes"].items()}
hashes = {p: hashlib.sha256(v).hexdigest() for p, v in sources.items()}
assert hashes == request["identity"]["files"]
assert hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == request["identity"]["export_sha256"]
def guard(event, args):
    if event in {"open", "sqlite3.connect"} and isinstance(args[0], (str, bytes, os.PathLike)):
        for path in (os.path.abspath(os.fsdecode(args[0])), os.path.realpath(os.fsdecode(args[0]))):
            name = os.path.basename(path)
            candidate = os.path.normcase(path)
            protected = [os.path.normcase(str(root / p)) + os.sep for p in ("data", "scratch/phase10")]
            if name == ".env" or name.startswith(".env.") or any(candidate.startswith(p) for p in protected):
                raise PermissionError("A9 worker denies protected input")
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname"}:
        frame = sys._getframe(1)
        while frame:
            if frame.f_code.co_name in {"socketpair", "_fallback_socketpair"} and frame.f_code.co_filename == __import__("socket").__file__:
                return
            frame = frame.f_back
        raise PermissionError("A9 worker denies network")
    if event in {"subprocess.Popen", "os.system", "os.fork", "os.posix_spawn", "os.spawn"}:
        raise PermissionError("A9 worker denies descendants")
sys.addaudithook(guard)
executed = {}
class Frozen(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "scripts":
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if fullname.startswith("scripts.") or fullname == "discordbot" or fullname.startswith("discordbot."):
            stem = ("src/" if fullname.startswith("discordbot") else "") + fullname.replace(".", "/")
            relative = next((p for p in (stem + "/__init__.py", stem + ".py") if p in sources), None)
            if relative is None:
                raise ImportError("module absent from verified source")
            spec = importlib.util.spec_from_loader(fullname, self, is_package=relative.endswith("/__init__.py"))
            spec.loader_state = relative
            return spec
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        relative = module.__spec__.loader_state
        if relative is None:  # Explicit scripts namespace, no disk search.
            module.__path__ = []
            return
        module.__file__ = str(root / relative)  # Logical origin; loader below owns bytes.
        executed[module.__name__] = {"path": relative, "sha256": hashes[relative]}
        exec(compile(sources[relative], module.__file__, "exec", dont_inherit=True), module.__dict__)
assert not any(n == "discordbot" or n.startswith(("discordbot.", "scripts.")) for n in sys.modules)
sys.meta_path.insert(0, Frozen())
# Suppress incidental candidate output; only the bounded protocol reaches parent.
sys.stdout = sys.stderr = open(os.devnull, "w")
from scripts import a9_candidate_packet as packet
source = request["identity"]
for name, pin in source["dependency_pins"].items():
    try:
        installed = metadata.version(name)
    except metadata.PackageNotFoundError:
        installed = None
    pin.update(installed=installed, matches=installed == pin["pin"])
source["platform"] = {"system": packet.platform.system(), "machine": packet.platform.machine(),
    "python": packet.platform.python_version(), "sqlite": packet.sqlite3.sqlite_version}
result = packet._measure(source, request["run_id"])
result["execution"] = {"mode": "fresh isolated interpreter; verified in-memory source compilation",
    "modules": executed, "export_sha256": source["export_sha256"],
    "bootstrap_sha256": request["bootstrap_sha256"],
    "interpreter": {"implementation": sys.implementation.name, "version": sys.version,
        "executable_sha256": hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest(),
        "isolated": sys.flags.isolated, "bytecode_writes_disabled": sys.dont_write_bytecode},
    "dependency_identity": "worker-installed distribution versions; wheel/ABI hashes not verified",
    "worker_exit_verified": False, "parent_pipe_guard": True}
result["receipt_sha256"] = packet._receipt_digest(result)
payload = json.dumps(result)
assert len(payload.encode()) <= packet.MAX_PACKET_BYTES
wire.write(payload)
wire.flush()
'''


def _frozen_bytes(before: dict[str, Any]) -> dict[str, str]:
    frozen = {}
    for relative, expected in before["files"].items():
        if safe_hash(relative) != expected:
            raise ValueError("source changed during capture")
        content = (ROOT / relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("source changed during capture")
        frozen[relative] = base64.b64encode(content).decode("ascii")
    return frozen


def _launch_worker(request: dict[str, Any], abort_requested: Callable[[], bool]) -> dict[str, Any]:
    # Inherit only OS interpreter/temp settings; no application credentials or PYTHONPATH.
    environment = {k: v for k, v in os.environ.items()
                   if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
                                    "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432",
                                    "PROCESSOR_IDENTIFIER"}}
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    process = None
    # A finite request file avoids a blocking pipe write before the launch deadline
    # (e.g. a stuck interpreter/site initialization). stdin is only a liveness pipe.
    with tempfile.TemporaryFile() as output, tempfile.NamedTemporaryFile(
            suffix="-a9-frozen.json", delete_on_close=False) as frozen:
        frozen.write(json.dumps(request).encode())
        frozen.flush()
        try:
            process = subprocess.Popen([sys.executable, "-I", "-B", "-c", WORKER_BOOTSTRAP, frozen.name],
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                cwd=tempfile.gettempdir(), env=environment)
            assert process.stdin is not None
            deadline = time.monotonic() + WORKER_SECONDS
            while process.poll() is None:
                if abort_requested():
                    raise InterruptedError("worker_cancelled")
                if time.monotonic() >= deadline:
                    raise TimeoutError("worker_timeout")
                try:
                    process.wait(timeout=.05)
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                raise ValueError("worker_failed")
            output.seek(0)
            content = output.read(MAX_PACKET_BYTES + 1)
            if len(content) > MAX_PACKET_BYTES:
                raise ValueError("worker_output_budget")
            return json.loads(content, object_pairs_hook=_unique_object)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
                if process.stdin is not None:
                    process.stdin.close()


def build_packet(*, abort_requested: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    """Certify only execution in a fresh worker bound to a verified byte snapshot.

    Launch/identity failures raise without returning a measurement certificate.
    Forced termination reaps the process but cannot promise graceful DB cleanup.
    """
    before = identity()
    request = {"root": str(ROOT), "identity": before, "bytes": _frozen_bytes(before),
               "run_id": uuid.uuid4().hex,
               "bootstrap_sha256": hashlib.sha256(WORKER_BOOTSTRAP.encode()).hexdigest()}
    if abort_requested():
        raise InterruptedError("worker_cancelled")
    try:
        packet = _launch_worker(request, abort_requested)
    except BaseException as error:
        error.add_note("No certificate; synthetic run " + request["run_id"]
                       + "; forced worker exit does not certify temporary DB cleanup")
        raise
    _validate_receipt(packet, before, exited=False)
    packet["execution"]["worker_exit_verified"] = True
    packet["source_unchanged_after_run"] = before == identity()
    if not packet["source_unchanged_after_run"]:
        packet["microphase"] = "PARTIAL"
    packet["guards"]["worker_wall_seconds"] = WORKER_SECONDS
    packet["guards"]["forced_exit_cleanup"] = "not guaranteed; no certificate on worker failure"
    packet["receipt_sha256"] = _receipt_digest(packet)
    if len(json.dumps(packet).encode()) > MAX_PACKET_BYTES:
        raise ValueError("packet output budget exceeded")
    return packet


def verify_packet(packet: dict[str, Any] | str | bytes) -> None:
    """Reject saved receipt drift; pass raw JSON to also reject duplicate keys.

    A previously decoded dict cannot retain evidence of duplicate JSON keys.
    Old receipts without the integrity field require fresh measurement, not repair.
    """
    try:
        if isinstance(packet, (str, bytes)):
            packet = json.loads(packet, object_pairs_hook=_unique_object)
        _validate_receipt(packet, identity(), exited=True)
        if packet["source_unchanged_after_run"] is not True:
            raise ValueError("source changed")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("saved packet identity drift") from error
