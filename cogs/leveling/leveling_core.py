import os
import time
import logging
import asyncio
import math
import re
from typing import Optional, Dict

import discord
from discord.ext import commands
from discord import app_commands

from database_manager import db_lock, get_user_data, update_user_xp, get_top_users

logger: logging.Logger = logging.getLogger("LevelingCog")
SUMMARY_CHANNEL_ID: int = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))

# --- Helper Functions ---
def calculate_jamo_length(text: str) -> int:
    length: int = 0
    for char in text:
        # 한글 음절 (가-힣)
        if 0xAC00 <= ord(char) <= 0xD7A3:
            char_code: int = ord(char) - 0xAC00
            jong: int = char_code % 28
            # 종성이 있으면 3타, 없으면 2타
            length += 3 if jong > 0 else 2
        elif char.strip(): # 공백 제외 다른 문자들 (숫자, 영어 등)
            length += 1
    return length

def get_required_xp(level: int) -> int:
    # 레벨업 요구량 곡선: 100 * (level ^ 1.5)
    return int(100 * (level ** 1.5))

class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.voice_sessions: Dict[int, dict] = {}  # user_id -> {"time": join_time_seconds, "guild_id": guild_id}

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """봇 기동 시, 이미 음성 채널에 존재하는 유저들을 스캔하여 세션을 복구합니다."""
        try:
            recovered: int = 0
            for guild in self.bot.guilds:
                for vc in guild.voice_channels:
                    for member in vc.members:
                        if not member.bot and member.id not in self.voice_sessions:
                            self.voice_sessions[member.id] = {"time": time.time(), "guild_id": guild.id}
                            recovered += 1
            if recovered > 0:
                logger.info(f"[Leveling] 봇 재기동: {recovered}명의 음성 세션을 복구하여 추적을 시작합니다.")
        except Exception as e:
            logger.error(f"[Leveling] on_ready 세션 복구 중 오류 발생: {e}", exc_info=True)

    async def cog_unload(self) -> None:
        """봇 종료 또는 언로드 시, 남아있는 음성 세션을 일괄 정산하여 기동 중 증발을 방지합니다."""
        try:
            logger.info("[Leveling] 봇 종료 감지: 남아있는 음성 세션을 DB에 강제 정산합니다.")
            for member_id, session_data in list(self.voice_sessions.items()):
                join_time: float = session_data["time"]
                guild_id: int = session_data["guild_id"]
                duration_sec: int = int(time.time() - join_time)
                
                if duration_sec >= 600:
                    duration_10min: int = duration_sec // 600
                    xp_to_add: int = duration_10min * 1
                    
                    user_data: Optional[Dict[str, any]] = await get_user_data(member_id, guild_id)
                    current_level: int = user_data["level"] if user_data else 1
                    current_xp: int = user_data["xp"] if user_data else 0
                    
                    total_xp: int = current_xp + xp_to_add
                    new_level: int = current_level
                    
                    # 레벨업 스케일 계산 (기동 중이므로 역할 부여는 생략, 레벨만 갱신)
                    while total_xp >= get_required_xp(new_level):
                        new_level += 1
                    
                    final_new_level: Optional[int] = new_level if new_level > current_level else None
                    await update_user_xp(member_id, guild_id, xp_added=xp_to_add, vc_sec_added=duration_sec, new_level=final_new_level)
                
                # 세션 삭제
                self.voice_sessions.pop(member_id, None)
            logger.info("[Leveling] 음성 세션 정산 및 안전 종료 완료.")
        except Exception as e:
            logger.error(f"[Leveling] cog_unload 정산 중 오류 발생: {e}", exc_info=True)




    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        try:
            if message.author.bot or not message.guild:
                return
            
            # 모든 채널에서 경험치 작동하도록 변경
            xp_to_add: int = calculate_jamo_length(message.content)
            if xp_to_add > 0:
                user_data: Optional[Dict[str, any]] = await get_user_data(message.author.id, message.guild.id)
                current_level: int = user_data["level"] if user_data else 1
                current_xp: int = user_data["xp"] if user_data else 0
                    
                total_xp: int = current_xp + xp_to_add
                new_level: int = current_level
                while total_xp >= get_required_xp(new_level):
                    new_level += 1
                
                final_new_level: Optional[int] = new_level if new_level > current_level else None
                
                await update_user_xp(message.author.id, message.guild.id, xp_added=xp_to_add, new_level=final_new_level)
        except Exception as e:
            logger.error(f"[Leveling] on_message 처리 중 오류 발생: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        try:
            if member.bot:
                return

            # 방에 들어옴
            if not before.channel and after.channel:
                self.voice_sessions[member.id] = {"time": time.time(), "guild_id": member.guild.id}
            
            # 방에서 나감
            elif before.channel and not after.channel:
                if member.id in self.voice_sessions:
                    session_data: dict = self.voice_sessions.pop(member.id)
                    join_time: float = session_data["time"]
                    duration_sec: int = int(time.time() - join_time)
                    
                    # 10분을 채우지 않으면 경험치 스킵 (악용 방지)
                    if duration_sec < 600:
                        return

                    # 10분당 1 XP 지급
                    duration_10min: int = duration_sec // 600
                    xp_to_add: int = duration_10min * 1
                    
                    if xp_to_add > 0:
                        user_data: Optional[Dict[str, any]] = await get_user_data(member.id, member.guild.id)
                        current_level: int = user_data["level"] if user_data else 1
                        current_xp: int = user_data["xp"] if user_data else 0
                        
                        total_xp: int = current_xp + xp_to_add
                        new_level: int = current_level
                        while total_xp >= get_required_xp(new_level):
                            new_level += 1
                        
                        final_new_level: Optional[int] = new_level if new_level > current_level else None
                        
                        await update_user_xp(member.id, member.guild.id, xp_added=xp_to_add, vc_sec_added=duration_sec, new_level=final_new_level)
        except Exception as e:
            logger.error(f"[Leveling] on_voice_state_update 처리 중 오류 발생: {e}", exc_info=True)

    # --- Commands ---
    @app_commands.command(name="내정보", description="나의 현재 레벨과 경험치 진행도를 확인합니다.")
    async def profile(self, interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer(ephemeral=True)
            if not interaction.guild:
                await interaction.followup.send("이 명령어는 서버 내에서만 사용할 수 있습니다.")
                return

            user_data: Optional[Dict[str, any]] = await get_user_data(interaction.user.id, interaction.guild.id)
            
            level: int = user_data["level"] if user_data else 1
            xp: int = user_data["xp"] if user_data else 0
            vc_seconds: int = user_data["total_vc_seconds"] if user_data else 0
            
            curr_req_xp: int = get_required_xp(level - 1) if level > 1 else 0
            next_req_xp: int = get_required_xp(level)
            
            # 진행도 바 계산 (10칸)
            progress_total: int = next_req_xp - curr_req_xp
            progress_current: int = xp - curr_req_xp
            ratio: float = progress_current / progress_total if progress_total > 0 else 0.0
            filled_blocks: int = int(ratio * 10)
            empty_blocks: int = 10 - filled_blocks
            progress_bar: str = "🟩" * filled_blocks + "⬜" * empty_blocks
            
            vc_hours: int = vc_seconds // 3600
            vc_minutes: int = (vc_seconds % 3600) // 60
            
            embed: discord.Embed = discord.Embed(title=f"👤 {interaction.user.display_name}님의 정보", color=0x3498DB)
            embed.add_field(name="현재 레벨", value=f"**Lv.{level}**", inline=True)
            embed.add_field(name="누적 경험치", value=f"{xp:,} XP", inline=True)
            embed.add_field(name="진행도", value=f"{progress_bar} ({ratio*100:.1f}%)", inline=False)
            embed.add_field(name="다음 레벨까지", value=f"{(next_req_xp - xp):,} XP 남음", inline=False)
            embed.add_field(name="음성 채널 누적 체류", value=f"{vc_hours}시간 {vc_minutes}분", inline=False)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"[Leveling] profile 명령어 실행 중 오류 발생: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("명령어 처리 중 오류가 발생했습니다.", ephemeral=True)
            else:
                await interaction.followup.send("명령어 처리 중 오류가 발생했습니다.", ephemeral=True)


    @app_commands.command(name="랭킹", description="서버 내 경험치 랭킹 TOP 10을 확인합니다.")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer(ephemeral=False)
            if not interaction.guild:
                await interaction.followup.send("이 명령어는 서버 내에서만 사용할 수 있습니다.")
                return

            top_users: list[Dict[str, any]] = await get_top_users(interaction.guild.id)
                
            embed: discord.Embed = discord.Embed(title=f"🏆 {interaction.guild.name} 랭킹 TOP 10", color=0xF1C40F)
            description: str = ""
            
            if not top_users:
                description = "이 서버에 경험치가 기록된 유저가 없습니다."
            else:
                for idx, row in enumerate(top_users):
                    member: Optional[discord.Member] = interaction.guild.get_member(row["user_id"])
                    name: str = member.display_name if member else f"알 수 없는 유저 ({row['user_id']})"
                    
                    medal: str = "🏅"
                    if idx == 0: medal = "🥇"
                    elif idx == 1: medal = "🥈"
                    elif idx == 2: medal = "🥉"
                    
                    description += f"{medal} **{idx+1}위** | {name} - **Lv.{row['level']}** ({row['xp']:,} XP)\n\n"
            
            embed.description = description
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"[Leveling] leaderboard 명령어 실행 중 오류 발생: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("랭킹 정보를 불러오는 중 오류가 발생했습니다.", ephemeral=True)
            else:
                await interaction.followup.send("랭킹 정보를 불러오는 중 오류가 발생했습니다.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))

