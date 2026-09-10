"""Discord-only lifecycle. An unavailable Watch dependency keeps Gateway alive."""

from typing import Any

from discordbot.platform.clock import Clock, Uuid4Generator
from discordbot.platform.telemetry import TelemetryEmitter
from discordbot.platform.errors import ConflictError
from discordbot.watch.adapters.control_client import LoopbackClient
from discordbot.watch.adapters.discord_io import DiscordAdminMessages, build_watch_cog
from discordbot.watch.adapters.security import public_origin
from discordbot.watch.application.discord_control import DiscordWatch


class DiscordWatchResource:
    name = "watch-loopback"
    required = False

    def __init__(self, bot: Any, origin: str, control_url: str, control_secret: str, admin_channel: int,
                 master: int, clock: Clock, telemetry: TelemetryEmitter, session: Any = None) -> None:
        self.bot, self.origin = bot, public_origin(origin)
        self.client = LoopbackClient(control_url, control_secret, clock, session)
        self.messages = DiscordAdminMessages(bot, admin_channel, master)
        self.controller = DiscordWatch(self.client, self.messages, master, clock, Uuid4Generator(), telemetry)
        self.messages.controller = self.controller
        self.cog = None
        self.started = self.closed = False

    async def start(self) -> None:
        if self.started:
            return
        if self.closed:
            raise ConflictError("Discord Watch resource stopped")
        try:
            await self.client.start()
            self.cog = build_watch_cog(self.bot, self.controller, self.origin)
            await self.bot.add_cog(self.cog)
            await self.controller.refresh()  # Typed connection failure changes only capability health.
            self.controller.schedule()
            self.started = True
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.cog is not None:
                await self.bot.remove_cog(self.cog.qualified_name)
                self.cog = None
        finally:
            await self.controller.stop()
            self.messages.stop()
            await self.client.stop()
