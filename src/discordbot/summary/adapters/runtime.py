"""Opt-in resource: listeners, bounded reconciliation/cleanup, provider lifetime."""

from __future__ import annotations

import asyncio
from typing import Any

from discordbot.platform.clock import Clock, Uuid4Generator
from discordbot.platform.errors import AppError, ConflictError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor
from discordbot.platform.telemetry import TelemetryEmitter
from discordbot.summary.application.capture import Capture
from discordbot.summary.application.service import SummaryService
from discordbot.summary.domain.models import Scope, SummaryConfig
from discordbot.summary.adapters.discord_io import DiscordAuthorization, DiscordHistory, message_value
from discordbot.summary.adapters.discord_ui import SummaryCog, SummaryController
from discordbot.summary.ports.io import Provider


class SummaryResource:
    name = "summary"
    required = True

    def __init__(self, bot: Any, config: SummaryConfig, provider: Provider,
                 clock: Clock, telemetry: TelemetryEmitter, *, owns_bot: bool = False) -> None:
        self.bot, self.config, self.clock = bot, config, clock
        self.background = TaskSupervisor(capacity=3, history_capacity=16, clock=clock)
        requests = TaskSupervisor(capacity=5, history_capacity=32, clock=clock)
        self.service = SummaryService(config, clock, Uuid4Generator(), Capture(config, clock),
            DiscordAuthorization(bot), provider, requests, telemetry, require_preload=True)
        self.controller = SummaryController(self.service)
        self.history = DiscordHistory(bot)
        self.cog: Any = None
        self._running = False
        self._closed = False
        self._owns_bot = owns_bot
        self._reconcile_again = False
        self._preload: asyncio.Task[None] | None = None
        self._cleanup: asyncio.Task[None] | None = None

    def _spec(self, name: str, seconds: float) -> TaskSpec:
        return TaskSpec(name=name, owner="summary", work_id=name, correlation_id="summary-lifecycle",
            deadline_seconds=seconds, cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN)

    async def start(self) -> None:
        if self._running:
            return
        if self._closed:
            raise ConflictError("Summary resource cannot restart after stop")
        self._running = True
        try:
            if self.config.enabled:
                start = getattr(self.service.provider, "start", None)
                if start:
                    await start()
            self.cog = SummaryCog(self.controller)
            await self.bot.add_cog(self.cog)
            if self.config.enabled:
                self.bot.add_listener(self.message, "on_message")
                self.bot.add_listener(self.ready, "on_ready")
                self.bot.add_listener(self.ready, "on_resumed")
                self._schedule_cleanup()
        except BaseException:
            await self.stop()
            raise

    async def message(self, message: Any) -> None:
        if self._running and self.config.enabled:
            value = message_value(message)
            if value is not None:
                self.service.capture.add(value)

    async def ready(self) -> None:
        if not self._running or not self.config.enabled:
            return
        self.service.capture.invalidate()
        if self._preload and not self._preload.done():
            self._reconcile_again = True
            return
        self._schedule_preload()

    def _schedule_preload(self) -> None:
        self._reconcile_again = False
        self._preload = self.background.start(self._spec("preload", 60), self._reconcile)
        self._preload.add_done_callback(self._preload_done)
        # Gateway listener returns immediately. The supervisor owns this work.

    def _preload_done(self, task: asyncio.Task[None]) -> None:
        if self._running and self._reconcile_again:
            self._schedule_preload()

    async def _reconcile(self) -> None:
        for scope in self.config.sources:
            try:
                # One bad source cannot prevent other guilds reconciling forever.
                async with asyncio.timeout(5):
                    await self.service.capture.preload(scope, self.history)
            except (AppError, TimeoutError):
                self.service.telemetry.emit("summary.preload", component="summary", result="failed")

    def _schedule_cleanup(self) -> None:
        if self._running and self.config.enabled:
            self._cleanup = self.background.start(self._spec("cleanup", self.config.prune_seconds + 5), self._prune)
            # Handover after completion keeps TaskSpec deadline finite and the
            # supervisor's retained observation history bounded for long uptimes.
            self._cleanup.add_done_callback(self._cleanup_done)

    async def _prune(self) -> None:
        await asyncio.sleep(self.config.prune_seconds)
        self.controller.prune()

    def _cleanup_done(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is None:
            self._schedule_cleanup()

    async def stop(self) -> None:
        if self._closed:
            return
        self._running = False
        self._closed = True
        self.bot.remove_listener(self.message, "on_message")
        self.bot.remove_listener(self.ready, "on_ready")
        self.bot.remove_listener(self.ready, "on_resumed")
        try:
            if self.cog is not None:
                await self.bot.remove_cog(self.cog.qualified_name)
        finally:
            await self.background.shutdown(grace_seconds=2)
            self.controller.close()
            try:
                await self.service.stop()
            finally:
                if self._owns_bot:
                    await self.bot.close()


def create_summary_bot() -> Any:
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    return commands.Bot(command_prefix=commands.when_mentioned, intents=intents)
