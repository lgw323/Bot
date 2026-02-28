import os
import time
import logging
import asyncio
import math
from typing import Optional, Dict
from database_manager import db_lock, get_user_data, update_user_xp, get_top_users

import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger("LevelingCog")
DB_PATH = "data/bot_database.db"
SUMMARY_CHANNEL_ID = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))

# Role prefixes for automatic assignment
ROLE_PREFIXES = ["Lv.", "lv.", "LV."]

# --- DB Helper Functions are imported from database_manager.py ---

def calculate_jamo_length(text: str) -> int:
    length = 0
    for char in text:
        # 한글 음절 (가-힣)
        if 0xAC00 <= ord(char) <= 0xD7A3:
            char_code = ord(char) - 0xAC00
            jong = char_code % 28
            # 종성이 있으면 3타, 없으면 2타
            length += 3 if jong > 0 else 2
        elif char.strip(): # 공백 제외 다른 문자들 (숫자, 영어 등)
            length += 1
    return length

def get_required_xp(level: int) -> int:
    # 레벨업 요구량 곡선: 100 * (level ^ 1.5)
    return int(100 * (level ** 1.5))


class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_sessions: Dict[int, float] = {}  # user_id -> join_time_seconds

    @commands.Cog.listener()
    async def on_ready(self):
        """봇 기동 시, 이미 음성 채널에 존재하는 유저들을 스캔하여 세션을 복구합니다."""
        recovered = 0
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot and member.id not in self.voice_sessions:
                        self.voice_sessions[member.id] = time.time()
                        recovered += 1
        if recovered > 0:
            logger.info(f"[Leveling] 봇 재기동: {recovered}명의 음성 세션을 복구하여 추적을 시작합니다.")

    async def cog_unload(self):
        """봇 종료 또는 언로드 시, 남아있는 음성 세션을 일괄 정산하여 기동 중 증발을 방지합니다."""
        logger.info("[Leveling] 봇 종료 감지: 남아있는 음성 세션을 DB에 강제 정산합니다.")
        for member_id, join_time in list(self.voice_sessions.items()):
            duration_sec = int(time.time() - join_time)
            if duration_sec >= 600:
                duration_10min = duration_sec // 600
                xp_to_add = duration_10min * 1
                
                # 봇 재기동 시 세션 복구된 유저는 원래 무슨 채널(서버)에 있었는지 알 수 없어 guild_id를 0으로 조회합니다.
                # 이는 최신 방식에서는 부정확할 수 있으나, 임시 방편입니다.
                user_data = await get_user_data(member_id, 0)
                current_level = user_data["level"] if user_data else 1
                current_xp = user_data["xp"] if user_data else 0
                
                total_xp = current_xp + xp_to_add
                new_level = current_level
                
                # 레벨업 스케일 계산 (기동 중이므로 역할 부여는 생략, 레벨만 갱신)
                while total_xp >= get_required_xp(new_level):
                    new_level += 1
                
                final_new_level = new_level if new_level > current_level else None
                await update_user_xp(member_id, 0, xp_added=xp_to_add, vc_sec_added=duration_sec, new_level=final_new_level)
            
            # 세션 삭제
            self.voice_sessions.pop(member_id, None)
        logger.info("[Leveling] 음성 세션 정산 및 안전 종료 완료.")

    async def check_level_up(self, member: discord.Member, current_level: int, total_xp: int) -> Optional[int]:
        """레벨업을 체크하고 관련된 역할 부여 처리를 수행합니다."""
        new_level = current_level
        while total_xp >= get_required_xp(new_level):
            new_level += 1
        
        if new_level > current_level:
            await self.assign_role_by_level(member, new_level)
            return new_level
        return None

    async def assign_role_by_level(self, member: discord.Member, level: int):
        """10레벨 단위 역할 등 규칙에 맞게 디스코드 역할을 부여합니다."""
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            logger.warning("봇에 '역할 관리' 권한이 없습니다. 역할 부여 알림을 패스합니다.")
            return

        # "Lv.10", "LV.20", "Lv 1" 등 서버 내 역할을 정규식으로 유연하게 스캔
        import re
        level_roles = []
        for role in guild.roles:
            match = re.search(r'(?i)^lv\.?\s*(\d+)', role.name)
            if match:
                role_lv = int(match.group(1))
                level_roles.append((role_lv, role))
        
        if not level_roles:
            logger.warning(f"서버에 'Lv.숫자' 형태의 역할이 단 하나도 없습니다! (현재 스캔된 역할 수: {len(guild.roles)})")


        # 내 레벨 이하의 역할 중 가장 높은 레벨의 역할 찾기
        target_role = None
        max_target_lv = -1
        for r_lv, r_obj in level_roles:
            if r_lv <= level and r_lv > max_target_lv:
                max_target_lv = r_lv
                target_role = r_obj

        # 이미 해당 역할을 가지고 있는지 확인
        if target_role and target_role not in member.roles:
            try:
                # 기존 레벨 역할 제거
                roles_to_remove = [r_obj for r_lv, r_obj in level_roles if r_obj in member.roles]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"레벨업({level})으로 인한 기존 역할 해제")
                # 새 역할 부여
                await member.add_roles(target_role, reason=f"레벨업 달성 (Lv.{level})")
                logger.info(f"{member.display_name}님에게 {target_role.name} 역할 지급 완료.")
            except discord.Forbidden:
                logger.error(f"권한 오류: {target_role.name} 역할을 지급할 수 없습니다. (역할 계층을 확인하세요)")
            except discord.HTTPException as e:
                logger.error(f"역할 지급 중 네트워크 오류: {e}")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        # 모든 채널에서 경험치 작동하도록 변경
        xp_to_add = calculate_jamo_length(message.content)
        if xp_to_add > 0:
            user_data = await get_user_data(message.author.id, message.guild.id)
            current_level = user_data["level"] if user_data else 1
            current_xp = user_data["xp"] if user_data else 0
                
            # 처음 채팅치는 유저(Lv.1 스타트)에게 Lv.1 관련 역할 부여
            if not user_data:
                await self.assign_role_by_level(message.author, 1)
            
            total_xp = current_xp + xp_to_add
            new_level = await self.check_level_up(message.author, current_level, total_xp)
            
            await update_user_xp(message.author.id, message.guild.id, xp_added=xp_to_add, new_level=new_level)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        # 방에 들어옴
        if not before.channel and after.channel:
            self.voice_sessions[member.id] = time.time()
        
        # 방에서 나감
        elif before.channel and not after.channel:
            if member.id in self.voice_sessions:
                join_time = self.voice_sessions.pop(member.id)
                duration_sec = int(time.time() - join_time)
                
                # 10분을 채우지 않으면 경험치 스킵 (악용 방지)
                if duration_sec < 600:
                    return

                # 10분당 1 XP 지급
                duration_10min = duration_sec // 600
                xp_to_add = duration_10min * 1
                
                if xp_to_add > 0:
                    user_data = await get_user_data(member.id, member.guild.id)
                    current_level = user_data["level"] if user_data else 1
                    current_xp = user_data["xp"] if user_data else 0
                    
                    # 처음 VC 이용하는 유저에게 Lv.1 관련 역할 부여
                    if not user_data:
                        await self.assign_role_by_level(member, 1)
                    
                    total_xp = current_xp + xp_to_add
                    new_level = await self.check_level_up(member, current_level, total_xp)
                    
                    await update_user_xp(member.id, member.guild.id, xp_added=xp_to_add, vc_sec_added=duration_sec, new_level=new_level)

    # --- Commands ---
    @app_commands.command(name="내정보", description="나의 현재 레벨과 경험치 진행도를 확인합니다.")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_data = await get_user_data(interaction.user.id, interaction.guild.id)
        
        level = user_data["level"] if user_data else 1
        xp = user_data["xp"] if user_data else 0
        vc_seconds = user_data["total_vc_seconds"] if user_data else 0
        
        # 만약 이미 Lv.N인데 역할을 못 받은 상태라면 여기서 강제 동기화(복구) 처리
        if isinstance(interaction.user, discord.Member):
            await self.assign_role_by_level(interaction.user, level)

        
        curr_req_xp = get_required_xp(level - 1) if level > 1 else 0
        next_req_xp = get_required_xp(level)
        
        # 진행도 바 계산 (10칸)
        progress_total = next_req_xp - curr_req_xp
        progress_current = xp - curr_req_xp
        ratio = progress_current / progress_total if progress_total > 0 else 0
        filled_blocks = int(ratio * 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "🟩" * filled_blocks + "⬜" * empty_blocks
        
        vc_hours = vc_seconds // 3600
        vc_minutes = (vc_seconds % 3600) // 60
        
        embed = discord.Embed(title=f"👤 {interaction.user.display_name}님의 정보", color=0x3498DB)
        embed.add_field(name="현재 레벨", value=f"**Lv.{level}**", inline=True)
        embed.add_field(name="누적 경험치", value=f"{xp:,} XP", inline=True)
        embed.add_field(name="진행도", value=f"{progress_bar} ({ratio*100:.1f}%)", inline=False)
        embed.add_field(name="다음 레벨까지", value=f"{(next_req_xp - xp):,} XP 남음", inline=False)
        embed.add_field(name="음성 채널 누적 체류", value=f"{vc_hours}시간 {vc_minutes}분", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="랭킹", description="서버 내 경험치 랭킹 TOP 10을 확인합니다.")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        top_users = await get_top_users(interaction.guild.id)
            
        embed = discord.Embed(title=f"🏆 {interaction.guild.name} 랭킹 TOP 10", color=0xF1C40F)
        description = ""
        
        if not top_users:
            description = "이 서버에 경험치가 기록된 유저가 없습니다."
        else:
            for idx, row in enumerate(top_users):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"알 수 없는 유저 ({row['user_id']})"
                
                medal = "🏅"
                if idx == 0: medal = "🥇"
                elif idx == 1: medal = "🥈"
                elif idx == 2: medal = "🥉"
                
                description += f"{medal} **{idx+1}위** | {name} - **Lv.{row['level']}** ({row['xp']:,} XP)\n\n"
        
        embed.description = description
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
