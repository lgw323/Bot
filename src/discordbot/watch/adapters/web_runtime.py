"""Opt-in watch-web resource. Explicit start; no bootstrap or server at import."""

from discordbot.platform.clock import Clock, Uuid4Generator
from discordbot.platform.errors import ShutdownError
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
    startup_cleanup_complete = False

    def __init__(self, database: SqliteDatabase, origin: str, capability_secret: str, control_secret: str,
                 clock: Clock, telemetry: TelemetryEmitter, metadata=None, limits: WatchLimits = WatchLimits()) -> None:
        self.database = database
        self.metadata = metadata if metadata is not None else OEmbed()
        self.service = WatchService(SqliteWatchWriter(database), Capabilities(capability_secret), self.metadata,
            limits, clock, Uuid4Generator(), telemetry)
        self.public_app = build_public_app(self.service, origin)
        self.control_app = build_control_app(self.service, control_secret)
        self.started = False
        self._database_closed = False
        self._stopping = False

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
        except BaseException as original:
            try:
                await self.stop()
            except BaseException as cleanup_error:
                raise original from cleanup_error
            raise

    async def stop(self) -> None:
        if self.startup_cleanup_complete:
            return
        if self._stopping:
            raise ShutdownError("Watch web cleanup already in progress")
        self._stopping = True
        self.started = False
        try:
            errors: list[BaseException] = []
            try:
                await self.service.stop()
            except BaseException as error:
                errors.append(error)
            # A pending lease release still needs its DB. Metadata close does
            # not, so a failed metadata close cannot retain a drained database.
            if self.service._work_stopped and not self.service._release_pending and not self._database_closed:
                try:
                    await self.database.stop()
                except BaseException as error:
                    errors.append(error)
                else:
                    self._database_closed = True
            self.startup_cleanup_complete = self.service._cleanup_complete and self._database_closed
            if errors:
                if len(errors) > 1:
                    raise errors[0] from errors[-1]
                raise errors[0]
        finally:
            self._stopping = False
