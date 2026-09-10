import asyncio
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from characterization.watch_support import AsgiSession, SECRET
from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.discord_app import build_discord_runtime
from discordbot.composition.watch_app import build_watch_runtime
from discordbot.platform.errors import ConfigurationError, ExternalTemporaryError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.control_server import build_control_app
from discordbot.watch.adapters.discord_runtime import DiscordWatchResource
from discordbot.watch.adapters.server import build_servers
from discordbot.watch.adapters.web_runtime import WatchWebResource


@pytest.mark.parametrize("root,forbidden", [
    ("discord_app", ["discordbot.watch.application.service", "discordbot.watch.application.session", "discordbot.watch.adapters.writer", "discordbot.watch.adapters.web", "discordbot.watch.adapters.control_server"]),
    ("watch_app", ["discord", "discordbot.watch.application.discord_control", "discordbot.watch.adapters.discord_io", "discordbot.watch.adapters.control_client"]),
])
def test_composition_transitive_imports_are_process_specific(root, forbidden):
    source = str(Path(__file__).resolve().parents[3] / "src")
    script = f"import sys,importlib,json;sys.path.insert(0,{source!r});importlib.import_module('discordbot.composition.{root}');print(json.dumps(sorted(sys.modules)))"
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, check=True, timeout=10)
    modules = json.loads(result.stdout)
    assert not set(forbidden) & set(modules)


@pytest.mark.asyncio
async def test_watch_root_owns_database_readiness_apps_and_shutdown(tmp_path, service, clock):
    database = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic-process.db"))
    await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    resource = WatchWebResource(database, "https://watch.example.test", "synthetic-capability-secret-32-characters",
        SECRET, clock, service.telemetry, metadata=service.metadata)
    runtime = build_watch_runtime(PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, "synthetic"), watch=resource, clock=clock)
    assert not resource.service.ready()
    await runtime.start()
    try:
        assert resource.service.ready() and runtime.health.snapshot().ready
        public, control = build_servers(resource, 9000, 9001)
        assert public.config.app is resource.public_app and control.config.app is resource.control_app
        assert public.config.ws_max_size == 4096 and not public.config.access_log
        assert control.config.host == "127.0.0.1" and not control.config.proxy_headers
        with pytest.raises(ConfigurationError):
            build_servers(resource, 9000, 9001, "0.0.0.0")
    finally:
        report = await runtime.shutdown()
    assert not report.tasks.remaining and not report.resource_errors
    assert not resource.service.supervisor.snapshot().active


@pytest.mark.asyncio
async def test_discord_gateway_liveness_survives_watch_failure(service, clock):
    bot = MagicMock()
    bot.add_cog, bot.remove_cog = AsyncMock(), AsyncMock()
    transport = AsgiSession(build_control_app(service, SECRET))
    resource = DiscordWatchResource(bot, "https://watch.example.test", "http://127.0.0.1:9001", SECRET,
        2000, 42, clock, service.telemetry, transport)
    runtime = build_discord_runtime(PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, "synthetic"), watch=resource, clock=clock)
    await runtime.start()
    try:
        assert resource.controller.health.snapshot().ready
        service.health.stop_accepting()
        await resource.controller.refresh()
        assert not resource.controller.health.snapshot().ready
        assert runtime.health.snapshot().live and runtime.health.snapshot().ready
        assert resource.controller.supervisor is not service.supervisor
        assert not hasattr(resource, "service") and not hasattr(resource.controller, "sessions")
    finally:
        report = await runtime.shutdown()
        await transport.close()
    assert not report.tasks.remaining and not report.resource_errors


@pytest.mark.asyncio
async def test_startup_control_failure_is_optional_for_discord_process(service, clock):
    bot = MagicMock()
    bot.add_cog, bot.remove_cog = AsyncMock(), AsyncMock()
    resource = DiscordWatchResource(bot, "https://watch.example.test", "http://127.0.0.1:9001", SECRET,
        2000, 42, clock, service.telemetry, MagicMock())
    resource.client.call = AsyncMock(side_effect=ExternalTemporaryError("synthetic unavailable"))
    runtime = build_discord_runtime(PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, "synthetic"), watch=resource, clock=clock)
    await runtime.start()
    try:
        assert runtime.health.snapshot().live and runtime.health.snapshot().ready
        assert not resource.controller.health.snapshot().ready
    finally:
        await runtime.shutdown()
