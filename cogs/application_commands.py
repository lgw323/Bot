import os
import logging # 이 줄은 삭제해도 되지만, 다른 파일과의 일관성을 위해 유지합니다.
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

# --- 로거 및 상수 ---
# logger = logging.getLogger(__name__) # 이 줄을 삭제합니다.
BOT_EMBED_COLOR = 0x5865F2
DEFAULT_SUMMARY_HOURS = float(os.getenv("DEFAULT_SUMMARY_HOURS", 6.0))

# --- 모든 명령어를 담는 Cog 클래스 ---
class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Cog 전역 에러 핸들러 추가 ---
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """이 Cog에 포함된 모든 명령어에서 처리되지 않은 오류를 잡아냅니다."""
        # self.bot.log를 사용하여 에러를 기록합니다.
        self.bot.log.error(f"명령어 '{interaction.command.name}' 실행 중 처리되지 않은 오류 발생: {error}", exc_info=True)
        
        # 상호작용에 이미 응답했는지 확인합니다.
        if not interaction.response.is_done():
            await interaction.response.send_message("명령어 처리 중 오류가 발생했습니다. 관리자에게 문의해주세요.", ephemeral=True)
        else:
            await interaction.followup.send("명령어 처리 중 오류가 발생했습니다. 관리자에게 문의해주세요.", ephemeral=True)

    # --- 요약 명령어 ---
    @app_commands.command(name="요약", description="최근 대화를 요약합니다.")
    @app_commands.describe(hours=f"요약 대상 시간 (기본: {DEFAULT_SUMMARY_HOURS}시간)")
    async def summary_command(self, interaction: discord.Interaction, hours: float = DEFAULT_SUMMARY_HOURS):
        summary_cog = self.bot.get_cog("SummaryListenersCog")
        if not summary_cog:
            await interaction.response.send_message("요약 기능이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=False)
        await summary_cog.execute_summary(interaction, hours)

    # --- 노래 명령어 (단일화) ---
    @app_commands.command(name="재생", description="유튜브 링크나 검색어로 노래를 재생하고, 봇을 음성 채널로 자동 초대합니다.")
    @app_commands.describe(검색어="재생할 노래의 유튜브 URL 또는 검색어")
    async def play(self, interaction: discord.Interaction, 검색어: str):
        cog = self.bot.get_cog("MusicAgentCog")
        if cog:
            await cog.handle_play(interaction, 검색어)
        else:
            await interaction.response.send_message("노래 기능이 아직 준비되지 않았습니다.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandsCog(bot))
