"""Local integration prototype for the existing deployment adapters.

No production entrypoint, credential transport, shell, persistent access or host
exclusion mechanism is installed here. Existing host mechanisms cannot enforce
the reviewed WAL helper's exclusion contract; LiveExclusion always refuses.
The executable local fixture is tests/support/cutover_local_worker.py, backed by
tests/integration/operations/cutover_model.py and the adjacent regression tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable, Protocol

from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
from discordbot.operations.adapters.deployment import Services
from discordbot.operations.ports.deployment import Release

HELPER_SHA = "34fdbc6f1efca388f419c374e34852de30af3882fec4f392d66a8b6c10d5a640"
HELPER_PATH = Path(__file__).with_name("stopped_wal.py")
if digest(HELPER_PATH) != HELPER_SHA:
    raise RuntimeError("reviewed helper identity changed")
_spec = importlib.util.spec_from_file_location("reviewed_stopped_wal_controller", HELPER_PATH)
wal = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = wal
_spec.loader.exec_module(wal)

PAIR = ("discord-bot", "watch-web")
OTHER = ("supper", "my-moving", "cloudflared")
OPERATIONS = ("discordbot-backup", "discordbot-update", "discordbot-manual")
PROPERTIES = ("ActiveState", "Result", "MainPID", "InvocationID", "NRestarts")
MAX_LIFETIME = 10800.0
CLEANUP_RESERVE = 60.0
SAFE_REASONS = frozenset({"none", "invalid_sealed_plan", "canonical_wal_decision_missing",
    "live_isolation_and_transport_unavailable", "live_consumer_exclusion_unavailable", "unit_not_allowlisted",
    "observer_deadline", "invalid_service_observation", "observer_target_changed", "consumer_not_stopped",
    "partial_release_requires_separate_decision", "release_capacity_requires_separate_decision",
    "candidate_identity_or_review_changed", "receipt_size", "cancelled", "disconnected", "health_abort",
    "deadline", "protected_service_changed", "new_private_receipt_required", "normalization_target_changed",
    "normalization_not_verified", "invalid_supervisor_lifetime", "pointer_changed", "synthetic_gate",
    "ownership_release_unconfirmed",
    "unexpected_gate_error", "NormalizationFailed", "ConflictError", "PermissionError", "OSError",
    "DataIntegrityError", "ExternalTemporaryError", "Refused", "RuntimeError", "KeyboardInterrupt"})


class Blocked(RuntimeError):
    """Only fixed safe reason codes are exported."""
    def __init__(self, code: str) -> None:
        code = code if code in SAFE_REASONS else "unexpected_gate_error"
        super().__init__(code)
        self.code = code


class Step(StrEnum):
    ADMIT = "admit"
    INSTALL = "install"
    VERIFY = "installed_verify"
    RESTORE = "latest_restore"
    OLD = "old_compatibility"
    RETURN = "candidate_return"
    EXCLUDE = "exclude_consumers"
    STOP = "stop_pair"
    STOPPED = "verify_stopped"
    BACKUP = "final_backup"
    FINAL_RESTORE = "final_restore"
    NORMALIZE = "normalize"
    INTENT = "activation_intent"
    POINTER = "pointer"
    START = "start_pair"
    READY = "readiness"
    SMOKE = "smoke"


CAPS = dict(zip(Step, (60, 1050, 300, 150, 150, 150, 15, 90, 30, 180, 150, 30, 10, 10, 90, 60, 15)))


@dataclass(frozen=True)
class Plan:
    run_id: str
    candidate: str
    previous: str
    source_sha256: str
    manifest_sha256: str
    wheel_lock_sha256: str
    cutover: bool = False
    canonical_wal_approved: bool = False
    lifetime: float = 1800
    mode: str = "local_synthetic"

    def validate(self) -> None:
        if (not re.fullmatch(r"[a-z0-9-]{1,48}", self.run_id)
                or any(not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", x) for x in (self.candidate, self.previous))
                or self.candidate == self.previous
                or any(not re.fullmatch(r"[0-9a-f]{64}", x) for x in
                       (self.source_sha256, self.manifest_sha256, self.wheel_lock_sha256))
                or not math.isfinite(self.lifetime) or not 120 <= self.lifetime <= MAX_LIFETIME):
            raise Blocked("invalid_sealed_plan")
        if self.cutover and not self.canonical_wal_approved:
            raise Blocked("canonical_wal_decision_missing")
        if self.mode != "local_synthetic":
            raise Blocked("live_isolation_and_transport_unavailable")


@dataclass
class Signals:
    cancel: bool = False
    connected: bool = True
    healthy: bool = True


class Exclusion(Protocol):
    epoch: str
    def acquire(self) -> None: ...
    def check(self, target: Path, deadline: float) -> None: ...
    def handoff_pair(self) -> None: ...
    def retain_stopped(self) -> None: ...


class LiveExclusion:
    """A shared ops lock and systemd queries do NOT exclude unrelated DB opens.

    Never accept serialized observer claims or an externally supplied 'exclusive'
    boolean as a substitute. There is no production authority implementation.
    """
    epoch = "unavailable"
    def acquire(self) -> None:
        raise Blocked("live_consumer_exclusion_unavailable")
    def check(self, target: Path, deadline: float) -> None:
        raise Blocked("live_consumer_exclusion_unavailable")
    def handoff_pair(self) -> None:
        raise Blocked("live_consumer_exclusion_unavailable")
    def retain_stopped(self) -> None:
        raise Blocked("live_consumer_exclusion_unavailable")


class FixedHostReader:
    """Exact read-only systemd vectors; uses the existing bounded Runner API.

    It is tested with a fake runner here; no actual systemctl is invoked. It
    supplies observations only, and never manufactures an exclusion capability.
    """
    def __init__(self, runner, cwd: Path) -> None:
        self.runner, self.cwd = runner, cwd

    def service(self, unit: str, deadline: float) -> dict:
        if unit not in (*PAIR, *OTHER, *OPERATIONS):
            raise Blocked("unit_not_allowlisted")
        values = {}
        for prop in PROPERTIES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Blocked("observer_deadline")
            values[prop] = self.runner.read(
                ["systemctl", "show", unit, "--property=" + prop, "--value"], self.cwd, min(5, remaining))
        if (not values["MainPID"].isdigit() or len(values["MainPID"]) > 20
                or len(values["InvocationID"]) > 64):
            raise Blocked("invalid_service_observation")
        return values

    def protected(self, deadline: float) -> dict:
        return {unit: self.service(unit, deadline) for unit in OTHER}


class StoppedObserver:
    def __init__(self, reader: FixedHostReader, exclusion: Exclusion, target: Path, lock: Path) -> None:
        self.reader, self.exclusion, self.target, self.lock = reader, exclusion, target, lock

    def __call__(self, target: Path, deadline: float):
        if target != self.target:
            raise Blocked("observer_target_changed")
        self.exclusion.check(target, deadline)
        services = {}
        for unit in (*PAIR, *OPERATIONS):
            value = self.reader.service(unit, deadline)
            state = (value["ActiveState"], value["Result"], int(value["MainPID"]))
            if state != ("inactive", "success", 0):
                raise Blocked("consumer_not_stopped")
            if unit in PAIR:
                services[unit] = state
        self.exclusion.check(target, deadline)
        return wal.StopEvidence(target, self.lock, self.exclusion.epoch,
                                min(deadline, time.monotonic() + 1), True, services)


class FixedWorkers(Protocol):
    # These are fixed sealed-worker roles, NOT a command or source-text API.
    def admission(self, plan: Plan) -> dict: ...
    def install(self, release: Release) -> None: ...
    def native(self, release: Release) -> None: ...
    def latest_restore(self, release: Release) -> None: ...
    def old_compatibility(self, release: Release) -> None: ...
    def candidate_return(self, release: Release) -> None: ...
    def final_restore(self, release: Release): ...


class DeploymentBridge:
    """Reuse LocalDeployment methods; deliberately bypass Deployment.run.

    Never call activate (which repeats backup and changes pointer), discard,
    retain or automatic rollback. Old-code verification is on isolated copies.
    Existing installation worker must use its retaining store (no auto-deletion).
    """
    def __init__(self, local, workers: FixedWorkers) -> None:
        self.local, self.workers = local, workers

    def admit(self, plan: Plan) -> None:
        value = self.workers.admission(plan)
        if self.local.store.current() != plan.previous:
            raise Blocked("pointer_changed")
        if value.get("partial_present"):
            raise Blocked("partial_release_requires_separate_decision")
        if value.get("release_count", 16) >= 16 and value.get("installed_exact") is not True:
            raise Blocked("release_capacity_requires_separate_decision")
        if (value.get("candidate") != plan.candidate or value.get("previous") != plan.previous
                or value.get("source_sha256") != plan.source_sha256
                or value.get("manifest_sha256") != plan.manifest_sha256
                or value.get("wheel_lock_sha256") != plan.wheel_lock_sha256
                or value.get("reviewed_promotion_included") is not True):
            raise Blocked("candidate_identity_or_review_changed")

    def install(self, release: Release) -> None:
        self.workers.install(release)

    def verify(self, release: Release) -> None:
        self.local.preflight(release)
        self.local.test(release)
        self.workers.native(release)
        # Compatibility is exercised by existing isolated recovery workers,
        # never LocalDeployment.compatible's canonical-DB inspection here.
        self.local.publish(release)

    def intent(self, previous: str, candidate: str) -> None:
        atomic_json(self.local.settings.state / "activation.json", {"previous": previous, "target": candidate})

    def pointer(self, candidate: str) -> None:
        self.local.store.activate(candidate)


@dataclass
class Result:
    status: str = "RUNNING"
    stage: str = "admission"
    reason: str = "none"
    completed: list[str] = field(default_factory=list)
    pair: str = "untouched"
    database: str = "not_attempted"
    intent: str = "not_attempted"
    pointer: str = "not_attempted"
    observed_pointer: str = "unknown"
    protected: str = "unknown"
    cleanup: str = "not_needed"

    def payload(self) -> dict:
        return dict(vars(self))


class Controller:
    def __init__(self, plan: Plan, bridge: DeploymentBridge, reader: FixedHostReader,
                 exclusion: Exclusion, signals: Signals, receipt: Path,
                 *, clock: Callable[[], float] = time.monotonic) -> None:
        self.plan, self.bridge, self.reader, self.exclusion = plan, bridge, reader, exclusion
        self.signals, self.receipt, self.clock = signals, receipt, clock
        self.result = Result()
        self.started = clock()
        self.end = self.started + plan.lifetime
        self.work_end = self.end - CLEANUP_RESERVE
        self.stage_end = self.work_end
        self.owner = None
        self.receipt_admitted = False

    def save(self) -> None:
        if not self.receipt_admitted:
            raise Blocked("new_private_receipt_required")
        payload = self.result.payload()
        if len(json.dumps(payload).encode()) > 4096:
            raise Blocked("receipt_size")
        atomic_json(self.receipt, payload)

    def guard(self, *, stopped: bool = False) -> None:
        if self.signals.cancel:
            raise Blocked("cancelled")
        if not self.signals.connected:
            raise Blocked("disconnected")
        if not self.signals.healthy:
            raise Blocked("health_abort")
        if self.clock() >= min(self.work_end, self.stage_end):
            raise Blocked("deadline")
        if self.reader.protected(time.monotonic() + 5) != self.protected_before:
            raise Blocked("protected_service_changed")
        expected = self.plan.previous if self.result.pointer == "not_attempted" else self.plan.candidate
        if self.bridge.local.store.current() != expected:
            raise Blocked("pointer_changed")
        if stopped:
            self.owner.check(self.bridge.local.settings.database,
                             self.bridge.local.settings.operation_lock, time.monotonic() + 10)

    def step(self, stage: Step, action: Callable, *, stopped: bool = False,
             mutation: tuple[str, str] | None = None):
        self.stage_end = min(self.work_end, self.clock() + CAPS[stage])
        self.result.stage = stage.value
        self.guard(stopped=stopped)
        if mutation:
            setattr(self.result, *mutation)  # durable intent precedes possible mutation
        self.save()
        value = action()
        self.guard(stopped=stopped)
        self.result.completed.append(stage.value)
        self.save()
        return value

    def run(self) -> Result:
        p = self.bridge.local
        disturbed = False
        baseline_taken = False
        owner = None
        try:
            self.plan.validate()
            if (self.receipt.exists() or not self.receipt.is_absolute()
                    or self.receipt.resolve() != self.receipt
                    or self.receipt.parent != p.settings.database.parent
                    or self.receipt.name != "controller.json"):
                raise Blocked("new_private_receipt_required")
            self.receipt_admitted = True
            self.protected_before = self.reader.protected(time.monotonic() + 5)
            baseline_taken = True
            observe = StoppedObserver(self.reader, self.exclusion, p.settings.database, p.settings.operation_lock)
            owner = wal.OperationOwner(p.settings.operation_lock, observe)
            owner.__enter__()
            self.owner = owner
            release = Release(self.plan.candidate)
            self.step(Step.ADMIT, lambda: self.bridge.admit(self.plan))
            self.step(Step.INSTALL, lambda: self.bridge.install(release))
            self.step(Step.VERIFY, lambda: self.bridge.verify(release))
            for stage, action in ((Step.RESTORE, self.bridge.workers.latest_restore),
                                  (Step.OLD, self.bridge.workers.old_compatibility),
                                  (Step.RETURN, self.bridge.workers.candidate_return)):
                self.step(stage, lambda action=action: action(release))
            if not self.plan.cutover:
                self.result.status = "LOCAL_PRECUTOVER_PASS"
            else:
                self.step(Step.EXCLUDE, self.exclusion.acquire)
                def stop_pair():
                    nonlocal disturbed
                    disturbed = True
                    p.stop()
                self.step(Step.STOP, stop_pair, mutation=("pair", "stop_attempted"))
                self.step(Step.STOPPED, lambda: None, stopped=True)
                self.result.pair = "stopped"
                self.step(Step.BACKUP, lambda: p.backup(release), stopped=True)
                request = self.step(Step.FINAL_RESTORE, lambda: self.bridge.workers.final_restore(release), stopped=True)
                if request.database != p.settings.database or request.operation_lock != p.settings.operation_lock:
                    raise Blocked("normalization_target_changed")
                normalized = self.step(Step.NORMALIZE, lambda: wal.normalize(request, owner), stopped=True,
                                       mutation=("database", "may_have_changed"))
                if normalized.get("outcome") != "verified":
                    raise Blocked("normalization_not_verified")
                self.result.database = "verified_same_inode_wal"
                self.step(Step.INTENT, lambda: self.bridge.intent(self.plan.previous, self.plan.candidate),
                          stopped=True, mutation=("intent", "may_have_changed"))
                self.result.intent = "written"
                self.step(Step.POINTER, lambda: self.bridge.pointer(self.plan.candidate),
                          stopped=True, mutation=("pointer", "may_have_changed"))
                self.result.pointer = "switched"
                self.exclusion.handoff_pair()
                self.step(Step.START, p.start, mutation=("pair", "start_attempted"))
                self.step(Step.READY, lambda: p.ready(release))
                self.step(Step.SMOKE, lambda: p.smoke(release))
                self.result.pair = "running"
                self.result.status = "LOCAL_CUTOVER_PASS"
            self.guard()
            self.result.observed_pointer = p.store.current()
            self.result.protected = "unchanged"
            self.save()
        except BaseException as error:
            self.result.status = "BLOCKED"
            reason = error.code if isinstance(error, Blocked) else type(error).__name__
            self.result.reason = reason if reason in SAFE_REASONS else "unexpected_gate_error"
            # No automatic rollback, restore, retry or pointer operation. If the
            # pair was disturbed, only the approved pair is stopped again.
            if disturbed:
                self.result.cleanup = "stop_unconfirmed"
                try:
                    p.stop()
                    self.result.pair = "stopped"
                    self.exclusion.retain_stopped()
                    self.result.cleanup = "pair_stopped_exclusion_retained_model"
                except BaseException:
                    self.result.pair = "unknown"
            try:
                if baseline_taken:
                    self.result.observed_pointer = p.store.current()
                    if not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", self.result.observed_pointer):
                        self.result.observed_pointer = "unknown"
                    self.result.protected = ("unchanged" if self.reader.protected(time.monotonic()+5)
                                             == self.protected_before else "changed")
            except BaseException:
                self.result.observed_pointer = "unknown"
            try:
                if self.receipt_admitted:
                    self.save()
            except BaseException:
                self.result.status = "UNCERTAIN_RECEIPT"
            if not isinstance(error, Exception):
                raise
        finally:
            if owner is not None and owner.held:
                try:
                    owner.__exit__(None, None, None)
                except BaseException:
                    self.result.status = "BLOCKED"
                    self.result.reason = "ownership_release_unconfirmed"
                    try:
                        self.save()
                    except BaseException:
                        self.result.status = "UNCERTAIN_RECEIPT"
        return self.result


class OwnedProcess:
    """An actual Popen capability, never a PID/name read from an artifact.

    This local prototype owns one non-spawning test worker. A real Linux worker
    tree requires the existing exact-unit/cgroup mechanism, not this PID wrapper.
    """
    def __init__(self, handle: subprocess.Popen) -> None:
        self.handle = handle

    def terminate_and_reap(self) -> None:
        if self.handle.poll() is None:
            self.handle.terminate()
        try:
            self.handle.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.handle.kill()
            self.handle.wait(timeout=1)


def supervise_owned(child: OwnedProcess, receipt: Path, signals: Signals,
                    *, timeout: float, poll_seconds: float = 0.05) -> dict:
    """Bounded capture on EVERY exit, including health/transport abort.

    No stdout/stderr forwarding, no incoming command frames, no retries. Future
    live supervision remains blocked on remote disconnect/cgroup enforcement.
    """
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_LIFETIME - 2:
        # The caller has already supplied an owned process. Invalid admission
        # must not orphan it while refusing the requested lifetime.
        child.terminate_and_reap()
        raise Blocked("invalid_supervisor_lifetime")
    end = time.monotonic() + timeout
    reason = "completed"
    cleanup = "unknown"
    captured = None
    final_receipt_valid = False
    try:
        while child.handle.poll() is None:
            if signals.cancel:
                reason = "cancelled"
                break
            if not signals.connected:
                reason = "disconnected"
                break
            if not signals.healthy:
                reason = "health_abort"
                break
            if time.monotonic() >= end:
                reason = "deadline"
                break
            time.sleep(min(poll_seconds, max(0, end-time.monotonic())))
    except BaseException:
        reason = "supervisor_interrupted"
    finally:
        # Collect while alive first, then after reaping. Earlier controllers lost
        # the worker outcome on a health abort before reaching result collection.
        for after_stop in (False, True):
            if after_stop:
                try:
                    child.terminate_and_reap()
                    cleanup = "owned_process_reaped"
                except BaseException:
                    cleanup = "owned_process_unconfirmed"
            try:
                value = read_json(receipt, 4096)
                if set(value) != set(Result().payload()):
                    raise ValueError("receipt schema")
                if value["stage"] not in {"admission", *(s.value for s in Step)}:
                    raise ValueError("receipt stage")
                if (value["status"] not in {"RUNNING", "BLOCKED", "UNCERTAIN_RECEIPT", "LOCAL_PRECUTOVER_PASS", "LOCAL_CUTOVER_PASS"}
                        or value["reason"] not in SAFE_REASONS
                        or not isinstance(value["completed"], list) or len(value["completed"]) > len(Step)
                        or any(x not in set(Step) for x in value["completed"])
                        or value["pair"] not in {"untouched", "stop_attempted", "stopped", "start_attempted", "running", "unknown"}
                        or value["database"] not in {"not_attempted", "may_have_changed", "verified_same_inode_wal"}
                        or value["intent"] not in {"not_attempted", "may_have_changed", "written"}
                        or value["pointer"] not in {"not_attempted", "may_have_changed", "switched"}
                        or value["protected"] not in {"unknown", "unchanged", "changed"}
                        or value["cleanup"] not in {"not_needed", "stop_unconfirmed", "pair_stopped_exclusion_retained_model"}
                        or (value["observed_pointer"] != "unknown" and not re.fullmatch(
                            r"r-[0-9a-f]{16}-[0-9a-f]{16}", value["observed_pointer"]))):
                    raise ValueError("receipt values")
                captured = value
                if after_stop:
                    final_receipt_valid = True
            except BaseException:
                pass  # Missing/partial receipts explicitly yield UNCERTAIN below.
    passed = (reason == "completed" and child.handle.returncode == 0 and cleanup == "owned_process_reaped"
              and final_receipt_valid and captured is not None
              and captured["status"] in {"LOCAL_PRECUTOVER_PASS", "LOCAL_CUTOVER_PASS"})
    return {"status": "LOCAL_PASS" if passed else "BLOCKED_OR_UNCERTAIN", "reason": reason,
            "returncode": child.handle.returncode, "cleanup": cleanup, "worker": captured,
            "final_receipt_valid": final_receipt_valid,
            "host_isolation_proven": False}
