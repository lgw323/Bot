"""Synthetic full V2 Discord -> signed HTTP -> watch-web -> temporary SQLite path."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx

from discordbot.platform.clock import Uuid4Generator
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.control_client import LoopbackClient
from discordbot.watch.adapters.control_server import build_control_app
from discordbot.watch.adapters.discord_io import DiscordAdminMessages, DiscordInteraction
from discordbot.watch.adapters.security import Capabilities
from discordbot.watch.adapters.writer import SqliteWatchWriter
from discordbot.watch.application.discord_control import DiscordWatch
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import WatchLimits

SECRET = "synthetic-loopback-secret-32-characters"


class AsgiSession:
    def __init__(self, app):
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)), base_url="http://127.0.0.1:9001")

    @asynccontextmanager
    async def post(self, url, data, headers, allow_redirects):
        response = await self.http.post(url, content=data, headers=headers)
        async def chunks(size):
            for index in range(0, len(response.content), size):
                yield response.content[index:index+size]
        yield SimpleNamespace(status=response.status_code, content=SimpleNamespace(iter_chunked=chunks))

    async def close(self):
        await self.http.aclose()


def interaction(clock, identity=1001):
    request = MagicMock()
    request.id, request.guild_id = identity, 100
    request.created_at = clock.now()
    request.user.id, request.user.mention = 42, "<@42>"
    request.response.is_done.return_value = False
    request.response.defer = AsyncMock()
    request.response.send_message = AsyncMock()
    request.followup.send = AsyncMock()
    request.edit_original_response = AsyncMock(return_value=SimpleNamespace(id=500, channel=SimpleNamespace(id=1000)))
    request.delete_original_response = AsyncMock()
    return request


@asynccontextmanager
async def harness(path):
    clock = SimpleNamespace(now=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc), monotonic=lambda: 1000.0)
    buffer = TelemetryBuffer(128)
    telemetry = TelemetryEmitter(buffer=buffer, clock=clock, service="test", environment="test", release="synthetic")
    database = SqliteDatabase(DatabaseConfig(path / "synthetic-watch.db"))
    await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    await database.start()
    writer = SqliteWatchWriter(database)
    metadata = SimpleNamespace(title=AsyncMock(return_value="Synthetic title"), close=AsyncMock())
    service = WatchService(writer, Capabilities("synthetic-capability-key-32-characters"), metadata,
        WatchLimits(), clock, Uuid4Generator(), telemetry)
    await service.start()
    transport = AsgiSession(build_control_app(service, SECRET))
    client = LoopbackClient("http://127.0.0.1:9001", SECRET, clock, transport)
    bot = MagicMock()
    channel = MagicMock()
    channel.send = AsyncMock(return_value=SimpleNamespace(id=600))
    channel.get_partial_message.return_value.delete = AsyncMock()
    bot.get_channel.return_value = channel
    messages = DiscordAdminMessages(bot, 2000, 42)
    controller = DiscordWatch(client, messages, 42, clock, Uuid4Generator(), telemetry)
    messages.controller = controller
    await controller.refresh()
    try:
        yield SimpleNamespace(clock=clock, database=database, writer=writer, service=service, client=client,
            controller=controller, messages=messages, channel=channel, buffer=buffer, bot=bot)
    finally:
        await controller.stop()
        messages.stop()
        await client.stop()
        await transport.close()
        await service.stop()
        await database.stop()
