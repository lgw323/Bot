import json
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet

from discordbot.composition.config import PlatformConfig, Environment, ServiceKind
from discordbot.composition.runtime import ProcessRuntime
from discordbot.operations.adapters.configuration import load_settings, private_mode
from discordbot.operations.adapters.deployment import Services
from discordbot.operations.adapters.hosting import Servers, health_app
from discordbot.operations.application.manual import ManualOperations
from discordbot.operations.adapters.manual import RequestInbox
from discordbot.operations.adapters.audit import Audit
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.errors import ConfigurationError, ExternalTemporaryError

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def config_files(tmp_path):
    config = json.loads((ROOT / "deploy" / "config.example.json").read_text())
    config["paths"] = {key: str(tmp_path / key) for key in config["paths"]}
    file = tmp_path / "config.json"
    file.write_text(json.dumps(config))
    for name, value in {"discord_token": "fake-token", "gemini_key": "fake-gemini", "db_key": Fernet.generate_key().decode(),
                        "control_key": "c" * 32, "capability_key": "k" * 32}.items():
        path = tmp_path / name
        path.write_text(value)
        path.chmod(0o600)
    return file, tmp_path


def test_secret_is_not_in_repr_and_service_credentials_are_separate(config_files):
    file, credentials = config_files
    settings = load_settings(file, credentials, "discord-bot")
    assert "fake-token" not in repr(settings) + repr(settings.secrets)
    assert settings.secrets.db_key == b"" and settings.secrets.capability_key == ""
    (credentials / "discord_token").unlink()
    assert load_settings(file, credentials, "watch-web").secrets.capability_key
    with pytest.raises(ConfigurationError): load_settings(file, credentials, "discord-bot")


@pytest.mark.parametrize("mode,owner", [(stat.S_IFREG | 0o644, 1), (stat.S_IFREG | 0o600, 999), (stat.S_IFDIR | 0o700, 1)])
def test_secret_permissions_are_fail_closed(mode, owner):
    with pytest.raises(ConfigurationError): private_mode(mode, owner, 1)


def test_missing_secret_fails_before_assembly_or_login(config_files, monkeypatch):
    from discordbot.composition.main import main
    file, credentials = config_files
    (credentials / "discord_token").unlink()
    monkeypatch.setattr("discordbot.composition.production_discord.assemble", lambda *a: pytest.fail("login/assembly"))
    assert main(["discord-bot", "--config", str(file), "--credentials", str(credentials), "--release", str(credentials)]) == 1


@pytest.mark.asyncio
async def test_health_gate_uses_platform_and_actual_feature_readiness():
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, "release1"))
    feature_ready = False
    app = health_app(runtime, lambda: feature_ready, lambda: {"queue_depth": 0})
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            assert (await client.get("/health/ready")).status_code == 503
            feature_ready = True
            ready = await client.get("/health/ready")
            assert ready.status_code == 200 and ready.json()["release"] == "release1"
            assert "queue_depth 0.0" in (await client.get("/metrics")).text
            runtime.health.stop_accepting()
            assert (await client.get("/health/ready")).status_code == 503
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("broken", ["discord-bot", "watch-web", "split_version"])
def test_pair_readiness_rejects_one_failed_or_split_version(tmp_path, broken):
    services = Services(None, tmp_path, (9010, 9011))
    def probe(index, path):
        service = services.names[index]
        return {"ready": service != broken, "service": service,
                "release": "wrong" if broken == "split_version" and index == 1 else "expected"}
    services.probe = probe
    with pytest.raises(ExternalTemporaryError): services.ready("expected", timeout=0)


@pytest.mark.asyncio
async def test_server_lifecycle_owns_both_startup_and_shutdown_without_serving_network():
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, "release"))
    fake = SimpleNamespace(config=SimpleNamespace(loaded=True, lifespan_class=lambda config: object()),
        startup=AsyncMock(), shutdown=AsyncMock(), on_tick=AsyncMock(return_value=False), started=True, should_exit=False)
    listeners = Servers((fake,), runtime.supervisor)
    await runtime.start()
    await listeners.start()
    assert listeners.ready()
    await listeners.stop()
    fake.shutdown.assert_awaited_once()
    await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("user,result", [(1,"accepted"),(1,"already_running"),(1,"failed"),(2,"accepted")])
async def test_manual_authorization_and_exactly_one_ephemeral_response(user, result):
    port = SimpleNamespace(accept=AsyncMock(return_value=result))
    responder = SimpleNamespace(reply=AsyncMock())
    await ManualOperations(1, port).request(user, "update", "receipt", responder)
    responder.reply.assert_awaited_once()
    assert responder.reply.call_args.kwargs == {"ephemeral": True}
    assert port.accept.await_count == int(user == 1)


@pytest.mark.asyncio
async def test_manual_timer_race_accepts_one_durable_request(tmp_path):
    import asyncio
    executor = BoundedExecutor(workers=2, queue_capacity=2, name="manual-test")
    audit_path = tmp_path / "audit"
    audit_path.mkdir()
    inbox = RequestInbox(tmp_path, tmp_path / "lock", executor, Audit(audit_path), "release")
    try:
        results = await asyncio.gather(inbox.accept("update", "same"), inbox.accept("update", "same"))
        assert sorted(results) == ["accepted", "already_running"]
        assert len(list(audit_path.iterdir())) == 1
        assert await inbox.accept("restart", "different") == "already_running"
    finally:
        await executor.close(grace_seconds=5)


@pytest.mark.asyncio
async def test_manual_completed_receipt_cannot_replay_after_another_operation(tmp_path):
    from discordbot.operations.adapters.filesystem import read_json, atomic_json
    executor = BoundedExecutor(workers=1, queue_capacity=1, name="manual-test")
    (tmp_path / "audit").mkdir()
    inbox = RequestInbox(tmp_path, tmp_path / "lock", executor, Audit(tmp_path / "audit"), "release")
    try:
        for receipt in ("one", "two"):
            assert await inbox.accept("restart", receipt) == "accepted"
            path = tmp_path / "manual-request.json"
            value = read_json(path)
            value["result"] = "ok"
            atomic_json(path, value)
        assert await inbox.accept("restart", "one") == "already_running"
    finally:
        await executor.close(grace_seconds=5)


@pytest.mark.parametrize("state,result", [("active","success"),("failed","timeout"),("inactive","exit-code")])
def test_stop_requires_clean_checkpoint_exit(tmp_path, state, result):
    runner = SimpleNamespace(run=lambda *args: None,
        read=lambda args, *rest: state if "--property=ActiveState" in args else result)
    with pytest.raises(ExternalTemporaryError): Services(runner, tmp_path, (9010, 9011)).stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("service", [ServiceKind.DISCORD_BOT, ServiceKind.WATCH_WEB])
async def test_entrypoint_signal_drains_checkpoint_and_restores_handlers(monkeypatch, service):
    import asyncio
    import signal
    from discordbot.composition.main import run_process

    config = PlatformConfig(service, Environment.TEST, "release")
    runtime = ProcessRuntime(config=config)
    handlers, calls = {}, []
    original = object()
    def register(sig, handler):
        previous = handlers.get(sig, original)
        handlers[sig] = handler
        return previous
    monkeypatch.setattr(signal, "signal", register)
    closed = asyncio.Event()
    async def checkpoint():
        calls.append("checkpoint")
    async def close():
        calls.append("gateway-close")
        closed.set()
    async def connect(**kwargs):
        await closed.wait()
    async def listener_start():
        handlers[signal.SIGTERM](signal.SIGTERM, None)
    listeners = SimpleNamespace(start=listener_start, stop=AsyncMock())
    probe = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    telemetry = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), flush=lambda: calls.append("flush"))
    feature = SimpleNamespace(bot=SimpleNamespace(connect=connect, close=close),
                              deferred=SimpleNamespace(stop=checkpoint))
    module = "production_discord" if service is ServiceKind.DISCORD_BOT else "production_watch"
    monkeypatch.setattr(f"discordbot.composition.{module}.assemble",
                        lambda *args: (runtime, feature, listeners, telemetry, probe))
    async with asyncio.timeout(5):
        await run_process(config, None)
    listeners.stop.assert_awaited_once()
    probe.stop.assert_awaited_once()
    telemetry.stop.assert_awaited_once()
    assert calls == (["checkpoint", "gateway-close", "flush"] if service is ServiceKind.DISCORD_BOT else ["flush"])
    assert all(value is original for value in handlers.values())
