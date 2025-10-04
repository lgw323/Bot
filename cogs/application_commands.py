import os
import logging
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

# --- 다른 파일에서 기능 로직 임포트 (경로 수정) ---
from .finance.finance_agent import create_briefing_embed

# --- 로거 및 상수 ---
logger = logging.getLogger(__name__)
BOT_EMBED_COLOR = 0x5865F2
DEFAULT_SUMMARY_HOURS = float(os.getenv("DEFAULT_SUMMARY_HOURS", 6.0))

# --- 모든 명령어를 담는 Cog 클래스 ---
class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Cog 전역 에러 핸들러 추가 ---
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """이 Cog에 포함된 모든 명령어에서 처리되지 않은 오류를 잡아냅니다."""
        logger.error(f"명령어 '{interaction.command.name}' 실행 중 처리되지 않은 오류 발생: {error}", exc_info=True)
        
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

    # --- 경제 브리핑 명령어 (상세 로깅 추가) ---
    @app_commands.command(name="경제브리핑", description="현재 환율과 주요 주식 정보를 확인합니다.")
    async def get_briefing_command(self, interaction: discord.Interaction):
        logger.info(f"'/경제브리핑' 명령어 수신 (사용자: {interaction.user.name})")
        try:
            logger.info("응답을 지연시키기 위해 defer()를 호출합니다.")
            await interaction.response.defer(thinking=True)
            logger.info("defer() 호출 완료. create_briefing_embed()를 호출합니다.")
            
            embed = await create_briefing_embed()
            logger.info("Embed 생성 완료. followup.send()로 최종 응답을 보냅니다.")
            
            await interaction.followup.send(embed=embed)
            logger.info("'/경제브리핑' 명령어 처리가 성공적으로 완료되었습니다.")
        except discord.errors.InteractionResponded:
            logger.warning("'/경제브리핑' 처리 중 'InteractionResponded' 오류 발생. 이미 응답이 처리된 것으로 보입니다.")
        except Exception as e:
            logger.error(f"'/경제브리핑' 명령어 처리 중 예외 발생: {e}", exc_info=True)

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
