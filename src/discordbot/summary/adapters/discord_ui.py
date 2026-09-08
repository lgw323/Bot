"""Lazy Discord UI and a single responder owner for each interaction."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from discordbot.platform.errors import (AppError, CancellationError, DeadlineExceededError,
    ExternalPermanentError, InternalError, ValidationError)
from discordbot.summary.application.service import SummaryService
from discordbot.summary.domain.models import Query, Result


class ResponderFailure(ExternalPermanentError):
    pass


class Responder:
    def __init__(self, interaction: Any) -> None:
        self.interaction = interaction
        self.acknowledged = bool(interaction.response.is_done())
        self.finished = False

    async def _call(self, call: Callable[[], Awaitable[Any]]) -> Any:
        try:
            async with asyncio.timeout(2):
                return await call()
        except asyncio.CancelledError:
            self.finished = True  # delivery outcome is uncertain; never retry
            raise
        except Exception:
            self.finished = True
            raise ResponderFailure("Summary Discord delivery failed") from None

    async def defer(self, *, ephemeral: bool = False) -> None:
        if not self.acknowledged and not self.finished:
            self.acknowledged = True  # claim before I/O, including uncertain failures
            await self._call(lambda: self.interaction.response.defer(thinking=True, ephemeral=ephemeral))

    async def send(self, **kwargs: Any) -> Any:
        if self.finished:
            return None
        self.finished = True
        if self.acknowledged:
            return await self._call(lambda: self.interaction.followup.send(wait=True, **kwargs))
        self.acknowledged = True
        return await self._call(lambda: self.interaction.response.send_message(**kwargs))

    async def modal(self, modal: Any) -> None:
        if self.finished or self.acknowledged:
            raise ResponderFailure("Summary modal already acknowledged")
        self.finished = self.acknowledged = True
        await self._call(lambda: self.interaction.response.send_modal(modal))

    async def error(self, error: AppError) -> None:
        # Class-owned messages only: arbitrary vendor diagnostics/safe_message
        # overrides must not leak via a dependency exception.
        await self.send(content=type(error).default_safe_message, ephemeral=True)


def summary_embed(result: Result, requester: str, page: int = 0) -> Any:
    import discord

    embed = discord.Embed(title=f"최근 {result.query.hours}시간 대화 요약",
        description=f"**📈 전체 대화 개요:**\n{result.summary.overall}", color=0x5865F2, timestamp=result.created_at)
    for value, topic in result.page(page):
        index = int(value.rsplit(":", 1)[1])
        embed.add_field(name=f"📌 주제 {index+1}: {topic.title[:30]}",
            value=f"**참여자:** {topic.participants[:15]}\n**키워드:** {topic.keywords[:15]}", inline=False)
    embed.set_footer(text=f"요청자: {requester[:100]} | 프롬프트 토큰: {result.summary.input_tokens:,} | {page+1}/{(len(result.summary.topics)+24)//25}")
    return embed


class SummaryController:
    def __init__(self, service: SummaryService) -> None:
        self.service = service
        self._views: dict[str, tuple[Any, float]] = {}
        self._modals: dict[str, tuple[Any, float]] = {}

    def prune(self) -> None:
        self.service.prune()
        for key in tuple(self._views):
            if self._views[key][1] <= self.service.clock.monotonic():
                self._views.pop(key)[0].stop()
        for key in tuple(self._modals):
            if self._modals[key][1] <= self.service.clock.monotonic():
                self._modals.pop(key)[0].stop()

    def close(self) -> None:
        for view, _ in self._views.values():
            view.stop()
        self._views.clear()
        for modal, _ in self._modals.values():
            modal.stop()
        self._modals.clear()

    async def run(self, interaction: Any, action: Callable[[Responder, float], Awaitable[None]]) -> None:
        responder = Responder(interaction)
        deadline = self.service.clock.monotonic() + 60
        try:
            try:
                async with self.service.timeout(self.service.remaining(deadline)):
                    await action(responder, deadline)
            except (TimeoutError, DeadlineExceededError):
                await responder.error(DeadlineExceededError("Summary deadline"))
            except ResponderFailure:
                raise
            except AppError as exc:
                await responder.error(exc)
            except asyncio.CancelledError:
                await responder.error(CancellationError("Summary cancelled"))
                raise
            except Exception:
                await responder.error(InternalError("Summary UI failed"))
        except ResponderFailure:
            self.service.telemetry.emit("summary.response", component="summary", result="delivery_failed")

    @staticmethod
    def context(interaction: Any) -> tuple[int, int, int]:
        if interaction.guild is None or interaction.channel_id is None:
            raise ValidationError("Summary requires guild")
        return interaction.guild.id, interaction.channel_id, interaction.user.id

    async def access(self, interaction: Any, result_id: str, message_id: int | None = None) -> Result:
        guild, channel, user = self.context(interaction)
        # This pre-modal check cannot consume Discord's three-second ACK window.
        async with asyncio.timeout(2):
            return await self.service.access(result_id, guild, channel, user,
                message_id if message_id is not None else interaction.message.id)

    async def deliver(self, interaction: Any, responder: Responder, query: Query,
                      deadline: float, previous: str | None = None) -> None:
        guild, channel, user = self.context(interaction)
        query.validate(self.service.config.retention_hours)
        self.service.scope(guild)
        await responder.defer()
        task = self.service.submit(guild, user, channel, query, deadline=deadline, previous=previous)
        view = None
        try:
            result = await task
            self.prune()
            view = SummaryView(self, result)
            sent = await responder.send(embed=summary_embed(result, interaction.user.display_name),
                                        view=view, ephemeral=False)
            self.service.bind(result.id, sent.id)
            if len(self._views) >= self.service.config.result_capacity:
                self._views.pop(next(iter(self._views)))[0].stop()
            self._views[result.id] = (view, result.expires_at)
        except BaseException:
            if view is not None:
                view.stop()
            # Cancellation can race with a completed application task before
            # its value is delivered to this coroutine. Reclaim that result too.
            if task.done() and not task.cancelled() and task.exception() is None:
                self.service.discard(task.result().id)
            raise

    async def execute(self, interaction: Any, query: Query) -> None:
        await self.run(interaction, lambda responder, deadline: self.deliver(interaction, responder, query, deadline))

    async def refresh(self, interaction: Any, result_id: str) -> None:
        async def action(responder: Responder, deadline: float) -> None:
            result = await self.access(interaction, result_id)
            await self.deliver(interaction, responder, result.query, deadline, previous=result_id)
        await self.run(interaction, action)

    async def advanced(self, interaction: Any, result_id: str) -> None:
        async def action(responder: Responder, deadline: float) -> None:
            result = await self.access(interaction, result_id)
            self.prune()
            modal = AdvancedSummaryModal(self, result)
            if len(self._modals) >= self.service.config.result_capacity:
                self._modals.pop(next(iter(self._modals)))[0].stop()
            self._modals[modal.custom_id] = (modal, self.service.clock.monotonic() + 300)
            try:
                await responder.modal(modal)
            except BaseException:
                self._modals.pop(modal.custom_id)[0].stop()
                raise
        await self.run(interaction, action)

    async def submit_modal(self, interaction: Any, result_id: str, message_id: int, query: Query) -> None:
        async def action(responder: Responder, deadline: float) -> None:
            await self.access(interaction, result_id, message_id)
            await self.deliver(interaction, responder, query, deadline, previous=result_id)
        await self.run(interaction, action)

    async def detail(self, interaction: Any, result_id: str, selection: str) -> None:
        import discord

        async def action(responder: Responder, deadline: float) -> None:
            result = await self.access(interaction, result_id)
            topic = self.service.topic(result, selection)
            embed = discord.Embed(title=f"주제 {int(selection.rsplit(':', 1)[1])+1}: {topic.title}", color=0x5865F2)
            for name, value in (("논의 시간대", topic.time), ("주요 참여자", topic.participants),
                ("핵심 키워드", topic.keywords), ("핵심 요지", topic.main_point),
                ("배경/맥락", topic.context), ("세부 내용", topic.details)):
                embed.add_field(name=name, value=value, inline=False)
            await responder.send(embed=embed, ephemeral=True)
        await self.run(interaction, action)

    async def page(self, interaction: Any, result_id: str, number: int) -> None:
        async def action(responder: Responder, deadline: float) -> None:
            result = await self.access(interaction, result_id)
            result.page(number)
            # Each navigation edits the bound public message, leaving the full
            # immutable result and absolute selection IDs unchanged.
            view = SummaryView(self, result, number)
            responder.finished = responder.acknowledged = True
            try:
                await responder._call(lambda: interaction.response.edit_message(
                    embed=summary_embed(result, interaction.user.display_name, number), view=view))
            except BaseException:
                view.stop()
                raise
            old = self._views.pop(result_id, None)
            if old:
                old[0].stop()
            self._views[result_id] = (view, result.expires_at)
        await self.run(interaction, action)


def SummaryView(controller: SummaryController, result: Result, page: int = 0) -> Any:
    import discord

    view = discord.ui.View(timeout=max(0.01, result.expires_at - controller.service.clock.monotonic()))
    refresh = discord.ui.Button(label="새로고침", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    refresh.callback = lambda i: controller.refresh(i, result.id)
    advanced = discord.ui.Button(label="고급 요약", emoji="✨", style=discord.ButtonStyle.primary, row=1)
    advanced.callback = lambda i: controller.advanced(i, result.id)
    view.add_item(refresh)
    view.add_item(advanced)
    select = discord.ui.Select(placeholder="자세히 볼 주제를 선택하세요...", options=[
        discord.SelectOption(label=f"주제 {int(value.rsplit(':', 1)[1])+1}: {topic.title}"[:100], value=value)
        for value, topic in result.page(page)])
    # Read the interaction payload, not mutable Select.values shared by callbacks.
    select.callback = lambda i: controller.detail(i, result.id, (i.data.get("values") or [""])[0])
    view.add_item(select)
    if len(result.summary.topics) > 25:
        for label, number in (("이전", page-1), ("다음", page+1)):
            button = discord.ui.Button(label=label, row=2,
                disabled=not 0 <= number < (len(result.summary.topics)+24)//25)
            async def callback(interaction: Any, target: int = number) -> None:
                await controller.page(interaction, result.id, target)
            button.callback = callback
            view.add_item(button)
    return view


def AdvancedSummaryModal(controller: SummaryController, result: Result) -> Any:
    import discord

    class Modal(discord.ui.Modal, title="고급 요약 옵션"):
        def __init__(self) -> None:
            super().__init__(timeout=300)
            self.keywords = discord.ui.TextInput(label="포함할 키워드 (쉼표로 구분)", required=False, max_length=1000)
            self.users = discord.ui.TextInput(label="특정 사용자 이름 (쉼표로 구분)", required=False, max_length=1000)
            self.extra = discord.ui.TextInput(label="추가 요청사항", required=False, max_length=1000, style=discord.TextStyle.long)
            for item in (self.keywords, self.users, self.extra):
                self.add_item(item)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            try:
                await controller.submit_modal(interaction, result.id, result.message_id,
                    Query(result.query.hours, self.keywords.value, self.users.value, self.extra.value))
            finally:
                controller._modals.pop(self.custom_id, None)
                self.stop()
    return Modal()


def SummaryCog(controller: SummaryController) -> Any:
    import discord
    from discord import app_commands
    from discord.ext import commands

    class Cog(commands.Cog, name="SummaryV2"):
        @app_commands.command(name="요약", description="최근 대화를 요약합니다.")
        @app_commands.describe(hours="요약 대상 시간 (기본: 6.0시간)")
        async def summarize(self, interaction: discord.Interaction, hours: float = 6.0) -> None:
            await controller.execute(interaction, Query(hours))
    return Cog()
