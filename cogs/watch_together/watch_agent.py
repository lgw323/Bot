import discord
from discord.ext import commands
import uuid
import os
import logging
from database_manager import add_watch_session, get_all_watch_sessions

logger = logging.getLogger("WatchAgent")

class WatchTogetherJoinView(discord.ui.View):
    def __init__(self, join_url: str):
        super().__init__(timeout=None)
        # 1클릭 입장용 링크 버튼 추가
        self.add_item(discord.ui.Button(label="🎬 시청방 바로 입장", url=join_url, style=discord.ButtonStyle.link))

class WatchAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 외부 도메인 주소 환경 변수 조회 (없으면 기본값 사용)
        self.base_url = os.getenv("WATCH_TOGETHER_URL", "http://localhost:8000")
        self._stale_sessions_cleaned = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Remove sessions left behind by a previous bot process."""
        if self._stale_sessions_cleaned:
            return

        from .watch_server import close_watch_session, manager

        try:
            for session in await get_all_watch_sessions():
                session_id = session["session_id"]
                if not manager.active_connections.get(session_id):
                    await close_watch_session(
                        session_id,
                        reason="봇 재시작 후 접속자 없음",
                    )
            self._stale_sessions_cleaned = True
        except Exception as e:
            logger.error(
                "Watch Together 이전 세션 정리에 실패했습니다: %s",
                e,
                exc_info=True,
            )

    async def handle_watch_together(self, interaction: discord.Interaction, ephemeral: bool = False):
        # 1. 고유 세션 UUID 생성
        session_id = str(uuid.uuid4())
        guild_id = interaction.guild_id or 0
        user_id = interaction.user.id
        
        try:
            # 2. 접속 주소 구성
            join_url = f"{self.base_url}/watch?session={session_id}"
            
            # 3. 임베드 메시지 구성
            embed = discord.Embed(
                title="🎬 Watch Together 방이 개설되었습니다!",
                description="아래 버튼을 눌러 외부 웹 브라우저로 동시 시청 세션에 즉시 참여하세요.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="🔗 접속 정보", value="아래 버튼을 누르면 새 창이 열리며 입장합니다. 링크 주소를 친구들과 공유해 같이 시청할 수도 있습니다.", inline=False)
            embed.add_field(name="🔑 세션 키", value=f"`{session_id}`", inline=True)
            embed.add_field(name="🧑 방장", value=interaction.user.mention, inline=True)
            embed.set_footer(text="유튜브 공식 영상 중 퍼가기(임베드)가 금지된 일부 영상은 같이 재생이 불가능할 수 있습니다.")
            
            # 버튼이 포함된 뷰 인스턴스 생성
            view = WatchTogetherJoinView(join_url)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
            
            # 4. 메시지 ID 및 채널 ID 캡처 (ephemeral=False 인 경우에만)
            message_id = None
            channel_id = None
            if not ephemeral:
                try:
                    msg = await interaction.original_response()
                    message_id = msg.id
                    channel_id = msg.channel.id
                except Exception as ex_msg:
                    logger.error(f"Failed to fetch original response message for watch session: {ex_msg}")
            
            # 5. SQLite DB에 세션 등록
            await add_watch_session(session_id, guild_id, user_id, channel_id, message_id)
            logger.info(f"Watch Together session created: {session_id} by User: {user_id}")

            log_cog = self.bot.get_cog("LogAgent")
            if log_cog and hasattr(log_cog, "send_watch_session_control"):
                try:
                    await log_cog.send_watch_session_control(
                        session_id=session_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        created_by=user_id,
                    )
                except Exception as log_error:
                    logger.warning(
                        "Watch Together 관리자 알림 전송 실패: %s",
                        log_error,
                    )
            
        except Exception as e:
            logger.error(f"Failed to create Watch Together session: {e}", exc_info=True)
            await interaction.response.send_message("❌ 시청 세션 방을 개설하는 동안 에러가 발생했습니다. 로그를 확인해 주세요.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WatchAgentCog(bot))
