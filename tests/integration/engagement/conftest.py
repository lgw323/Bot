from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


class FakeClock:
    def __init__(self):
        self.wall = datetime(2027, 2, 28, 0, tzinfo=timezone.utc)
        self.tick = 1000.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.tick

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.tick += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic-engagement.db"))
    await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    await db.start()
    try:
        yield db
    finally:
        await db.stop()


@pytest_asyncio.fixture
async def service(database, clock):
    app = EngagementService(SqliteEngagementRepository(database), SqliteEngagementEvents(database),
        MasterAuthorization(42), EngagementConfig(42, ((100, 1001), (200, 2001))), clock, "synthetic-boot")
    await app.start()
    try:
        yield app
    finally:
        await app.stop()
