"""Opt-in watch-web resource. Explicit start; no bootstrap or server at import."""

from discordbot.platform.clock import Clock, Uuid4Generator
from discordbot.platform.telemetry import TelemetryEmitter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.watch.adapters.control_server import build_control_app
from discordbot.watch.adapters.metadata import OEmbed
from discordbot.watch.adapters.security import Capabilities
from discordbot.watch.adapters.web import build_public_app
from discordbot.watch.adapters.writer import SqliteWatchWriter
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import WatchLimits


class WatchWebResource:
    name = "watch-web"
    required = True

    def __init__(self, database: SqliteDatabase, origin: str, capability_secret: str, control_secret: str,
                 clock: Clock, telemetry: TelemetryEmitter, metadata=None, limits: WatchLimits = WatchLimits()) -> None:
        self.database = database
        self.metadata = metadata if metadata is not None else OEmbed()
        self.service = WatchService(SqliteWatchWriter(database), Capabilities(capability_secret), self.metadata,
            limits, clock, Uuid4Generator(), telemetry)
        self.public_app = build_public_app(self.service, origin)
        self.control_app = build_control_app(self.service, control_secret)
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        try:
            await self.database.start()  # Existing Phase 3 store only; never bootstrap automatically.
            start = getattr(self.metadata, "start", None)
            if start:
                await start()
            await self.service.start()
            self.service.schedule()
            self.started = True
        except BaseException:
            try:
                await self.service.stop()
            finally:
                await self.database.stop()
            raise

    async def stop(self) -> None:
        try:
            await self.service.stop()
        finally:
            await self.database.stop()
            self.started = False
