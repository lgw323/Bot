import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.runtime import ProcessRuntime
from discordbot.operations.adapters.hosting import Servers, TelemetryDrain
from discordbot.operations.adapters.probe import Probe
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.platform.tasks import TaskResult, TaskSpec

from .test_production_tools import tool


@pytest.mark.asyncio
async def test_periodic_success_keeps_metrics_and_history_without_journal_churn():
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, "synthetic"))
    await runtime.start()
    runtime.telemetry_buffer.drain()
    # Drive the real three scheduler specifications without waiting on clocks/network.
    specs = []
    supervisor = SimpleNamespace(start=lambda spec, factory: specs.append(spec) or asyncio.get_running_loop().create_future())
    fixture = SimpleNamespace(supervisor=supervisor)
    Servers((), supervisor).schedule()
    TelemetryDrain(fixture).schedule()
    Probe(None, fixture).schedule()
    try:
        for spec in specs:
            for _ in range(100):
                task = runtime.supervisor.start(spec, lambda: asyncio.sleep(0))
                await task
                await asyncio.sleep(0)
        assert not runtime.telemetry_buffer.drain()
        counts = runtime.metrics.snapshot()
        assert sum(value for (name, labels), value in counts.items() if name == "task_result_total") == 600
        assert runtime.supervisor.snapshot().observations[-1].result is TaskResult.SUCCEEDED
        async def fail():
            raise DatabaseUnavailableError("synthetic private detail")
        for spec in specs:
            with pytest.raises(DatabaseUnavailableError):
                await runtime.supervisor.start(spec, fail)
            await asyncio.sleep(0)
        events = runtime.telemetry_buffer.drain()
        assert len(events) == 3 and all(item.event == "task.failed" for item in events)
        assert "synthetic private detail" not in json.dumps([item.as_dict() for item in events])
        await runtime.supervisor.start(TaskSpec("user-work", "test", "work", "test", 5), lambda: asyncio.sleep(0))
        await asyncio.sleep(0)
        assert [item.event for item in runtime.telemetry_buffer.drain()] == ["task.started", "task.succeeded"]
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_generic_probe_failure_emits_safe_code_and_latches_readiness(monkeypatch):
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, "synthetic"))
    database = SimpleNamespace(probe=AsyncMock(side_effect=DatabaseUnavailableError("private DB path", context={"path": "private"})))
    factories = []
    runtime.supervisor = SimpleNamespace(start=lambda spec, factory: factories.append(factory) or asyncio.get_running_loop().create_future())
    probe = Probe(database, runtime)
    probe.schedule()
    monkeypatch.setattr("discordbot.operations.adapters.probe.asyncio.sleep", AsyncMock())
    try:
        await factories[0]()
        assert not probe.ready()
        events = runtime.telemetry_buffer.drain()
        assert len(events) == 1 and events[0].event == "database.probe_failed"
        assert events[0].fields == {"error_code": "database_unavailable", "operation": "select1_probe", "probe_disposition": "hard"}
        database.probe.side_effect = None
        await factories[0]()
        assert not probe.ready()  # A safety failure remains latched; no automatic recovery.
        assert not runtime.telemetry_buffer.drain()
    finally:
        await runtime.executor.close(grace_seconds=1)


def test_journal_diagnostic_only_releases_allowlisted_labels():
    diagnostic = tool("staging/inspect_journal_counts.py")
    assert diagnostic.event_category(json.dumps({"event": "task.succeeded", "task_name": "telemetry-drain", "secret": "private"})) == "task.succeeded:telemetry-drain"
    for value in (None, [], "private", "null", '["private"]', '{"event":["private"]}'):
        assert diagnostic.event_category(value) == "other"
    assert diagnostic.event_category('{"event":"task.failed","task_name":"private"}') == "task.failed:other"
