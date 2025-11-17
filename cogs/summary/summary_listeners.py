import os
import logging
from datetime import datetime, timedelta, timezone
from collections import deque

import discord
from discord.ext import commands, tasks
from discord import ui

# 동일 디렉토리 내의 summarizer_agent 모듈을 명시적으로 참조하도록 변경
# OpenAI 관련 임포트 변경
from .summarizer_agent import (
    initialize_gemini_client,  # 변경
    gemini_summarize,          # 변경
    parse_summary_to_structured_data
)

# --- 로거 및 상수 설정 ---
logger = logging.getLogger(__name__)
BOT_EMBED_COLOR = 0x5865F2

# --- 환경 변수 ---
SUMMARY_CHANNEL_ID = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))
LOG_RETENTION_HOURS = float(os.getenv("LOG_RETENTION_HOURS", 24.0))
INITIAL_LOAD_HOURS = float(os.getenv("INITIAL_LOAD_HOURS", 3.0))
MAX_LOG_COUNT = int(os.getenv("MAX_LOG_COUNT", 300))
MAX_HISTORY_FETCH = int(os.getenv("MAX_HISTORY_FETCH", 200))
PRUNE_INTERVAL_MINUTES = int(os.getenv("PRUNE_INTERVAL_MINUTES", 10))


# --- UI 클래스 ---
class AdvancedSummaryModal(ui.Modal, title='고급 요약 옵션'):
    def __init__(self, hours: float, cog):
        super().__init__(timeout=300)
        self.hours = hours
        self.cog = cog
        self.keywords = ui.TextInput(label="포함할 키워드 (쉼표로 구분)", placeholder="예: AI, 기획, 업데이트", required=False, style=discord.TextStyle.short)
        self.users = ui.TextInput(label="특정 사용자 이름 (쉼표로 구분)", placeholder="예: DrBear, Custodian", required=False, style=discord.TextStyle.short)
        self.prompt_req = ui.TextInput(label="추가 요청사항", placeholder="예: 조금 더 긍정적인 분위기로 요약해줘", required=False, style=discord.TextStyle.long)
        self.add_item(self.keywords)
        self.add_item(self.users)
        self.add_item(self.prompt_req)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)
        await self.cog.execute_summary(interaction, self.hours, keywords=self.keywords.value or None, users=self.users.value or None, extra_prompt=self.prompt_req.value or None)

class SummaryView(ui.View):
    def __init__(self, hours: float, topics: list, cog):
        super().__init__(timeout=3600)
        self.hours = hours
        self.topics = topics
        self.cog = cog
        if self.topics:
            options = [discord.SelectOption(label=f"주제 {i+1}: {topic.get('title', '제목 없음')[:100]}", value=str(i)) for i, topic in enumerate(self.topics)]
            self.topic_select = ui.Select(placeholder="자세히 볼 주제를 선택하세요...", options=options, min_values=1, max_values=1)
            self.topic_select.callback = self.on_topic_select
            self.add_item(self.topic_select)

    @ui.button(label="새로고침", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def on_refresh(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=False)
        await self.cog.execute_summary(interaction, self.hours)

    @ui.button(label="고급 요약", style=discord.ButtonStyle.primary, emoji="✨", row=1)
    async def on_advanced(self, interaction: discord.Interaction, button: ui.Button):
        modal = AdvancedSummaryModal(self.hours, self.cog)
        await interaction.response.send_modal(modal)

    async def on_topic_select(self, interaction: discord.Interaction):
        topic_index = int(interaction.data['values'][0])
        selected_topic = self.topics[topic_index]
        embed = discord.Embed(title=f"주제 {topic_index+1}: {selected_topic.get('title', '제목 없음')}", color=BOT_EMBED_COLOR)
        embed.add_field(name="논의 시간대", value=selected_topic.get('time', 'N/A'), inline=False)
        embed.add_field(name="주요 참여자", value=selected_topic.get('participants', 'N/A'), inline=False)
        embed.add_field(name="핵심 키워드", value=selected_topic.get('keywords', 'N/A'), inline=False)
        summary_value = (f"**- 핵심 요지:** {selected_topic.get('main_point', '정보 없음')}\n"
                         f"**- 배경/맥락:** {selected_topic.get('context', '정보 없음')}\n"
                         f"**- 세부 내용:** {selected_topic.get('details', '정보 없음')}")
        embed.add_field(name="상세 요약", value=summary_value, inline=False)
        embed.set_footer(text=f"요청자: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 핵심 Cog 클래스 ---
class SummaryListenersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_log = deque(maxlen=MAX_LOG_COUNT)
        
        # OPENAI_API_KEY -> GOOGLE_API_KEY로 변경
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        if GOOGLE_API_KEY and SUMMARY_CHANNEL_ID != 0:
            initialize_gemini_client(GOOGLE_API_KEY) # 변경
            # initialize_tiktoken_encoder() 제거
            self.prune_old_messages.start()
            self.initial_load_done = False
        else:
            logger.warning("[Summary] GOOGLE_API_KEY 또는 채널 ID가 설정되지 않아 요약 기능이 비활성화됩니다.")
            self.initial_load_done = True

    async def cog_load(self):
        logger.info("[SummaryListeners] Cog 로드 완료.")
        
    def cog_unload(self):
        if self.prune_old_messages.is_running():
            self.prune_old_messages.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.initial_load_done:
            await self.load_recent_messages()
            self.initial_load_done = True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.initial_load_done or message.author.bot: return
        if message.channel.id == SUMMARY_CHANNEL_ID and message.content:
            log_tuple = (message.created_at.replace(tzinfo=timezone.utc), message.guild.id, message.author.id, message.author.display_name, message.content)
            self.message_log.append(log_tuple)

    async def load_recent_messages(self):
        try:
            channel = self.bot.get_channel(SUMMARY_CHANNEL_ID)
            if not isinstance(channel, discord.TextChannel):
                logger.error(f"초기 메시지 로드 실패: 채널 ID '{SUMMARY_CHANNEL_ID}'를 찾을 수 없거나 텍스트 채널이 아닙니다.")
                return
            
            now_utc = datetime.now(timezone.utc)
            threshold_time = now_utc - timedelta(hours=INITIAL_LOAD_HOURS)
            messages_loaded_count = 0
            async for msg in channel.history(limit=MAX_HISTORY_FETCH, after=threshold_time, oldest_first=True):
                if not msg.author.bot and msg.content:
                    self.message_log.append((msg.created_at.replace(tzinfo=timezone.utc), msg.guild.id, msg.author.id, msg.author.display_name, msg.content))
                    messages_loaded_count += 1
            logger.info(f"[로딩] 초기 메시지 로드 완료. 지난 {INITIAL_LOAD_HOURS}시간 동안 채널({SUMMARY_CHANNEL_ID})에서 {messages_loaded_count}개 메시지 적재됨.")
        except discord.Forbidden:
            logger.error(f"초기 메시지 로드 오류: 채널 {SUMMARY_CHANNEL_ID}에 접근 권한이 없습니다.")
        except Exception as e:
            logger.error(f"초기 메시지 로드 중 예기치 않은 오류 발생: {e}", exc_info=True)
    
    @tasks.loop(minutes=PRUNE_INTERVAL_MINUTES)
    async def prune_old_messages(self):
        if not self.message_log: return
        now_utc = datetime.now(timezone.utc)
        threshold_time = now_utc - timedelta(hours=LOG_RETENTION_HOURS)
        pruned_count = 0
        while self.message_log and self.message_log[0][0] < threshold_time:
            self.message_log.popleft()
            pruned_count += 1
        if pruned_count > 0:
            logger.info(f"오래된 메시지 {pruned_count}개 삭제됨. (현재 보유 {len(self.message_log)}개)")
        
    async def execute_summary(self, interaction: discord.Interaction, hours: float, **kwargs):
        target_channel = self.bot.get_channel(SUMMARY_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send("오류: 요약 대상 채널을 찾을 수 없습니다.", ephemeral=True)
            return

        try:
            now_utc = datetime.now(timezone.utc)
            threshold_time = now_utc - timedelta(hours=hours)
            guild_id = interaction.guild.id
            
            # 필터링 로직 추가 (kwargs에서 키워드와 사용자 필터링)
            keywords = [k.strip().lower() for k in kwargs.get('keywords', '').split(',') if k.strip()] if kwargs.get('keywords') else []
            users = [u.strip().lower() for u in kwargs.get('users', '').split(',') if u.strip()] if kwargs.get('users') else []

            logs_to_process = [log for log in self.message_log if log[0] >= threshold_time and log[1] == guild_id]

            if keywords:
                logs_to_process = [log for log in logs_to_process if any(kw in log[4].lower() for kw in keywords)]
            
            if users:
                logs_to_process = [log for log in logs_to_process if log[3].lower() in users]

            if not logs_to_process:
                await interaction.followup.send(f"지난 {hours}시간 동안 #{target_channel.name} 채널에서 요약할 메시지가 없습니다.", ephemeral=True)
                return

            # gpt_summarize -> gemini_summarize로 변경
            summary_text, input_tokens = await gemini_summarize(logs_to_process, **kwargs)
            structured_summary = parse_summary_to_structured_data(summary_text)

            if not structured_summary or not structured_summary.get('topics'):
                await interaction.followup.send(f"요약 내용을 구조화하는 데 실패했습니다. 원본 텍스트:\n```\n{summary_text[:1800]}\n```")
                return

            embed = discord.Embed(title=f"최근 {hours}시간 대화 요약", description=f"**📈 전체 대화 개요:**\n{structured_summary.get('overall_summary', '내용 없음')}", color=BOT_EMBED_COLOR, timestamp=datetime.now(timezone.utc))
            for i, topic in enumerate(structured_summary['topics']):
                embed.add_field(name=f"📌 주제 {i+1}: {topic.get('title', '제목 없음')}", value=f"**참여자:** {topic.get('participants', 'N/A')}\n**키워드:** {topic.get('keywords', 'N/A')}", inline=False)
            
            token_info = f"요청자: {interaction.user.display_name}"
            if input_tokens:
                token_info += f" | 프롬프트 토큰: {input_tokens:,}"
            embed.set_footer(text=token_info)
            
            view = SummaryView(hours, structured_summary['topics'], self)
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"요약 실행 중 오류 발생: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send("요약 생성 중 치명적인 오류가 발생했습니다. 로그를 확인해주세요.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryListenersCog(bot))