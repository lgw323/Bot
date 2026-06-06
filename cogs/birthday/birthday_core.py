import os
import logging
import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

from database_manager import add_birthday, remove_birthday, get_birthdays_today, get_all_birthdays

logger: logging.Logger = logging.getLogger(__name__)

MASTER_USER_ID: int = int(os.getenv("MASTER_USER_ID", "0"))
SUMMARY_CHANNEL_ID: int = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))

class BirthdayCoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        if SUMMARY_CHANNEL_ID != 0:
            self.birthday_loop.start()

    def cog_unload(self) -> None:
        self.birthday_loop.cancel()

    # KST 기준 매일 오전 9시
    KST = datetime.timezone(datetime.timedelta(hours=9))
    target_time = datetime.time(hour=9, minute=0, tzinfo=KST)

    @tasks.loop(time=target_time)
    async def birthday_loop(self) -> None:
        await self.bot.wait_until_ready()
        if SUMMARY_CHANNEL_ID == 0:
            return

        channel = self.bot.get_channel(SUMMARY_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.error(f"생일 알람 전송 실패: SUMMARY_CHANNEL_ID({SUMMARY_CHANNEL_ID}) 채널을 찾을 수 없거나 텍스트 채널이 아닙니다.")
            return

        now = datetime.datetime.now(self.KST)
        month, day = now.month, now.day

        # 모든 길드를 돌면서 오늘 생일인 사람을 찾습니다.
        for guild in self.bot.guilds:
            birthday_users = await get_birthdays_today(guild.id, month, day)
            if not birthday_users:
                continue

            # 생일인 사람 멘션 문자열 생성
            mentions = []
            for uid in birthday_users:
                member = guild.get_member(uid)
                if member:
                    mentions.append(member.mention)
                else:
                    mentions.append(f"<@{uid}>")
            
            mentions_str = ", ".join(mentions)
            
            embed = discord.Embed(
                title="🎉 오늘은 생일입니다! 🎉",
                description=f"@everyone 오늘은 {mentions_str} 님의 생일입니다!\n모두 축하해주세요! 🎂🎁",
                color=0xFFB6C1
            )
            try:
                await channel.send(embed=embed)
                logger.info(f"[{guild.name}] 생일 축하 메시지 전송 완료: {mentions_str}")
            except Exception as e:
                logger.error(f"[{guild.name}] 생일 축하 메시지 전송 중 오류: {e}")

    @app_commands.command(name="생일등록", description="[어드민 전용] 멤버의 생일을 등록합니다.")
    @app_commands.describe(user="생일을 등록할 멤버", month="월 (1~12)", day="일 (1~31)")
    async def register_birthday(self, interaction: discord.Interaction, user: discord.Member, month: int, day: int):
        if interaction.user.id != MASTER_USER_ID:
            await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
            return

        if not (1 <= month <= 12) or not (1 <= day <= 31):
            await interaction.response.send_message("올바른 날짜를 입력해주세요.", ephemeral=True)
            return

        await add_birthday(user.id, interaction.guild_id, month, day)
        await interaction.response.send_message(f"✅ {user.display_name} 님의 생일을 {month}월 {day}일로 등록했습니다.", ephemeral=True)

    @app_commands.command(name="생일삭제", description="[어드민 전용] 멤버의 생일 정보를 삭제합니다.")
    @app_commands.describe(user="생일을 삭제할 멤버")
    async def delete_birthday(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id != MASTER_USER_ID:
            await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
            return

        count = await remove_birthday(user.id, interaction.guild_id)
        if count > 0:
            await interaction.response.send_message(f"✅ {user.display_name} 님의 생일 정보를 삭제했습니다.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {user.display_name} 님의 등록된 생일 정보가 없습니다.", ephemeral=True)

    @app_commands.command(name="생일목록", description="서버에 등록된 생일 목록을 확인합니다.")
    async def list_birthdays(self, interaction: discord.Interaction):
        birthdays = await get_all_birthdays(interaction.guild_id)
        if not birthdays:
            await interaction.response.send_message("현재 등록된 생일 정보가 없습니다.", ephemeral=True)
            return

        lines = []
        for b in birthdays:
            member = interaction.guild.get_member(b['user_id'])
            name = member.display_name if member else f"알 수 없는 유저({b['user_id']})"
            lines.append(f"• **{name}**: {b['month']}월 {b['day']}일")
        
        embed = discord.Embed(title="🎂 서버 생일 목록 🎂", description="\n".join(lines), color=0xFFB6C1)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BirthdayCoreCog(bot))
