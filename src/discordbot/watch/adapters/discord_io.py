"""Lazy Discord SDK UI. Uses the loopback client exclusively for Watch state."""

import asyncio
from typing import Any
from urllib.parse import urlsplit

from discordbot.platform.errors import AppError, CapacityError, ConfigurationError, ExternalTemporaryError
from discordbot.watch.application.discord_control import DiscordWatch
from discordbot.watch.adapters.security import public_origin

FAILURE = "❌ 시청 세션 방을 개설하는 동안 에러가 발생했습니다. 로그를 확인해 주세요."


class DiscordInteraction:
    def __init__(self, interaction: Any, origin: str) -> None:
        self.raw, self.origin = interaction, public_origin(origin)
        self.guild, self.user = interaction.guild_id or 0, interaction.user.id
        self.operation = str(interaction.id)
        self.issued = int(interaction.created_at.timestamp())
        self.acknowledged = self.failed = self.invited = False

    async def acknowledge(self) -> None:
        if self.acknowledged:
            return
        self.acknowledged = True  # Never retry an uncertain initial response.
        if not self.raw.response.is_done():
            async with asyncio.timeout(2):
                await self.raw.response.defer(thinking=True, ephemeral=False)

    async def invite(self, capability: str) -> tuple[int, int]:
        import discord
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="🎬 시청방 바로 입장", style=discord.ButtonStyle.link,
            url=f"{self.origin}/watch?session={capability}"))
        embed = discord.Embed(title="🎬 Watch Together 방이 개설되었습니다!",
            description="아래 버튼을 눌러 외부 웹 브라우저로 동시 시청 세션에 즉시 참여하세요.", color=discord.Color.blurple())
        embed.add_field(name="🔗 접속 정보", value="아래 버튼을 누르면 새 창이 열리며 입장합니다. 링크 주소를 친구들과 공유해 같이 시청할 수도 있습니다.", inline=False)
        embed.add_field(name="🧑 방장", value=self.raw.user.mention, inline=True)
        embed.set_footer(text="유튜브 공식 영상 중 퍼가기(임베드)가 금지된 일부 영상은 같이 재생이 불가능할 수 있습니다.")
        self.invited = True
        try:
            async with asyncio.timeout(5):
                message = await self.raw.edit_original_response(content=None, embed=embed, view=view)
            return message.channel.id, message.id
        finally:
            view.stop()

    async def retract(self) -> None:
        if self.acknowledged:
            async with asyncio.timeout(2):
                await self.raw.delete_original_response()

    async def failure(self) -> None:
        if self.failed:
            return
        self.failed = True
        try:
            async with asyncio.timeout(2):
                if self.acknowledged or self.raw.response.is_done():
                    await self.raw.followup.send(FAILURE, ephemeral=True)
                else:
                    self.acknowledged = True
                    await self.raw.response.send_message(FAILURE, ephemeral=True)
        except Exception:
            raise ExternalTemporaryError("Discord Watch response unavailable") from None


class DiscordAdminMessages:
    def __init__(self, bot: Any, channel_id: int, master: int) -> None:
        if type(channel_id) is not int or channel_id <= 0 or type(master) is not int or master <= 0:
            raise ConfigurationError("Watch private admin configuration required")
        self.bot, self.channel_id, self.master = bot, channel_id, master
        self.controller: DiscordWatch | None = None
        self.views: dict[int, Any] = {}

    async def create(self, session_id: str, guild: int, user: int) -> tuple[int, int]:
        import discord
        if len(self.views) >= 128:
            raise CapacityError("Watch admin view capacity")
        controller, master = self.controller, self.master
        class ControlView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=21600)

            @discord.ui.button(label="🛑 세션 강제 종료", style=discord.ButtonStyle.danger,
                custom_id="log_agent:close_watch_session")
            async def close_button(self, interaction, button):
                if interaction.user.id != master:
                    await interaction.response.send_message("이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
                    return
                await interaction.response.defer()
                try:
                    if controller is None:
                        raise ExternalTemporaryError("Watch control unavailable")
                    await controller.master_close(interaction.user.id, session_id)
                except AppError:
                    await interaction.followup.send(FAILURE, ephemeral=True)
                else:
                    button.disabled = True
                    self.stop()

        view = ControlView()
        try:
            async with asyncio.timeout(5):
                channel = self.bot.get_channel(self.channel_id) or await self.bot.fetch_channel(self.channel_id)
                embed = discord.Embed(title="🎬 Watch Together 세션 생성",
                    description="필요하면 아래 버튼으로 세션을 즉시 종료할 수 있습니다.", color=discord.Color.blurple())
                embed.add_field(name="서버 ID", value=str(guild), inline=True)
                embed.add_field(name="생성자", value=f"<@{user}>", inline=True)
                message = await channel.send(embed=embed, view=view)
            self.views[message.id] = view
            return self.channel_id, message.id
        except BaseException:
            view.stop()
            raise

    async def delete(self, channel: int, message: int) -> None:
        import discord
        try:
            async with asyncio.timeout(2):
                target = self.bot.get_channel(channel) or await self.bot.fetch_channel(channel)
                await target.get_partial_message(message).delete()
        except discord.NotFound:
            pass  # Idempotent deletion; the message is already absent.
        except Exception:
            raise ExternalTemporaryError("Discord Watch message cleanup unavailable") from None
        view = self.views.pop(message, None)
        if view:
            view.stop()

    def stop(self) -> None:
        for view in self.views.values():
            view.stop()
        self.views.clear()


def build_watch_cog(bot: Any, controller: DiscordWatch, origin: str):
    import discord
    from discord import app_commands
    from discord.ext import commands

    class WatchCog(commands.Cog):
        @app_commands.command(name="시청", description="외부 웹 브라우저에서 유튜브를 동시에 볼 수 있는 실시간 시청 방을 개설합니다.")
        async def watch_command(self, interaction: discord.Interaction):
            if not controller.health.snapshot().ready:
                await interaction.response.send_message("시청 기능이 아직 준비되지 않았습니다.", ephemeral=True)
                return
            wrapped = DiscordInteraction(interaction, origin)
            try:
                await controller.request(wrapped)
            except AppError:
                await wrapped.failure()

    return WatchCog()
