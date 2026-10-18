"""A8-M4: synthetic synchronous driver for real Probe factories and callbacks.

Adapted from the retained discovery reproducer: repository-relative paths, isolated
historical policy loading, a healthy control, and explicit contract RED assertions.
No event loop, sockets, SQLite files, services, real backup metadata or credentials.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from discordbot.operations.adapters import probe as current
from discordbot.platform.errors import DatabaseUnavailableError

ROOT = Path(__file__).resolve().parents[3]
HISTORICAL = "8e9018d4b8061cde6006eee47fa4103522f77718"
PROBE_PATH = "src/discordbot/operations/adapters/probe.py"
POLICY_PATH = "src/discordbot/operations/adapters/probe_policy.py"
BUSY = dict(operation="select1_probe", stage="probe_configure",
            exception_family="sqlite_operational", sqlite_errorcode=5,
            sqlite_family="busy", connection_opened=True,
            close_succeeded=True, cleanup_failed=False)


def load_module(version: str) -> ModuleType:
    if version == "current":
        return current
    policy = ModuleType("a8t1_historical_policy")
    module = ModuleType("a8t1_historical_probe")
    for target, path in ((policy, POLICY_PATH), (module, PROBE_PATH)):
        source = subprocess.check_output(["git", "show", f"{HISTORICAL}:{path}"], cwd=ROOT)
        exec(compile(source, f"{HISTORICAL}:{path}", "exec"), target.__dict__)
    module.ProbePolicy = policy.ProbePolicy
    return module


class ImmediateFuture:
    """Only the Future interface used by Probe; dispatch callbacks synchronously."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[ImmediateFuture], None]] = []
        self.finished = False
        self.is_cancelled = False

    def add_done_callback(self, callback: Callable[[ImmediateFuture], None]) -> None:
        self.callbacks.append(callback)

    def set_result(self, value: object) -> None:
        self.finished = True
        for callback in self.callbacks:
            callback(self)

    def done(self) -> bool:
        return self.finished

    def cancelled(self) -> bool:
        return self.is_cancelled

    def exception(self) -> None:
        return None

    def cancel(self) -> None:
        if not self.finished:
            self.is_cancelled = True
            self.set_result(None)


async def immediate_gather(*args: Any, **kwargs: Any) -> list[object]:
    assert all(future.done() for future in args)
    return []


def complete(coroutine: Coroutine[Any, Any, Any]) -> Any:
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("unexpected blocking await in synthetic driver")


async def exercise(module: ModuleType, *, terminal: bool) -> dict[str, Any]:
    now = [0.0]
    pending: list[tuple[Callable[..., Any], ImmediateFuture]] = []
    futures: list[ImmediateFuture] = []
    events: list[str] = []
    samples: list[dict[str, Any]] = []
    counters = {"scheduled": 0, "stats": 0}
    metadata = [99900.0]

    def start(spec: object, factory: Callable[..., Any]) -> ImmediateFuture:
        future = ImmediateFuture()
        pending.append((factory, future))
        futures.append(future)
        counters["scheduled"] += 1
        return future

    def stat() -> SimpleNamespace:
        counters["stats"] += 1
        return SimpleNamespace(st_mtime=metadata[0])

    async def run(work: Callable[[], Any]) -> Any:
        return work()

    runtime = SimpleNamespace(
        clock=SimpleNamespace(monotonic=lambda: now[0], now=lambda: datetime.fromtimestamp(100000 + now[0], timezone.utc)),
        metrics=SimpleNamespace(increment=lambda *a, **k: None, dropped_series=0),
        telemetry=SimpleNamespace(emit=lambda event, **kw: events.append(event)),
        telemetry_buffer=SimpleNamespace(dropped_count=0), executor=SimpleNamespace(run=run),
        supervisor=SimpleNamespace(start=start, capacity=10, snapshot=lambda: SimpleNamespace(active=[])))
    database = SimpleNamespace(probe=AsyncMock(), observations=[], admitted=(0, 0))
    probe = module.Probe(database, runtime, SimpleNamespace(stat=stat))
    old_asyncio = module.asyncio
    module.asyncio = SimpleNamespace(sleep=AsyncMock(), gather=immediate_gather)

    async def sample(at: float, busy: bool = False) -> None:
        now[0] = at
        database.probe.side_effect = DatabaseUnavailableError("synthetic", context=BUSY) if busy else None
        factory, future = pending.pop(0)
        await factory()
        future.set_result(None)  # Executes the real production scheduling callback.
        samples.append(dict(t=at, ready=probe.ready(), hard=probe.policy.hard,
                            calls=database.probe.await_count, scheduled=counters["scheduled"]))

    try:
        probe.database_ready = True
        probe.schedule()
        for at, busy in ((5, True), (10, False), (15, False), (20, terminal)):
            await sample(at, busy)
        before = probe.gauges()
        now[0] += 7 * 3600
        database.probe.side_effect = None
        if terminal:
            probe.schedule()  # Healthy driver availability cannot bypass the latch.
        else:
            await sample(now[0])  # One pending healthy probe samples the advanced clock.
        after = probe.gauges()
        actual_age = 100000 + now[0] - metadata[0]
        calls_after_elapsed = database.probe.await_count
        metadata[0] = 100000 + now[0]  # Simulated new backup metadata.
        if not terminal:
            await sample(now[0] + 5)
        after_publication = probe.gauges()
        result = dict(samples=samples, events=events, before_age=before["backup_age_seconds"],
                      actual_age=actual_age, reported_age=after["backup_age_seconds"],
                      rpo_exceeded=after["backup_rpo_exceeded"],
                      after_publication_age=after_publication["backup_age_seconds"],
                      calls_after_elapsed=calls_after_elapsed, stat_calls=counters["stats"],
                      hard=probe.policy.hard, ready=probe.ready(), pending_before_stop=len(pending))
        await probe.stop()
        pending.clear()  # Discard only the synthetic cancelled factory handle.
        assert all(future.done() for future in futures)
        result["all_futures_done"] = True
        return result
    finally:
        await probe.stop()
        module.asyncio = old_asyncio


@pytest.mark.parametrize("version", ["historical", "current"])
def test_intended_latch_and_healthy_metric_negative_control(version: str) -> None:
    module = load_module(version)
    latched = complete(exercise(module, terminal=True))
    healthy = complete(exercise(module, terminal=False))
    assert latched["events"] == ["database.probe_contention", "database.probe_recovered", "database.probe_failed"]
    assert latched["hard"] and not latched["ready"]
    assert latched["calls_after_elapsed"] == 4 and latched["pending_before_stop"] == 0
    assert healthy["reported_age"] == healthy["actual_age"] == 25320
    assert healthy["rpo_exceeded"] == 1 and healthy["after_publication_age"] == 5
    assert not healthy["hard"] and healthy["ready"]


@pytest.mark.parametrize("version", ["historical", "current"])
def test_backup_freshness_must_not_remain_false_healthy_after_latch(version: str) -> None:
    result = complete(exercise(load_module(version), terminal=True))
    assert result["actual_age"] == 25320
    # Current-age reporting or explicit unknown is acceptable; a stale safe value is not.
    assert result["rpo_exceeded"] == 1 and (
        result["reported_age"] < 0 or result["reported_age"] == result["actual_age"]
    ), f"actual_age={result['actual_age']}, reported_age={result['reported_age']}, rpo_exceeded={result['rpo_exceeded']}"
