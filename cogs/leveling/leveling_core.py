import os
import time
import logging
import asyncio
import sqlite3
import math
from typing import Optional, Dict

import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger("LevelingCog")
DB_PATH = "data/bot_database.db"
SUMMARY_CHANNEL_ID = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))

# Role prefixes for automatic assignment
ROLE_PREFIXES = ["Lv.", "lv.", "LV."]

# --- DB Helper Functions ---
async def get_user_data(user_id: int):
    def _get():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
    return await asyncio.to_thread(_get)

async def update_user_xp(user_id: int, guild_id: int, xp_added: int, vc_sec_added: int = 0, new_level: int = None):
    def _update():
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
            if new_level is not None:
                c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ?, level = ? WHERE user_id = ?",
                          (xp_added, vc_sec_added, new_level, user_id))
            else:
                c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ? WHERE user_id = ?",
                          (xp_added, vc_sec_added, user_id))
            conn.commit()
    await asyncio.to_thread(_update)

async def get_top_users(guild_id: int, limit: int = 10):
    def _get():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            # In case the bot is in multiple guilds, we filter by guild_id
            c.execute("SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT ?", (guild_id, limit))
            return [dict(row) for row in c.fetchall()]
    return await asyncio.to_thread(_get)

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
        
        # 특정 채널(요약 채널)에서만 경험치 작동
        if SUMMARY_CHANNEL_ID and message.channel.id == SUMMARY_CHANNEL_ID:
            xp_to_add = calculate_jamo_length(message.content)
            if xp_to_add > 0:
                user_data = await get_user_data(message.author.id)
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
                
                # 1분에 0.1 XP (10분당 1 XP) 지급으로 대폭 하향 조정
                # int형 변수이므로 10분 단위로 절사하여 지급합니다.
                duration_10min = duration_sec // 600
                xp_to_add = duration_10min * 1
                
                if xp_to_add > 0:
                    user_data = await get_user_data(member.id)
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
        user_data = await get_user_data(interaction.user.id)
        
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
        
        if not top_users:
            await interaction.followup.send("아직 랭킹 정보가 없습니다.")
            return
            
        embed = discord.Embed(title=f"🏆 {interaction.guild.name} 랭킹 TOP 10", color=0xF1C40F)
        description = ""
        
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
