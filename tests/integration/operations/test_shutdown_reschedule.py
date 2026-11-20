"""Real scheduler completion races, with no sockets, credentials or systemd."""

import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.composition import worker
from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.guardian import WorkerControl
from discordbot.composition.runtime import ProcessRuntime, require_clean_shutdown
from discordbot.operations.adapters import hosting, probe as probe_module
from discordbot.platform.termination import TerminationPolicy


class Channel:
    def __init__(self):
        self.packets = []

    def send(self, packet):
        self.packets.append(packet)

    def fileno(self):
        return 77  # Reader registration is modeled, never touches this FD.


@pytest.fixture
def managed(monkeypatch):
    loop = asyncio.SelectorEventLoop()
    monkeypatch.setattr(worker.asyncio, "new_event_loop", lambda: loop)
    monkeypatch.setattr(loop, "add_reader", lambda *args: None)
    monkeypatch.setattr(loop, "remove_reader", lambda *args: None)
    errors = []
    install = loop.set_exception_handler

    def capture(handler):
        def observed(current, context):
            errors.append(type(context.get("exception")).__name__)
            handler(current, context)
        install(observed)

    monkeypatch.setattr(loop, "set_exception_handler", capture)
    handlers = {}

    def register(sig, handler):
        previous = handlers.get(sig, object())
        handlers[sig] = handler
        return previous

    monkeypatch.setattr(worker.signal, "signal", register)
    control = WorkerControl(Channel(), TerminationPolicy(1, .2, 1))
    return control, handlers, errors


@pytest.mark.parametrize("kind", ["listeners", "probe", "telemetry"])
@pytest.mark.parametrize("service", [ServiceKind.DISCORD_BOT, ServiceKind.WATCH_WEB])
@pytest.mark.parametrize("queued_before_close", [False, True])
def test_completed_periodic_work_does_not_fail_worker_after_admission_closes(
    managed, monkeypatch, kind, service, queued_before_close,
):
    control, _, errors = managed

    async def application(channel):
        runtime = ProcessRuntime(config=PlatformConfig(service, Environment.TEST, "synthetic"))
        await runtime.start()
        gate, waiting = asyncio.Event(), asyncio.Event()

        async def pause(_):
            waiting.set()
            await gate.wait()

        # Only scheduler sleeps are modeled. The worker/runtime keep real asyncio.
        if kind == "listeners":
            monkeypatch.setattr(hosting, "asyncio", SimpleNamespace(sleep=pause, gather=asyncio.gather))
            server = SimpleNamespace(on_tick=AsyncMock(return_value=False), should_exit=False, shutdown=AsyncMock())
            component = hosting.Servers((server,), runtime.supervisor)
            component.started.append(server)
        elif kind == "telemetry":
            monkeypatch.setattr(hosting, "asyncio", SimpleNamespace(sleep=pause, gather=asyncio.gather))
            component = hosting.TelemetryDrain(runtime)
        else:
            monkeypatch.setattr(probe_module, "asyncio", SimpleNamespace(sleep=pause, gather=asyncio.gather))
            database = SimpleNamespace(probe=AsyncMock())
            component = probe_module.Probe(database, runtime)
        component.schedule()
        current = component.tick if kind == "listeners" else component.task
        await waiting.wait()
        if queued_before_close:
            gate.set()
            await asyncio.sleep(0)
            assert current.done()  # Its done callbacks are queued behind us.
        # Same admission boundary as run_process.stop -> begin_shutdown.
        runtime.begin_shutdown()
        gate.set()
        await current
        await asyncio.sleep(0)  # Actual successful-task done callback must run.
        await component.stop()
        require_clean_shutdown(await runtime.shutdown())

    result = worker.run_managed(application, control)
    assert (result, errors) == (0, [])
    assert b"F" not in control.channel.packets
    assert control.channel.packets[-1] == b"C"


@pytest.mark.parametrize("mode,expected", [
    ("requested", 0), ("repeated", 0), ("self_cancel", 1),
    ("already_cancelled", 1), ("epoch_only", 1), ("cleanup_error", 1),
    ("loop_error", 1), ("deadline", 1),
])
def test_worker_distinguishes_requested_cancel_from_failure(managed, mode, expected):
    control, handlers, errors = managed
    cleaned = []

    async def application(channel):
        loop = asyncio.get_running_loop()
        if mode == "loop_error":
            loop.call_exception_handler({"exception": RuntimeError("SYNTHETIC_PRIVATE_CANARY")})
            return
        if mode == "epoch_only":
            channel.stopping()
            raise asyncio.CancelledError
        if mode == "self_cancel":
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
        if mode == "already_cancelled":
            asyncio.current_task().cancel()
        if mode == "deadline":
            channel.stopping(loop.time() - channel.policy.grace)
        else:
            handlers[signal.SIGTERM](signal.SIGTERM, None)
            if mode == "repeated":
                handlers[signal.SIGTERM](signal.SIGTERM, None)
        try:
            await asyncio.Future()
        finally:
            if mode in ("requested", "repeated"):
                await asyncio.sleep(.001)
                cleaned.append("async-finally-complete")
            if mode == "cleanup_error":
                raise RuntimeError("SYNTHETIC_PRIVATE_CANARY")

    assert worker.run_managed(application, control) == expected
    assert (b"C" in control.channel.packets) == (expected == 0)
    assert (b"F" in control.channel.packets) == (expected == 1)
    assert errors == (["RuntimeError"] if mode == "loop_error" else [])
    if mode == "deadline":
        assert b"A" in control.channel.packets
    if expected == 0:
        assert cleaned == ["async-finally-complete"]


def test_expected_cancel_does_not_hide_async_generator_finalizer_failure(managed):
    control, handlers, errors = managed
    retained = []

    async def application(channel):
        async def generator():
            try:
                yield 1
            finally:
                await asyncio.sleep(0)
                raise RuntimeError("SYNTHETIC_PRIVATE_CANARY")

        owned = generator()
        retained.append(owned)
        await anext(owned)
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        await asyncio.Future()

    assert worker.run_managed(application, control) == 1
    assert errors == ["RuntimeError"]
    assert b"F" in control.channel.packets and b"C" not in control.channel.packets
    assert retained[0].ag_frame is None
