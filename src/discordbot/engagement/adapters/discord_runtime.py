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
from discordbot.engagement.ports.events import EngagementConfig, VoicePresence
from discordbot.platform.clock import Clock
from discordbot.platform.errors import ShutdownError, AppError, ConfigurationError
from discordbot.platform.tasks import require_tasks_stopped, TaskSupervisor
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
                self.service.gateway_session(self.stream)
                return
            if kind == "RESUMED":
                # Discord replays missed dispatches before this marker. Reopen
                # live time here, not on socket connect or each replay receipt.
                self.service.gateway_resumed()
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

    async def disconnected(self) -> None:
        try:
            self.service.gateway_disconnected()
        except AppError as exc:
            logger.warning("engagement voice disconnect failed: %s", exc.code.value)

    async def ready(self) -> None:
        # Capture the cache without awaiting; reconciliation and seeding share one
        # writer transaction. Current-stream events win over sequence-zero seeds.
        stream = self.stream
        members = []
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot:
                        continue
                    state = member.voice
                    members.append(VoicePresence(guild.id, member.id, channel.id,
                        bool(state and (state.self_mute or state.mute or state.self_deaf or state.deaf))))
        try:
            await self.service.voice_ready(stream, tuple(members))
        except AppError as exc:
            logger.warning("engagement voice recovery failed: %s", exc.code.value)


class EngagementResource:
    name = "engagement"
    required = True
    startup_cleanup_complete = False

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
            self.bot.add_listener(self.gateway.disconnected, "on_disconnect")
            self.bot.add_listener(self.ready, "on_ready")
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self.startup_cleanup_complete:
            return
        if getattr(self, "_stopping", False):
            raise ShutdownError("Engagement cleanup already incomplete")
        self._stopping = True
        was_started = self._service_started
        self._service_started = False
        self.bot.remove_listener(self.gateway.receive, "on_socket_raw_receive")
        self.bot.remove_listener(self.gateway.disconnected, "on_disconnect")
        self.bot.remove_listener(self.ready, "on_ready")
        await self.bot.remove_cog(self.cog.qualified_name)
        await self.scheduler.stop()
        require_tasks_stopped(await self.supervisor.shutdown(grace_seconds=2))
        if was_started:
            await self.service.stop()
        await self.bot.close()
        self.startup_cleanup_complete = True


def create_engagement_bot() -> commands.Bot:
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.voice_states = True
    return commands.Bot(command_prefix=commands.when_mentioned, intents=intents, enable_debug_events=True)
