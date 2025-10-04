# -*- coding: utf-8 -*-
import os
import logging
import json
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
import random
import string

import discord
from discord.ext import commands, tasks
from discord import ui, app_commands

# --- 로거 및 상수 설정 ---
logger = logging.getLogger(__name__)
MINING_CHANNEL_ID = int(os.getenv("MINING_CHANNEL_ID", "0"))
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL") 
# 데이터 파일 경로 수정
DATA_FILE = "data/mining_data.json"
BOT_EMBED_COLOR = 0xFFA500
WAITING_COLOR = 0x99AAB5
SUCCESS_COLOR = 0x00FF00

MINING_DIFFICULTY_PREFIX = os.getenv("MINING_DIFFICULTY_PREFIX", "000")
MINING_REWARD_AMOUNT = int(os.getenv("MINING_REWARD_AMOUNT", "10"))

# --- 데이터 관리 ---
data_lock = asyncio.Lock()

async def load_mining_data():
    async with data_lock:
        if not os.path.exists(DATA_FILE):
            return {}
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"'{DATA_FILE}' 파일 로드 실패: {e}")
            return {}

async def save_mining_data(data):
    async with data_lock:
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
        except IOError as e:
            logger.error(f"'{DATA_FILE}' 파일 저장 실패: {e}")

# --- UI 컴포넌트 ---
class SubmitNonceModal(ui.Modal, title="✅ 정답 제출"):
    nonce_input = ui.TextInput(label="찾아낸 Nonce 값을 입력하세요", placeholder="예: 1234567", required=True)

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.verify_submission(interaction, self.nonce_input.value)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"SubmitNonceModal에서 오류 발생: {error}", exc_info=True)
        await interaction.response.send_message("처리 중 오류가 발생했습니다.", ephemeral=True)

# --- 핵심 Cog 클래스 ---
class MiningAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_rounds = {}
        self.control_panels = {}
        self.last_round_info = {}
        self.success_messages = {}
        self.difficulty = {"prefix": MINING_DIFFICULTY_PREFIX, "reward": MINING_REWARD_AMOUNT}

    @commands.Cog.listener()
    async def on_ready(self):
        if MINING_CHANNEL_ID == 0 or not WEB_CLIENT_URL:
            logger.warning("[Mining] MINING_CHANNEL_ID 또는 WEB_CLIENT_URL이 설정되지 않아 기능이 비활성화됩니다.")
            return
            
        for guild in self.bot.guilds:
            await self.setup_control_panel(guild)
        
        self.update_panel_loop.start()
        logger.info("[Mining] 모든 서버의 채굴 제어판 설정 및 업데이트 루프 시작 완료.")

    def cog_unload(self):
        self.update_panel_loop.cancel()

    @tasks.loop(minutes=1)
    async def update_panel_loop(self):
        """1분마다 활성 라운드가 있는 모든 제어판을 업데이트합니다."""
        for guild_id_str, round_info in self.active_rounds.items():
            if round_info.get("is_active"):
                try:
                    guild = self.bot.get_guild(int(guild_id_str))
                    if guild:
                        await self.update_control_panel(guild)
                except Exception as e:
                    logger.error(f"제어판 자동 업데이트 중 오류 발생 (Guild ID: {guild_id_str}): {e}")

    async def setup_control_panel(self, guild: discord.Guild):
        channel = guild.get_channel(MINING_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel): return

        async for message in channel.history(limit=100):
            if message.author == self.bot.user and message.embeds:
                embed = message.embeds[0]
                if embed.footer and embed.footer.text and "채굴 제어판" in embed.footer.text:
                    self.control_panels[str(guild.id)] = message
                    logger.info(f"[{guild.name}] 기존 채굴 제어판 메시지를 찾았습니다.")
                    await self.update_control_panel(guild)
                    return

        embed, view = self.create_panel_components(guild)
        message = await channel.send(embed=embed, view=view)
        self.control_panels[str(guild.id)] = message
        logger.info(f"[{guild.name}] 새로운 채굴 제어판 메시지를 생성했습니다.")

    def _create_dynamic_view(self, guild: discord.Guild) -> ui.View:
        guild_id_str = str(guild.id)
        is_active = self.active_rounds.get(guild_id_str, {}).get("is_active", False)
        
        view = ui.View(timeout=None)

        start_button = ui.Button(label="💎 새 블록 채굴 시작", style=discord.ButtonStyle.success, custom_id=f"start_mining_{guild.id}")
        async def start_callback(interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("관리자만 채굴을 시작할 수 있습니다.", ephemeral=True)
                return
            await interaction.response.defer()
            await self.start_new_round(interaction)
        start_button.callback = start_callback
        view.add_item(start_button)

        if is_active:
            round_info = self.active_rounds[guild_id_str]
            mining_url = f"{WEB_CLIENT_URL}?seed={round_info['seed']}&target={round_info['target_prefix']}"
            view.add_item(ui.Button(label="⛏️ 웹에서 채굴 시작", style=discord.ButtonStyle.link, url=mining_url))

        leaderboard_button = ui.Button(label="🏆 리더보드", style=discord.ButtonStyle.blurple, custom_id=f"leaderboard_{guild.id}")
        leaderboard_button.callback = self.show_leaderboard
        view.add_item(leaderboard_button)

        submit_button = ui.Button(label="✅ 정답 제출", style=discord.ButtonStyle.primary, custom_id=f"submit_nonce_{guild.id}", disabled=not is_active)
        async def submit_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(SubmitNonceModal(self))
        submit_button.callback = submit_callback
        view.add_item(submit_button)
        
        return view

    def create_panel_components(self, guild: discord.Guild) -> tuple[discord.Embed, ui.View]:
        guild_id_str = str(guild.id)
        round_info = self.active_rounds.get(guild_id_str)

        if round_info and round_info.get("is_active"):
            embed = discord.Embed(title="💎 채굴 진행 중", description="아래 정보를 확인하고 웹 클라이언트에서 채굴을 시작하세요!", color=BOT_EMBED_COLOR)
            embed.add_field(name="시드 (Seed)", value=f"```{round_info['seed']}```", inline=False)
            embed.add_field(name="목표 (Target)", value=f"해시가 `{round_info['target_prefix']}`(으)로 시작", inline=False)
            
            start_time = round_info['start_time']
            elapsed = datetime.now(timezone.utc) - start_time
            elapsed_str = str(timedelta(seconds=int(elapsed.total_seconds())))
            embed.add_field(name="경과 시간", value=elapsed_str, inline=True)
            embed.add_field(name="난이도", value=f"'{round_info['target_prefix']}'", inline=True)

        else:
            embed = discord.Embed(title="⛏️ 채굴 대기 중", description="관리자가 새로운 블록 채굴을 시작할 때까지 대기해주세요.", color=WAITING_COLOR)
            last_info = self.last_round_info.get(guild_id_str)
            if last_info:
                winner = guild.get_member(last_info['winner_id'])
                winner_name = winner.mention if winner else "알 수 없는 유저"
                embed.add_field(name="최근 우승자", value=winner_name, inline=True)
                embed.add_field(name="소요 시간", value=last_info['elapsed_str'], inline=True)

        embed.set_footer(text="채굴 제어판")
        view = self._create_dynamic_view(guild)
        return embed, view

    async def update_control_panel(self, guild: discord.Guild):
        panel_message = self.control_panels.get(str(guild.id))
        if not panel_message: return

        try:
            embed, view = self.create_panel_components(guild)
            await panel_message.edit(embed=embed, view=view)
        except discord.NotFound:
            logger.warning(f"[{guild.name}] 제어판 메시지를 찾을 수 없어 새로 생성합니다.")
            await self.setup_control_panel(guild)
        except Exception as e:
            logger.error(f"[{guild.name}] 제어판 업데이트 중 오류 발생: {e}")

    def generate_seed(self, guild_id: int) -> str:
        timestamp = int(datetime.now(timezone.utc).timestamp())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"dsc-mine-{guild_id}-{timestamp}-{random_str}"

    async def start_new_round(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)

        if guild_id_str in self.success_messages:
            try:
                await self.success_messages[guild_id_str].delete()
            except (discord.NotFound, discord.Forbidden):
                pass 
            finally:
                del self.success_messages[guild_id_str]
        
        if self.active_rounds.get(guild_id_str, {}).get("is_active"):
            await interaction.followup.send("이미 채굴 라운드가 진행 중입니다.", ephemeral=True)
            return
        
        seed = self.generate_seed(interaction.guild.id)
        target_prefix = self.difficulty['prefix']
        self.active_rounds[guild_id_str] = {
            "is_active": True, "seed": seed, "target_prefix": target_prefix,
            "start_time": datetime.now(timezone.utc), "winner": None
        }
        logger.info(f"[{interaction.guild.name}] 새 채굴 라운드 시작. Seed: {seed}")
        
        await self.update_control_panel(interaction.guild)
        await interaction.followup.send("✅ 새로운 채굴 라운드를 시작했습니다.", ephemeral=True)


    async def verify_submission(self, interaction: discord.Interaction, nonce_str: str):
        await interaction.response.defer(ephemeral=True)
        guild_id_str = str(interaction.guild.id)
        round_info = self.active_rounds.get(guild_id_str)

        if not round_info or not round_info.get("is_active"):
            await interaction.followup.send("이미 종료된 라운드입니다.", ephemeral=True)
            return

        try:
            nonce = int(nonce_str)
        except ValueError:
            await interaction.followup.send("Nonce 값은 반드시 숫자여야 합니다.", ephemeral=True)
            return

        data_to_hash = round_info["seed"] + str(nonce)
        hash_result = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

        if hash_result.startswith(round_info["target_prefix"]):
            await self.end_round(interaction, hash_result, nonce)
            await interaction.followup.send("🎉 정답입니다! 블록 채굴에 성공했습니다!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ 오답입니다. (결과: `{hash_result[:10]}...`)", ephemeral=True)

    async def end_round(self, interaction: discord.Interaction, final_hash: str, nonce: int):
        guild = interaction.guild
        winner = interaction.user
        guild_id_str = str(guild.id)
        round_info = self.active_rounds.get(guild_id_str)
        if not round_info or not round_info["is_active"]: return
        
        round_info["is_active"] = False
        round_info["winner"] = winner.id
        
        elapsed = datetime.now(timezone.utc) - round_info["start_time"]
        elapsed_str = str(timedelta(seconds=int(elapsed.total_seconds())))
        reward = self.difficulty["reward"]

        logger.info(f"[{guild.name}] 채굴 성공! 승자: {winner.display_name}, 소요 시간: {elapsed.total_seconds():.2f}초")

        self.last_round_info[guild_id_str] = {
            "winner_id": winner.id,
            "elapsed_str": elapsed_str
        }

        data = await load_mining_data()
        guild_data = data.setdefault(guild_id_str, {"leaderboard": {}, "total_blocks_mined": 0})
        leaderboard = guild_data.setdefault("leaderboard", {})
        winner_id_str = str(winner.id)
        leaderboard[winner_id_str] = leaderboard.get(winner_id_str, 0) + reward
        guild_data["total_blocks_mined"] = guild_data.get("total_blocks_mined", 0) + 1
        await save_mining_data(data)

        channel = guild.get_channel(MINING_CHANNEL_ID)
        if channel:
            embed = discord.Embed(title="🎉 블록 채굴 성공!", description=f"**{winner.mention}** 님이 새로운 블록을 발견했습니다!", color=SUCCESS_COLOR)
            embed.add_field(name="소요 시간", value=elapsed_str, inline=True)
            embed.add_field(name="획득 포인트", value=f"**{reward} 포인트**", inline=True)
            embed.add_field(name="정답 Nonce", value=f"`{nonce}`", inline=True)
            embed.add_field(name="성공 해시", value=f"`{final_hash}`", inline=False)
            embed.set_thumbnail(url=winner.display_avatar.url)
            success_msg = await channel.send(embed=embed)
            self.success_messages[guild_id_str] = success_msg
        
        await self.update_control_panel(guild)
    
    async def show_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id_str = str(interaction.guild.id)
        data = await load_mining_data()
        guild_data = data.get(guild_id_str, {})
        leaderboard = guild_data.get("leaderboard", {})
        total_blocks = guild_data.get("total_blocks_mined", 0)

        if not leaderboard:
            await interaction.followup.send("아직 채굴 기록이 없습니다.", ephemeral=True)
            return

        sorted_board = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)
        embed = discord.Embed(title="🏆 채굴 리더보드", color=BOT_EMBED_COLOR)
        
        description = []
        rank_emojis = ["🥇", "🥈", "🥉"]
        for i, (user_id, score) in enumerate(sorted_board[:10]):
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except (discord.NotFound, ValueError):
                user_name = f"ID: {user_id}"
            rank = rank_emojis[i] if i < 3 else f"`#{i+1}`"
            description.append(f"{rank} **{user_name}** - {score} 포인트")

        embed.description = "\n".join(description)
        embed.set_footer(text=f"이 서버에서 총 {total_blocks}개의 블록이 채굴되었습니다.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    if MINING_CHANNEL_ID == 0 or not WEB_CLIENT_URL: return
    await bot.add_cog(MiningAgentCog(bot))
