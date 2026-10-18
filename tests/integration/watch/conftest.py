from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from discordbot.platform.clock import Uuid4Generator
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.security import Capabilities
from discordbot.watch.adapters.writer import SqliteWatchWriter
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import WatchLimits


class Clock:
    def __init__(self):
        self.wall = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.tick = 1000.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.tick

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.tick += seconds


class Metadata:
    async def title(self, identity):
        return "Synthetic video"

    async def close(self):
        pass


class Socket:
    def __init__(self, gate=None):
        self.messages, self.codes = [], []
        self.gate = gate

    async def send(self, message):
        if self.gate:
            await self.gate.wait()
        self.messages.append(message)

    async def close(self, code):
        self.codes.append(code)


@pytest.fixture
def clock():
    return Clock()


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic-watch.db"))
    await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    await db.start()
    try:
        yield db
    finally:
        await db.stop()


@pytest_asyncio.fixture
async def service(database, clock):
    telemetry = TelemetryEmitter(buffer=TelemetryBuffer(128), clock=clock,
        service="watch-web", environment="test", release="synthetic")
    app = WatchService(SqliteWatchWriter(database), Capabilities("synthetic-capability-secret-32-characters"),
        Metadata(), WatchLimits(), clock, Uuid4Generator(), telemetry)
    await app.start()
    try:
        yield app
    finally:
        await app.stop()


@pytest_asyncio.fixture
async def invite(service, clock):
    return await service.create(100, 42, "synthetic-operation", int(clock.now().timestamp()))
