import discord
from discord.ext import commands
from discord import app_commands
import uuid
import os
import logging
from database_manager import add_watch_session

logger = logging.getLogger("WatchAgent")

class WatchAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 외부 도메인 주소 환경 변수 조회 (없으면 기본값 사용)
        self.base_url = os.getenv("WATCH_TOGETHER_URL", "http://localhost:8000")

    async def handle_watch_together(self, interaction: discord.Interaction, ephemeral: bool = False):
        # 1. 고유 세션 UUID 생성
        session_id = str(uuid.uuid4())
        guild_id = interaction.guild_id or 0
        user_id = interaction.user.id
        
        try:
            # 2. SQLite DB에 세션 등록
            await add_watch_session(session_id, guild_id, user_id)
            
            # 3. 접속 주소 구성
            join_url = f"{self.base_url}/watch?session={session_id}"
            
            # 4. 임베드 메시지 구성
            embed = discord.Embed(
                title="🎬 Watch Together 방이 개설되었습니다!",
                description="아래 링크를 통해 외부 웹 브라우저로 동시 시청 세션에 참여하세요.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="🔗 접속 주소 (친구들과 공유하세요)", value=f"[동시 시청 참여하기]({join_url})", inline=False)
            embed.add_field(name="🔑 세션 키", value=f"`{session_id}`", inline=True)
            embed.add_field(name="🧑 방장", value=interaction.user.mention, inline=True)
            embed.set_footer(text="유튜브 공식 영상 중 퍼가기(임베드)가 금지된 일부 영상은 같이 재생이 불가능할 수 있습니다.")
            
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            logger.info(f"Watch Together session created: {session_id} by User: {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to create Watch Together session: {e}", exc_info=True)
            await interaction.response.send_message("❌ 시청 세션 방을 개설하는 동안 에러가 발생했습니다. 로그를 확인해 주세요.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WatchAgentCog(bot))
