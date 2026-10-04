"""Bounded local A9 preparation; closed synthetic/candidate adapters only.

This is a harness logic check, never staging acceptance or a capacity measurement.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Callable


KINDS = ("music", "watch", "command", "engagement")
FAULTS = ("none", "provider_timeout", "db_busy", "slow_peer", "unexpected")


class UnsafeTarget(ValueError):
    """Configuration failed before creating any output."""


class _CandidateBoundary(Exception):
    """Internal early abort; its fixed reason is retained without error text."""


@dataclass(frozen=True)
class Config:
    run_id: str
    target_identity: str
    temp_root: Path
    scope: str = "LOCAL_SYNTHETIC_ONLY"
    adapter: str = "fake"
    ticks: int = 4
    interval_seconds: float = 0.01
    multiplier: int = 1
    max_seconds: float = 2.0
    max_operations: int = 64
    max_output_bytes: int = 16384
    free_floor_bytes: int = 1048576
    fault: str = "none"
    fault_at: int = 0

    def validate(self) -> None:
        if (self.scope != "LOCAL_SYNTHETIC_ONLY" or self.adapter != "fake"
                or not isinstance(self.run_id, str) or not isinstance(self.temp_root, Path)
                or not re.fullmatch(r"[0-9a-f]{32}", self.run_id)
                or self.target_identity != "fake://a9/" + self.run_id):
            raise UnsafeTarget("Explicit local fake identity required")
        root = self.temp_root
        # Existing roots, relative paths, traversal, symlinks and Windows junctions
        # are refused. Cleanup never takes ownership of a pre-existing directory.
        if (not root.is_absolute() or ".." in root.parts or root.exists()
                or root.is_symlink() or root.is_junction()
                or root.name != "a9-campaign-" + self.run_id
                or root.parent != Path(tempfile.gettempdir()).resolve()
                or root.parent.resolve() != root.parent):
            raise UnsafeTarget("New direct child of canonical OS temporary root required")
        integers = ((self.ticks, 1, 32), (self.multiplier, 1, 2),
                    (self.max_operations, 1, 256), (self.max_output_bytes, 1, 65536),
                    (self.free_floor_bytes, 1048576, 2**40), (self.fault_at, 0, 255))
        if any(type(value) is not int or not low <= value <= high
               for value, low, high in integers):
            raise UnsafeTarget("Integer safety bound rejected")
        for value, low, high in ((self.interval_seconds, 0.001, 0.1),
                                 (self.max_seconds, 0.01, 5.0)):
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise UnsafeTarget("Finite time bound required")
        if self.fault not in FAULTS or self.fault_at >= self.ticks * 4 * self.multiplier:
            raise UnsafeTarget("Unknown or unreachable synthetic fault")


def config_from_mapping(value: dict) -> Config:
    """Strict shape: extra URLs, services, credential paths, etc. are not ignored."""
    try:
        result = Config(**{**value, "temp_root": Path(value["temp_root"])})
        result.validate()
        return result
    except (TypeError, KeyError) as error:
        raise UnsafeTarget("Explicit closed configuration required") from error


def _percentile(values: list[float], fraction: float) -> float | None:
    return sorted(values)[math.ceil(len(values) * fraction) - 1] if values else None


def run(config: Config, *, candidate: bool = False,
        abort_requested: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep) -> dict:
    """Run built-in fake labels or one fixed candidate packet; no live dispatch.

    Default mode has no DB/tasks. Candidate mode explicitly uses temporary SQLite
    and owned workers through the fixed adapter, with all external I/O fake.
    Bounds cover generated work and bytes, not OS CPU/RSS quotas. Returned evidence
    contains only allowlisted synthetic aggregates, never arbitrary error text.
    """
    config.validate()
    if type(candidate) is not bool:
        raise UnsafeTarget("Explicit boolean candidate selection required")
    adapter = None
    kinds = KINDS
    if candidate:
        # Closed, built-in local adapter only; never a provider URL or plugin.
        from scripts.a9_candidate_adapter import CandidateAdapter, STEPS
        if (not __debug__ or config.ticks != 1 or config.multiplier != 1 or config.fault != "none"
                or clock is not time.monotonic or sleep is not time.sleep):
            raise UnsafeTarget("Candidate packet requires one real-clock fixed scenario")
        kinds = STEPS
    root = config.temp_root
    root.mkdir(mode=0o700)  # exclusive; a concurrent creator cannot be adopted
    identity = root.stat()
    samples: list[dict] = []
    counts: Counter[str] = Counter()
    latencies: dict[str, list[float]] = {kind: [] for kind in kinds}
    scheduled = config.ticks * len(kinds) * config.multiplier
    written = 0
    status = "complete"
    reason = "none"
    cleaned = False
    started = 0.0
    ticks_seen: list[float] = []
    elapsed = 0.0
    primary_reason = "none"
    adapter_evidence: dict = {}

    def boundary() -> str | None:
        current = root.stat()
        if (root.is_symlink() or root.is_junction()
                or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)):
            return "target_changed"
        if abort_requested():
            return "operator_abort"
        if clock() - started >= config.max_seconds:
            return "time_budget"
        if shutil.disk_usage(root).free < config.free_floor_bytes:
            return "free_floor"
        return None

    try:
        started = clock()
        if candidate:
            reason = boundary() or "none"
            if reason != "none":
                raise _CandidateBoundary
            adapter = CandidateAdapter(root, started + config.max_seconds)
            adapter.start()
        with (root / "samples.jsonl").open("xb") as stream:
            for tick in range(config.ticks):
                wait = started + tick * config.interval_seconds - clock()
                if wait > 0:
                    sleep(min(wait, max(0.0, config.max_seconds - (clock() - started))))
                reason = boundary() or "none"
                if reason != "none":
                    break
                ticks_seen.append(clock() - started)
                for kind in kinds * config.multiplier:
                    reason = boundary() or "none"
                    if reason != "none":
                        break
                    if len(samples) >= config.max_operations:
                        reason = "operation_budget"
                        break
                    before = time.perf_counter() if candidate else clock()
                    # Reserve enough bytes before executing candidate work so a
                    # completed operation never disappears at the output boundary.
                    if candidate and written + 512 > config.max_output_bytes:
                        reason = "output_budget"
                        break
                    fault = config.fault if len(samples) == config.fault_at else "none"
                    # Deliberately no provider dispatch. These are model outcomes,
                    # not classifications of real SQLite/provider exceptions.
                    classification = ("ok" if fault == "none" else
                                      "unexpected_fault" if fault == "unexpected" else
                                      "expected_" + fault)
                    if adapter is not None:
                        classification = adapter.execute(kind)
                    latency = max(0.0, (time.perf_counter() if candidate else clock()) - before)
                    sample = {"index": len(samples), "tick": tick, "kind": kind,
                              "latency_seconds": latency, "classification": classification}
                    encoded = (json.dumps(sample, separators=(",", ":")) + "\n").encode()
                    if written + len(encoded) > config.max_output_bytes:
                        reason = "output_budget"
                        break
                    stream.write(encoded)
                    written += len(encoded)
                    samples.append(sample)
                    counts[classification] += 1
                    if classification == "ok":
                        latencies[kind].append(latency)
                    if classification == "unexpected_fault":
                        reason = "unexpected_fault"
                        break
                if reason != "none":
                    break
        elapsed = clock() - started
        if reason != "none":
            status = "aborted"
    except _CandidateBoundary:
        status = "aborted"
    except KeyboardInterrupt:
        status, reason = "aborted", "interrupted"
    except Exception:
        status, reason = "aborted", "harness_error"
    finally:
        primary_reason = reason
        elapsed = max(0.0, time.monotonic() - started) if clock is time.monotonic else elapsed
        # No recursive deletion: only our exact file and empty new directory.
        try:
            try:
                current = root.stat()
                same_root = (not root.is_symlink() and not root.is_junction()
                    and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino))
            except OSError:
                same_root = False
            # Drain workers even after replacement, but never flush service writes
            # through a changed path. Refuse file deletion in that case.
            if adapter is not None:
                try:
                    adapter_evidence = adapter.close(flush=same_root)
                finally:
                    adapter_evidence = adapter.evidence()
            if not same_root:
                raise UnsafeTarget("Cleanup ownership changed")
            if adapter is not None:
                adapter.remove_files()
            output = root / "samples.jsonl"
            if output.is_symlink() or output.is_junction():
                raise UnsafeTarget("Cleanup file replaced")
            output.unlink(missing_ok=True)
            root.rmdir()
            cleaned = True
        except OSError:
            status, reason = "aborted", "cleanup_failed"
        except UnsafeTarget:
            status, reason = "aborted", "cleanup_refused"
        except Exception:
            status, reason = "aborted", "cleanup_failed"

    if candidate:
        elapsed = max(0.0, clock() - started)

    gaps = [right - left for left, right in zip(ticks_seen, ticks_seen[1:])]
    return {
        "scope": "LOCAL_CANDIDATE_FAKE_EXTERNAL" if candidate else "SYNTHETIC_HARNESS_ONLY", "a9": "BLOCKED",
        "target_identity": config.target_identity, "status": status, "reason": reason,
        "planned_operations": scheduled, "recorded_operations": len(samples),
        "missing_operations": scheduled - len(samples),
        "planned_ticks": config.ticks, "observed_ticks": len(ticks_seen),
        "missing_ticks": config.ticks - len(ticks_seen),
        "max_tick_gap_seconds": max(gaps, default=None),
        "late_tick_gaps": sum(gap > config.interval_seconds * 1.5 for gap in gaps),
        "elapsed_seconds": elapsed, "output_bytes": written,
        "classifications": dict(counts), "cleanup_complete": cleaned,
        "owned_workers_remaining": 0,
        **({"samples": samples, "candidate": adapter_evidence,
            "primary_reason": primary_reason,
            "owned_workers_remaining": adapter_evidence.get("admitted_remaining", 0 if adapter is None else None)}
           if candidate else {}),
        "latency": {kind: {"successful_samples": len(values),
                           "p95_seconds": _percentile(values, .95),
                           "p99_seconds": _percentile(values, .99)}
                    for kind, values in latencies.items()},
    }
