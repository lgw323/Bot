"""Offline real-candidate probes; no real data/config, provider or service access."""
from collections import Counter
import copy
from dataclasses import replace
import json
import hashlib
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import threading
import uuid

import pytest

from scripts import a9_candidate_adapter as adapter
from scripts import a9_candidate_packet as packet
from scripts import a9_local_harness as harness
from discordbot.platform.errors import DataIntegrityError


@pytest.fixture
def config():
    identity = uuid.uuid4().hex
    return harness.Config(identity, "fake://a9/" + identity,
        Path(tempfile.gettempdir()).resolve() / ("a9-campaign-" + identity), ticks=1, max_seconds=5)


def test_candidate_paths_persist_atomic_results_and_measure_actual_work(config, monkeypatch):
    calls = Counter()
    original = adapter.SqliteDatabase._transaction
    async def observe(self, *args, **kwargs):
        calls["write" if kwargs["writable"] else "read"] += 1
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(adapter.SqliteDatabase, "_transaction", observe)
    before_threads = set(threading.enumerate())
    result = harness.run(config, candidate=True)
    assert result["status"] == "complete", result
    assert result["cleanup_complete"] and not config.temp_root.exists()
    assert set(threading.enumerate()) <= before_threads
    assert result["owned_workers_remaining"] == 0
    assert result["candidate"]["loop_closed"] and result["candidate"]["database_stopped"]
    assert len(result["candidate"]["checks"]) == 9
    assert all(result["candidate"]["checks"].values())
    assert calls["read"] >= 6 and calls["write"] >= 10
    samples = result["samples"]
    assert result["planned_operations"] == result["recorded_operations"] == len(samples) == 8
    assert result["missing_operations"] == 0
    assert result["classifications"] == dict(Counter(s["classification"] for s in samples))
    assert result["classifications"] == {"ok": 5, "expected_db_busy": 1,
        "expected_rollback": 1, "expected_cancellation": 1}
    for sample in samples:
        measured = result["latency"][sample["kind"]]
        assert measured["successful_samples"] == int(sample["classification"] == "ok")
        assert measured["p95_seconds"] == (sample["latency_seconds"] if sample["classification"] == "ok" else None)
        assert sample["latency_seconds"] > 0
    assert samples[6]["latency_seconds"] >= .009  # Actual awaited fake IO, not a label.
    observations = result["candidate"]["database_observations"]
    workers = [o for o in observations if o["phase"] == "worker_finished"]
    # Two maintenance/inspect workers, minus one post-stop rejected read.
    assert len(workers) == sum(calls.values()) + 2 - 1
    assert len(observations) == len(workers) + 3  # busy, rollback, cancelled awaiters
    assert any(o["step"] == "busy_write" and o["result"] == "database_unavailable" for o in workers)
    assert any(o["step"] == "cancel_write" and o["result"] == "cancellation" for o in workers)
    assert all(o["queue_seconds"] >= 0 and o["execution_seconds"] >= 0 for o in workers)


def test_original_fake_control_still_has_no_candidate_transactions(config, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("fake control entered candidate")
    monkeypatch.setattr(adapter.SqliteDatabase, "__init__", forbidden)
    result = harness.run(config)
    assert result["recorded_operations"] == 4 and "candidate" not in result


def test_unexpected_actual_service_failure_keeps_attempt_and_prior_samples(config, monkeypatch):
    async def broken(*args, **kwargs):
        raise DataIntegrityError("NEVER_EXPORT_RAW_FAILURE")
    monkeypatch.setattr(adapter.EngagementService, "profile", broken)
    result = harness.run(config, candidate=True)
    assert result["status"] == "aborted" and result["reason"] == "unexpected_fault"
    assert result["recorded_operations"] == 3 and result["missing_operations"] == 5
    assert result["classifications"] == {"ok": 2, "unexpected_fault": 1}
    assert result["samples"][-1]["kind"] == "profile_read"
    assert result["cleanup_complete"] and result["owned_workers_remaining"] == 0
    assert "NEVER_EXPORT_RAW_FAILURE" not in json.dumps(result)


@pytest.mark.parametrize("field,value,reason", [
    ("max_operations", 2, "operation_budget"), ("max_output_bytes", 1, "output_budget"),
    ("max_seconds", .01, "harness_error"),
])
def test_candidate_guards_preserve_and_cleanup(config, field, value, reason):
    result = harness.run(replace(config, **{field: value}), candidate=True)
    assert result["status"] == "aborted"
    # Fast machines may finish setup before the time ceiling, then stop at boundary.
    assert result["reason"] in ({"harness_error", "time_budget", "unexpected_fault"} if field == "max_seconds" else {reason})
    assert result["cleanup_complete"] and not config.temp_root.exists()
    assert result["owned_workers_remaining"] == 0
    assert result["recorded_operations"] + result["missing_operations"] == 8
    if field == "max_output_bytes":
        assert not result["samples"] and not result["candidate"]["checks"]


def test_operator_abort_stops_setup_workers(config):
    result = harness.run(config, candidate=True, abort_requested=lambda: True)
    assert result["reason"] == "operator_abort" and result["cleanup_complete"]
    assert result["owned_workers_remaining"] == 0 and not result["samples"]
    assert result["candidate"] == {}  # Guard runs before opening a DB.


def test_wrong_sqlite_error_is_not_mislabeled_expected_busy(config, monkeypatch):
    from discordbot.platform.errors import DatabaseUnavailableError
    original = adapter.CandidateAdapter.message
    async def wrong_failure(self, event="one"):
        if event == "busy":
            raise DatabaseUnavailableError("synthetic wrong cause", context={"sqlite_code": 10})
        return await original(self, event)
    monkeypatch.setattr(adapter.CandidateAdapter, "message", wrong_failure)
    result = harness.run(config, candidate=True)
    assert result["reason"] == "unexpected_fault" and result["recorded_operations"] == 4
    assert "expected_db_busy" not in result["classifications"]
    assert result["cleanup_complete"]


def test_existing_target_refused_without_reading_or_removing_sentinel(config):
    config.temp_root.mkdir()
    sentinel = config.temp_root / "unowned.txt"
    sentinel.write_text("synthetic sentinel")
    try:
        with pytest.raises(harness.UnsafeTarget):
            harness.run(config, candidate=True)
        assert sentinel.read_text() == "synthetic sentinel"
    finally:
        sentinel.unlink()
        config.temp_root.rmdir()


def test_cleanup_failure_preserves_original_fault_and_observations(config, monkeypatch):
    original = adapter.CandidateAdapter.operation
    async def broken(self, step):
        if step == "profile_read":
            (self.root / "unowned.txt").write_text("synthetic sentinel")
            raise RuntimeError("synthetic fault")
        return await original(self, step)
    monkeypatch.setattr(adapter.CandidateAdapter, "operation", broken)
    result = harness.run(config, candidate=True)
    try:
        assert result["reason"] == "cleanup_failed"
        assert result["primary_reason"] == "unexpected_fault"
        assert result["samples"][-1]["classification"] == "unexpected_fault"
        assert result["candidate"]["database_observations"]
        assert result["owned_workers_remaining"] == 0
        assert (config.temp_root / "unowned.txt").read_text() == "synthetic sentinel"
    finally:
        (config.temp_root / "unowned.txt").unlink()
        config.temp_root.rmdir()


def test_changed_root_drains_without_service_flush_or_file_deletion(config, monkeypatch):
    changed = False
    flushes = []
    original_step = adapter.CandidateAdapter.operation
    original_flag = Path.is_junction
    original_stop = adapter.EngagementService.stop
    async def marked(self, step):
        nonlocal changed
        result = await original_step(self, step)
        changed = True
        return result
    async def stop(self):
        flushes.append(1)
        return await original_stop(self)
    monkeypatch.setattr(adapter.CandidateAdapter, "operation", marked)
    monkeypatch.setattr(adapter.EngagementService, "stop", stop)
    monkeypatch.setattr(Path, "is_junction", lambda self: True if self == config.temp_root and changed else original_flag(self))
    result = harness.run(config, candidate=True)
    changed = False
    try:
        assert result["reason"] == "cleanup_refused"
        assert result["primary_reason"] == "target_changed"
        assert result["owned_workers_remaining"] == 0 and not flushes
        assert (config.temp_root / "synthetic.db").exists()
    finally:
        for name in ("synthetic.db", "synthetic.db-wal", "synthetic.db-shm", "samples.jsonl"):
            (config.temp_root / name).unlink(missing_ok=True)
        config.temp_root.rmdir()


@pytest.mark.parametrize("changes", [{"ticks": 2}, {"multiplier": 2}, {"fault": "db_busy"},
    {"temp_root": Path("data")}, {"target_identity": "https://example.invalid"}])
def test_candidate_closed_configuration_rejects_before_creation(config, changes):
    with pytest.raises(harness.UnsafeTarget):
        harness.run(replace(config, **changes), candidate=True)
    assert not config.temp_root.exists()


def test_source_path_escape_and_identity_changes_are_detected(monkeypatch):
    with pytest.raises(ValueError):
        packet.safe_hash("../escape.py")
    original = packet.safe_hash
    before = packet.identity()
    monkeypatch.setattr(packet, "safe_hash", lambda name: "0" * 64 if name == "scripts/a9_candidate_adapter.py" else original(name))
    assert packet.identity()["export_sha256"] != before["export_sha256"]


def test_packet_identity_coverage_and_sanitized_bounds():
    result = packet.build_packet()
    assert result["microphase"] == "PASS" and result["a9"] == "BLOCKED"
    assert result["source_unchanged_after_run"]
    assert result["source"]["export_sha256"] == packet.digest(result["source"]["files"])
    assert result["config_sha256"] == packet.digest(result["config"])
    assert result["scenario_sha256"] == packet.digest(result["scenario"])
    assert result["source"]["arm64_abi"] == "NOT_VERIFIED"
    assert result["coverage"]["omitted"]
    assert len(json.dumps(result).encode()) < packet.MAX_PACKET_BYTES
    assert str(Path(tempfile.gettempdir())) not in json.dumps(result)


def test_packet_refuses_source_drift_as_pass(monkeypatch):
    original = packet.identity
    count = 0
    def changed():
        nonlocal count
        value = original()
        count += 1
        if count > 1:
            value["export_sha256"] = "0" * 64
        return value
    monkeypatch.setattr(packet, "identity", changed)
    result = packet.build_packet()
    assert result["microphase"] == "PARTIAL" and not result["source_unchanged_after_run"]


@pytest.fixture
def frozen_export(tmp_path, monkeypatch):
    origin = packet.ROOT
    export = tmp_path / "export"
    for relative in packet.identity()["files"]:
        target = export / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((origin / relative).read_bytes())
    monkeypatch.setenv("GIT_DIR", str(origin / ".git"))
    monkeypatch.setattr(packet, "ROOT", export)
    return export


def poison_adapter(export):
    path = export / "scripts/a9_candidate_adapter.py"
    before = path.read_text(encoding="utf-8")
    needle = '        return await self.app.message(100, 10, event, "abc", self.app.clock.now())'
    assert before.count(needle) == 1
    path.write_text(before.replace(needle,
        '        raise RuntimeError("AUDIT_CHANGED_CODE_EXECUTED")\n' + needle), encoding="utf-8")
    return path


def test_stale_imports_cannot_certify_changed_export(frozen_export):
    # Adapter, packet and storage were already imported from a DIFFERENT source path.
    path = poison_adapter(frozen_export)
    result = packet.build_packet()
    assert result["microphase"] == "PARTIAL"
    assert result["result"]["reason"] == "unexpected_fault"
    assert result["result"]["recorded_operations"] == 1
    assert result["result"]["cleanup_complete"]
    assert result["result"]["owned_workers_remaining"] == 0
    measured = result["execution"]["modules"]["scripts.a9_candidate_adapter"]
    assert measured["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["execution"]["worker_exit_verified"]
    packet.verify_packet(result)  # Identity verified, never a functional PASS claim.


def test_timestamp_size_valid_stale_pycache_is_never_executed(frozen_export):
    path = frozen_export / "scripts/a9_candidate_adapter.py"
    before = path.read_bytes()
    stamp = path.stat()
    py_compile.compile(str(path), doraise=True)
    needle = b'return await self.app.message(100, 10, event, "abc", self.app.clock.now())'
    replacement = b'raise RuntimeError("STALE_BYTECODE_MUST_NOT_RUN")'
    changed = before.replace(needle, replacement.ljust(len(needle)))
    assert len(before) == len(changed) and before != changed
    path.write_bytes(changed)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    result = packet.build_packet()
    assert result["microphase"] == "PARTIAL"
    assert result["result"]["reason"] == "unexpected_fault"
    assert result["result"]["cleanup_complete"]


def test_capture_race_refused_before_worker_launch(frozen_export, monkeypatch):
    original = packet._frozen_bytes
    def capture(before):
        poison_adapter(frozen_export)
        return original(before)
    monkeypatch.setattr(packet, "_frozen_bytes", capture)
    with pytest.raises(ValueError, match="source changed during capture"):
        packet.build_packet()


def test_change_after_capture_executes_frozen_bytes_and_marks_drift(frozen_export, monkeypatch):
    original = packet._launch_worker
    def launch(request, abort):
        poison_adapter(frozen_export)
        return original(request, abort)
    monkeypatch.setattr(packet, "_launch_worker", launch)
    result = packet.build_packet()
    assert result["microphase"] == "PARTIAL" and not result["source_unchanged_after_run"]
    assert result["result"]["recorded_operations"] == 8
    assert result["result"]["cleanup_complete"]
    measured = result["execution"]["modules"]["scripts.a9_candidate_adapter"]
    assert measured["sha256"] != hashlib.sha256(
        (frozen_export / measured["path"]).read_bytes()).hexdigest()


def test_changed_packet_configuration_is_measured_in_fresh_worker(frozen_export):
    path = frozen_export / "scripts/a9_candidate_packet.py"
    path.write_text(path.read_text(encoding="utf-8").replace("ticks=1, max_seconds=5)",
        "ticks=1, max_seconds=4)"), encoding="utf-8")
    result = packet.build_packet()
    assert result["microphase"] == "PASS"
    assert result["config"]["max_seconds"] == 4
    assert result["config_sha256"] == packet.digest(result["config"])


def test_saved_manifest_rejects_post_generation_source_drift(frozen_export):
    result = packet.build_packet()
    packet.verify_packet(result)
    poison_adapter(frozen_export)
    with pytest.raises(ValueError, match="saved packet identity drift"):
        packet.verify_packet(result)


def test_worker_launch_failure_never_returns_a_certificate(monkeypatch):
    original = subprocess.Popen
    def launch(args, **kwargs):
        if "-I" in args:
            raise OSError("synthetic launch failure")
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(OSError, match="synthetic launch failure"):
        packet.build_packet()


@pytest.mark.parametrize("mode", ["timeout", "cancel", "interrupt"])
def test_worker_stall_or_cancellation_reaps_process(frozen_export, monkeypatch, mode):
    path = frozen_export / "scripts/a9_candidate_adapter.py"
    path.write_text(path.read_text(encoding="utf-8") + "\ntime.sleep(30)\n", encoding="utf-8")
    children = []
    original = subprocess.Popen
    def launch(args, **kwargs):
        child = original(args, **kwargs)
        if "-I" in args:
            children.append(child)
        return child
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(packet, "WORKER_SECONDS", .3)
    def abort():
        if children and mode == "interrupt":
            raise KeyboardInterrupt()
        return bool(children) and mode == "cancel"
    error = {"timeout": TimeoutError, "cancel": InterruptedError, "interrupt": KeyboardInterrupt}[mode]
    with pytest.raises(error):
        packet.build_packet(abort_requested=abort)
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdin.closed


def test_parent_pipe_loss_terminates_worker_before_orphan(frozen_export, monkeypatch):
    path = frozen_export / "scripts/a9_candidate_adapter.py"
    path.write_text(path.read_text(encoding="utf-8") + "\ntime.sleep(30)\n", encoding="utf-8")
    before = packet.identity()
    request = {"root": str(frozen_export), "identity": before, "bytes": packet._frozen_bytes(before),
        "run_id": uuid.uuid4().hex, "bootstrap_sha256": hashlib.sha256(packet.WORKER_BOOTSTRAP.encode()).hexdigest()}
    request_path = frozen_export.parent / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    child = subprocess.Popen([sys.executable, "-I", "-B", "-c", packet.WORKER_BOOTSTRAP, str(request_path)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        child.stdin.close()  # Same EOF observed after abrupt parent exit.
        assert child.wait(timeout=5) == 90
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)


@pytest.mark.parametrize("payload", ["raise RuntimeError('worker crash')",
    "import socket; socket.create_connection(('example.invalid', 80))",
    "import subprocess; subprocess.run(['forbidden-child'])"])
def test_worker_fault_and_external_actions_fail_closed(frozen_export, payload):
    path = frozen_export / "scripts/a9_candidate_adapter.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + payload + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="worker_failed"):
        packet.build_packet()


def test_stale_parent_storage_and_harness_are_not_measurement_dependencies(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("already loaded parent code executed")
    monkeypatch.setattr(adapter.SqliteDatabase, "_transaction", forbidden)
    monkeypatch.setattr(packet, "run", forbidden)
    result = packet.build_packet()
    assert result["microphase"] == "PASS"
    assert result["result"]["recorded_operations"] == 8
    assert result["result"]["candidate"]["database_observations"]
    for name in ("scripts.a9_local_harness", "discordbot.storage.adapters.execution"):
        assert name in result["execution"]["modules"]
    assert result["execution"]["interpreter"]["isolated"] == 1


def test_corrupted_frozen_payload_rejected_by_worker_before_measurement(monkeypatch):
    original = packet._launch_worker
    def launch(request, abort):
        request["bytes"]["scripts/a9_candidate_adapter.py"] = "cGFzcw=="
        return original(request, abort)
    monkeypatch.setattr(packet, "_launch_worker", launch)
    with pytest.raises(ValueError, match="worker_failed"):
        packet.build_packet()


def test_operator_abort_before_launch_does_not_create_process(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("worker started after cancellation")
    monkeypatch.setattr(packet, "_launch_worker", forbidden)
    with pytest.raises(InterruptedError, match="worker_cancelled"):
        packet.build_packet(abort_requested=lambda: True)


@pytest.mark.parametrize("field", ["config", "scenario", "execution"])
def test_saved_packet_metadata_drift_is_rejected(field):
    result = packet.build_packet()
    if field == "execution":
        result[field]["modules"]["scripts.a9_candidate_adapter"]["sha256"] = "0" * 64
    else:
        result[field]["unmeasured"] = True
    with pytest.raises(ValueError, match="saved packet identity drift"):
        packet.verify_packet(result)


@pytest.fixture(scope="module")
def saved_receipt():
    result = packet.build_packet()
    assert result["microphase"] == "PASS"
    packet.verify_packet(result)
    return result


def test_saved_packet_requires_measured_adapter_provenance(saved_receipt):
    damaged = copy.deepcopy(saved_receipt)
    damaged["execution"]["modules"].pop("scripts.a9_candidate_adapter")
    assert damaged["microphase"] == "PASS"
    with pytest.raises(ValueError, match="identity"):
        packet.verify_packet(damaged)


def test_receipt_covers_every_measured_module_without_fixed_import_count(saved_receipt):
    for name in saved_receipt["execution"]["modules"]:
        damaged = copy.deepcopy(saved_receipt)
        damaged["execution"]["modules"].pop(name)
        with pytest.raises(ValueError, match="identity"):
            packet.verify_packet(damaged)


def damage_receipt(result, mutation):
    execution = result["execution"]
    modules = execution["modules"]
    adapter_name = "scripts.a9_candidate_adapter"
    if mutation.startswith("missing_required:"):
        modules.pop(mutation.split(":", 1)[1])
    elif mutation == "empty_modules":
        execution["modules"] = {}
    elif mutation == "missing_modules":
        execution.pop("modules")
    elif mutation == "list_modules":
        execution["modules"] = list(modules.values())
    elif mutation == "null_entry":
        modules[adapter_name] = None
    elif mutation == "missing_hash":
        modules[adapter_name].pop("sha256")
    elif mutation == "extra_entry_field":
        modules[adapter_name]["unmeasured"] = True
    elif mutation == "extra_module":
        modules["scripts.unmeasured"] = {"path": "scripts/unmeasured.py", "sha256": "0" * 64}
    elif mutation == "duplicate_path":
        modules["scripts.alias"] = copy.deepcopy(modules[adapter_name])
    elif mutation == "swapped_names":
        other = "scripts.a9_local_harness"
        modules[adapter_name], modules[other] = modules[other], modules[adapter_name]
    elif mutation == "wrong_hash":
        modules[adapter_name]["sha256"] = "0" * 64
    elif mutation == "wrong_path":
        modules[adapter_name]["path"] = "../a9_candidate_adapter.py"
    elif mutation == "missing_parent":
        modules.pop("discordbot")
    elif mutation in {"export_sha256", "bootstrap_sha256"}:
        execution[mutation] = "0" * 64
    elif mutation == "source_binding":
        result["source"]["files"]["scripts/a9_local_harness.py"] = "0" * 64
        result["source"]["export_sha256"] = packet.digest(result["source"]["files"])
    elif mutation == "bad_interpreter":
        execution["interpreter"]["isolated"] = True  # bool must not satisfy int schema
    elif mutation == "missing_interpreter":
        execution.pop("interpreter")
    elif mutation == "missing_mode":
        execution.pop("mode")
    elif mutation == "false_parent_guard":
        execution["parent_pipe_guard"] = False
    elif mutation == "truthy_exit":
        execution["worker_exit_verified"] = "true"
    elif mutation == "truthy_unchanged":
        result["source_unchanged_after_run"] = "true"
    else:
        raise AssertionError(mutation)


@pytest.mark.parametrize("mutation", [
    "missing_required:scripts.a9_candidate_adapter", "missing_required:scripts.a9_candidate_packet",
    "missing_required:scripts.a9_local_harness", "empty_modules", "missing_modules", "list_modules",
    "null_entry", "missing_hash", "extra_entry_field", "extra_module", "duplicate_path", "swapped_names",
    "wrong_hash", "wrong_path", "missing_parent", "export_sha256", "bootstrap_sha256", "source_binding",
    "bad_interpreter", "missing_interpreter", "missing_mode", "false_parent_guard", "truthy_exit",
    "truthy_unchanged",
])
def test_receipt_invariants_fail_closed_even_with_recomputed_checksum(saved_receipt, mutation):
    damaged = copy.deepcopy(saved_receipt)
    damage_receipt(damaged, mutation)
    damaged["receipt_sha256"] = packet._receipt_digest(damaged)
    with pytest.raises(ValueError, match="identity"):
        packet.verify_packet(damaged)


@pytest.mark.parametrize("mutation", ["missing", "changed", "extra_allowed_module", "changed_result"])
def test_whole_receipt_integrity_is_required(saved_receipt, mutation):
    damaged = copy.deepcopy(saved_receipt)
    if mutation == "missing":
        damaged.pop("receipt_sha256")
    elif mutation == "changed":
        damaged["receipt_sha256"] = "0" * 64
    elif mutation == "changed_result":
        damaged["result"]["recorded_operations"] += 1
    else:
        # An unexecuted yet allowlisted module is still a receipt alteration.
        files = damaged["source"]["files"]
        relative = next(p for p in files if p.startswith("src/discordbot/") and p.endswith(".py")
                        and p not in {m["path"] for m in damaged["execution"]["modules"].values()})
        name = relative.removeprefix("src/").removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        damaged["execution"]["modules"][name] = {"path": relative, "sha256": files[relative]}
    with pytest.raises(ValueError, match="identity"):
        packet.verify_packet(damaged)


def test_saved_json_rejects_duplicate_module_keys_and_accepts_reordering(saved_receipt):
    raw = json.dumps(saved_receipt, sort_keys=True)
    packet.verify_packet(raw)
    packet.verify_packet(raw.encode())
    duplicate = '"scripts.a9_candidate_adapter": ' + json.dumps(
        saved_receipt["execution"]["modules"]["scripts.a9_candidate_adapter"])
    damaged = raw.replace('"modules": {', '"modules": {' + duplicate + ', ', 1)
    with pytest.raises(ValueError, match="identity"):
        packet.verify_packet(damaged)
    with pytest.raises(ValueError, match="duplicate"):
        json.loads(damaged, object_pairs_hook=packet._unique_object)


@pytest.mark.parametrize("damaged", [None, [], {}, '{', '{"execution": null}'])
def test_malformed_saved_receipts_fail_closed(damaged):
    with pytest.raises(ValueError, match="identity"):
        packet.verify_packet(damaged)


@pytest.mark.parametrize("mutation", ["missing_required:scripts.a9_candidate_adapter",
    "missing_required:scripts.a9_local_harness", "extra_module", "duplicate_path", "swapped_names",
    "missing_hash", "export_sha256", "bootstrap_sha256", "source_binding"])
def test_worker_return_uses_same_receipt_validation(monkeypatch, mutation):
    original = packet._launch_worker
    def launch(request, abort):
        result = original(request, abort)
        assert result["result"]["cleanup_complete"]
        assert result["result"]["owned_workers_remaining"] == 0
        damage_receipt(result, mutation)
        result["receipt_sha256"] = packet._receipt_digest(result)
        return result
    monkeypatch.setattr(packet, "_launch_worker", launch)
    with pytest.raises(ValueError, match="identity"):
        packet.build_packet()
