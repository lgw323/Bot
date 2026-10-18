"""Discord presentation only. Command names/options and publicness remain V1-compatible."""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import discord
    from discord.ext import commands


from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.domain.policy import Progress, required_xp, valid_birthday
from discordbot.platform.errors import AppError, ConflictError, ExternalTemporaryError

logger = logging.getLogger(__name__)


def profile_embed(user: "discord.Member", progress: Progress) -> "discord.Embed":
    import discord

    previous = required_xp(progress.level - 1) if progress.level > 1 else 0
    total = required_xp(progress.level) - previous
    current = progress.total - previous
    ratio = current / total
    filled = int(ratio * 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    embed = discord.Embed(title=f"👤 {user.display_name}님의 정보", color=0x3498DB)
    embed.add_field(name="현재 레벨", value=f"**Lv.{progress.level}**", inline=True)
    embed.add_field(name="총 누적 경험치", value=f"**{progress.total:,} XP**", inline=True)
    embed.add_field(name="경험치 상세", value=f"💬 텍스트: {progress.text:,} XP\n🎙️ 음성: {progress.voice:,} XP", inline=False)
    embed.add_field(name="다음 레벨까지 (진행도)", value=f"{bar} **{ratio*100:.1f}%**\n`[ {current:,} / {total:,} XP ]` (달성까지 **{total-current:,} XP** 남음)", inline=False)
    embed.add_field(name="음성 채널 누적 체류", value=f"**{int(progress.seconds // 3600)}시간 {int(progress.seconds % 3600 // 60)}분**", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed


def chunks(lines: list[str], maximum: int = 3500) -> list[str]:
    pages: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > maximum:
            pages.append(current)
            current = ""
        current += ("\n" if current else "") + line
    if current:
        pages.append(current)
    return pages


async def error_response(interaction: "discord.Interaction", error: AppError) -> None:
    logger.warning("engagement command failed: %s", error.code.value)
    if interaction.response.is_done():
        await interaction.followup.send(error.safe_message, ephemeral=True)
    else:
        await interaction.response.send_message(error.safe_message, ephemeral=True)


def require_guild(interaction: "discord.Interaction") -> int:
    if interaction.guild is None:
        raise ConflictError("guild required", safe_message="이 명령어는 서버 내에서만 사용할 수 있습니다.")
    return interaction.guild.id


def EngagementCog(service: EngagementService) -> "commands.Cog":
    """Load SDK/class decorators only during explicit adapter construction."""
    import discord
    from discord import app_commands
    from discord.ext import commands

    class EngagementCog(commands.Cog):
        def __init__(self, service: EngagementService) -> None:
            self.service = service

        @commands.Cog.listener()
        async def on_message(self, message: discord.Message) -> None:
            try:
                await self.service.message(message.guild.id if message.guild else None, message.author.id,
                    str(message.id), message.content, message.created_at, bot=message.author.bot)
            except AppError as exc:
                logger.warning("engagement message failed: %s", exc.code.value)

        @app_commands.command(name="내정보", description="나의 현재 레벨과 경험치 진행도를 확인합니다.")
        async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                guild = require_guild(interaction)
                target_id = self.service.profile_target(interaction.user.id, user.id if user else None)
                target = user if user is not None and target_id == user.id else interaction.user
                progress = await self.service.profile(guild, target_id)
            except AppError as exc:
                await error_response(interaction, exc)
                return
            await interaction.followup.send(embed=profile_embed(target, progress))

        @app_commands.command(name="랭킹", description="서버 내 경험치 랭킹 TOP 10을 확인합니다.")
        async def leaderboard(self, interaction: discord.Interaction, ephemeral: bool = False) -> None:
            await interaction.response.defer(ephemeral=ephemeral)
            try:
                guild = require_guild(interaction)
                rows = await self.service.ranking(guild)
            except AppError as exc:
                await error_response(interaction, exc)
                return
            lines = []
            for index, row in enumerate(rows):
                member = interaction.guild.get_member(row.user_id)
                name = member.display_name if member else f"알 수 없는 유저 ({row.user_id})"
                progress = Progress(row.xp, row.total_vc_seconds)
                medal = ("🥇", "🥈", "🥉")[index] if index < 3 else "🏅"
                lines.append(f"{medal} **{index+1}위** | {name} - **Lv.{progress.level}** ({progress.total:,} XP)\n\n")
            embed = discord.Embed(title=f"🏆 {interaction.guild.name} 랭킹 TOP 10", color=0xF1C40F,
                description="".join(lines) if lines else "이 서버에 경험치가 기록된 유저가 없습니다.")
            await interaction.followup.send(embed=embed)

        @app_commands.command(name="생일등록", description="[어드민 전용] 멤버의 생일을 등록합니다.")
        @app_commands.describe(user="생일을 등록할 멤버", month="월 (1~12)", day="일 (1~31)")
        async def register_birthday(self, interaction: discord.Interaction, user: discord.Member, month: int, day: int) -> None:
            try:
                self.service.require_master(interaction.user.id)
                guild = require_guild(interaction)
                if not valid_birthday(month, day):
                    from discordbot.platform.errors import ValidationError
                    raise ValidationError("invalid calendar date", safe_message="올바른 날짜를 입력해주세요.")
                await interaction.response.defer(ephemeral=True)
                await self.service.register_birthday(interaction.user.id, guild, user.id, month, day)
            except AppError as exc:
                await error_response(interaction, exc)
                return
            await interaction.followup.send(f"✅ {user.display_name} 님의 생일을 {month}월 {day}일로 등록했습니다.", ephemeral=True)

        @app_commands.command(name="생일삭제", description="[어드민 전용] 멤버의 생일 정보를 삭제합니다.")
        @app_commands.describe(user="생일을 삭제할 멤버")
        async def delete_birthday(self, interaction: discord.Interaction, user: discord.Member) -> None:
            try:
                self.service.require_master(interaction.user.id)
                guild = require_guild(interaction)
                await interaction.response.defer(ephemeral=True)
                deleted = await self.service.delete_birthday(interaction.user.id, guild, user.id)
            except AppError as exc:
                await error_response(interaction, exc)
                return
            content = f"✅ {user.display_name} 님의 생일 정보를 삭제했습니다." if deleted else f"❌ {user.display_name} 님의 등록된 생일 정보가 없습니다."
            await interaction.followup.send(content, ephemeral=True)

        @app_commands.command(name="생일목록", description="서버에 등록된 생일 목록을 확인합니다.")
        async def list_birthdays(self, interaction: discord.Interaction, ephemeral: bool = False) -> None:
            try:
                guild = require_guild(interaction)
                # Empty results are always private. Inspect one bounded page before choosing ACK visibility.
                async with asyncio.timeout(2):
                    page = await self.service.birthdays(guild)
            except TimeoutError:
                await error_response(interaction, ExternalTemporaryError("birthday query timed out"))
                return
            except AppError as exc:
                await error_response(interaction, exc)
                return
            if not page:
                await interaction.response.send_message("현재 등록된 생일 정보가 없습니다.", ephemeral=True)
                return
            offset = 0
            while page:
                lines = []
                for row in page:
                    member = interaction.guild.get_member(row.user_id)
                    name = member.display_name if member else f"알 수 없는 유저({row.user_id})"
                    lines.append(f"• **{name}**: {row.birth_month}월 {row.birth_day}일")
                for description in chunks(lines):
                    embed = discord.Embed(title="🎂 서버 생일 목록 🎂", description=description, color=0xFFB6C1)
                    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
                    await send(embed=embed, ephemeral=ephemeral)
                if len(page) < 100:
                    return
                offset += 100
                try:
                    page = await self.service.birthdays(guild, offset=offset)
                except AppError as exc:
                    await error_response(interaction, exc)
                    return

    return EngagementCog(service)


class DiscordBirthdayDelivery:
    def __init__(self, bot: "commands.Bot") -> None:
        self.bot = bot

    async def send(self, guild_id: int, channel_id: int, users: tuple[int, ...]) -> None:
        import discord

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild_id:
            raise ConflictError("birthday channel is unavailable or belongs to another guild")
        for mentions in chunks([f"<@{user}>" for user in users], maximum=3000):
            embed = discord.Embed(title="🎉 오늘은 생일입니다! 🎉", color=0xFFB6C1,
                description=f"@everyone 오늘은 {mentions.replace(chr(10), ', ')} 님의 생일입니다!\n모두 축하해주세요! 🎂🎁")
            await channel.send(embed=embed)
