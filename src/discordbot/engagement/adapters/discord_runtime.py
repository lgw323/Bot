"""Opt-in Engagement wiring; construction never logs in or migrates a database."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord.ext import commands

from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.discord_ui import DiscordBirthdayDelivery, EngagementCog
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.scheduler import BirthdayScheduler
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.platform.clock import Clock
from discordbot.platform.errors import AppError, ConfigurationError
from discordbot.platform.tasks import TaskSupervisor
from discordbot.storage.adapters.execution import SqliteDatabase

logger = logging.getLogger(__name__)


class VoiceGateway:
    """Only transport cursor metadata lives here; voice accrual state lives in SQLite.

    discord.py 2.7 exposes decompressed JSON via socket_raw_receive when debug
    events are enabled. The payload is never retained/logged. Stable session hash
    plus Gateway sequence rejects resumed/redelivered/out-of-order voice events.
    """
    def __init__(self, bot: commands.Bot, service: EngagementService) -> None:
        self.bot = bot
        self.service = service
        self.stream = "initial"

    async def receive(self, payload: str | bytes) -> None:
        if not isinstance(payload, str) or len(payload) > 2 * 1024 * 1024:
            logger.warning("unsupported or oversized engagement gateway frame")
            return
        try:
            packet = json.loads(payload)
            if packet.get("op") != 0:
                return
            kind, data, sequence = packet.get("t"), packet.get("d"), packet.get("s")
            if kind == "READY":
                self.stream = hashlib.sha256(data["session_id"].encode()).hexdigest()
                return
            if kind != "VOICE_STATE_UPDATE":
                return
            guild = self.bot.get_guild(int(data["guild_id"]))
            user = int(data["user_id"])
            member = guild.get_member(user) if guild else None
            raw_user = data.get("member", {}).get("user", {})
            is_bot = raw_user.get("bot", False) if raw_user else member.bot if member else True
            await self.service.voice(int(data["guild_id"]), user, self.stream, int(sequence),
                int(data["channel_id"]) if data.get("channel_id") else None,
                any(data.get(key, False) for key in ("self_mute", "mute", "self_deaf", "deaf")), bot=is_bot)
        except AppError as exc:
            logger.warning("engagement voice failed: %s", exc.code.value)
        except (TypeError, ValueError, KeyError, AttributeError):
            logger.warning("invalid engagement gateway event")

    async def ready(self) -> None:
        # Sequence zero seeds only missing sessions. Repeated ready never resets
        # a session whose sequenced events were already observed in this stream.
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    state = member.voice
                    try:
                        await self.service.voice(guild.id, member.id, self.stream, 0, channel.id,
                            bool(state and (state.self_mute or state.mute or state.self_deaf or state.deaf)), bot=member.bot)
                    except AppError as exc:
                        logger.warning("engagement voice recovery failed: %s", exc.code.value)


class EngagementResource:
    name = "engagement"
    required = True

    def __init__(self, bot: commands.Bot, database: SqliteDatabase, config: EngagementConfig,
                 clock: Clock, supervisor: TaskSupervisor, epoch: str) -> None:
        self.bot = bot
        self.supervisor = supervisor
        self.service = EngagementService(SqliteEngagementRepository(database), SqliteEngagementEvents(database),
            MasterAuthorization(config.master_user_id), config, clock, epoch)
        self.gateway = VoiceGateway(bot, self.service)
        self.scheduler = BirthdayScheduler(self.service, DiscordBirthdayDelivery(bot), supervisor)
        self.cog = EngagementCog(self.service)
        self._service_started = False

    async def ready(self) -> None:
        if not self._service_started:
            return
        await self.gateway.ready()
        if self._service_started:
            self.scheduler.start()

    async def start(self) -> None:
        try:
            if not getattr(self.bot, "_enable_debug_events", False):
                raise ConfigurationError("engagement voice requires Discord debug receive events")
            await self.service.start()
            self._service_started = True
            await self.bot.add_cog(self.cog)
            self.bot.add_listener(self.gateway.receive, "on_socket_raw_receive")
            self.bot.add_listener(self.ready, "on_ready")
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        was_started = self._service_started
        self._service_started = False
        self.bot.remove_listener(self.gateway.receive, "on_socket_raw_receive")
        self.bot.remove_listener(self.ready, "on_ready")
        try:
            await self.bot.remove_cog(self.cog.qualified_name)
            await self.scheduler.stop()
            await self.supervisor.shutdown(grace_seconds=2)
            if was_started:
                await self.service.stop()
        finally:
            await self.bot.close()


def create_engagement_bot() -> commands.Bot:
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.voice_states = True
    return commands.Bot(command_prefix=commands.when_mentioned, intents=intents, enable_debug_events=True)
