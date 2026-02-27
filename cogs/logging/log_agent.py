import os
import sys
import logging
import traceback
from logging.handlers import TimedRotatingFileHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# --- 설정값 ---
# 로그를 저장할 로컬 디렉토리 (data 폴더 내부에 logs 폴더 생성)
LOG_DIR = "data/logs"
# 디스코드 로그 채널 ID (로그 전용 서버의 채널 ID)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

class DiscordLogHandler(logging.Handler):
    """
    [커스텀 핸들러]
    ERROR 레벨 이상의 로그를 감지하면, 지정된 디스코드 채널로 비동기 전송합니다.
    """
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.target_channel = None

    def emit(self, record):
        """
        로깅 이벤트가 발생했을 때 호출되는 함수입니다.
        """
        # 1. 봇이 준비되지 않았거나, 로그 채널 ID가 설정되지 않았다면 무시
        if LOG_CHANNEL_ID == 0 or not self.bot.is_ready():
            return

        # 2. ERROR 이상의 심각한 문제만 필터링 (INFO, DEBUG는 무시)
        if record.levelno >= logging.ERROR:
            # logging 모듈은 동기(sync) 방식이지만, discord.py는 비동기(async)입니다.
            # 다른 스레드에서 들어올 수 있으므로 run_coroutine_threadsafe를 사용합니다.
            import asyncio
            asyncio.run_coroutine_threadsafe(self._async_emit(record), self.bot.loop)

    async def _async_emit(self, record):
        """
        실제로 디스코드 메시지를 전송하는 비동기 함수입니다.
        """
        try:
            # 채널 객체 캐싱 (최초 1회만 가져옴)
            if not self.target_channel:
                self.target_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            
            if self.target_channel:
                # 로그 메시지 포맷팅
                msg = self.format(record)
                
                # 디스코드 메시지 길이 제한(2000자) 처리
                if len(msg) > 1900:
                    msg = msg[:1900] + "...(내용이 너무 길어 생략됨)"
                
                # 가독성을 위한 Embed 생성
                embed = discord.Embed(
                    title="🚨 시스템 오류 발생 (System Error)", 
                    description=f"```log\n{msg}\n```",
                    color=0xFF0000  # 빨간색
                )
                
                # 발생 위치 정보 (모듈명, 라인 번호)
                footer_text = f"Module: {record.module} | Line: {record.lineno}"
                embed.set_footer(text=footer_text)
                
                await self.target_channel.send(embed=embed)

        except Exception:
            # 로깅 전송 중 에러가 발생하면 콘솔에만 출력하고 멈춤 (무한 루프 방지)
            print("[DiscordLogHandler] 로그 전송 실패", file=sys.stderr)

class LogAgentCog(commands.Cog, name="LogAgent"):
    """
    봇의 전역 로깅 시스템을 초기화하고 관리하는 Cog입니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._setup_logging()
        # 다른 Cog에서 self.bot.log.info(...) 형태로 사용할 수 있도록 주입
        self.bot.log = logging.getLogger("MyBot")

    def _setup_logging(self):
        """
        Python의 logging 모듈을 설정합니다.
        """
        # 1. 로그 디렉토리 생성
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)

        # 2. 루트 로거 가져오기 및 초기화
        logger = logging.getLogger()
        logger.setLevel(logging.WARNING) # SD카드 수명 및 메모리 절약을 위해 WARNING 레벨 이상만 포착
        
        # 기존 핸들러가 있다면 제거 (중복 출력 방지)
        if logger.hasHandlers():
            logger.handlers.clear()

        # 3. 포매터 정의 (로그의 모양 결정)
        # 예: [2025-12-20 14:00:00] [ERROR] [music.py:50] 연결 실패
        standard_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 4. [파일 핸들러] 설정
        # TimedRotatingFileHandler: 정해진 시간마다 파일을 교체함 (midnight = 자정)
        file_handler = TimedRotatingFileHandler(
            filename=f"{LOG_DIR}/system.log",
            when="midnight",
            interval=1,
            backupCount=30, # 30일치 로그 보관
            encoding="utf-8"
        )
        file_handler.setFormatter(standard_formatter)
        file_handler.setLevel(logging.INFO) # 파일에는 모든 정보 기록
        logger.addHandler(file_handler)

        # 5. [콘솔 핸들러] 설정 (터미널 출력용)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(standard_formatter)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)

        logging.info("✅ 로깅 시스템 초기화 완료 (File + Console)")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        봇이 준비되면 디스코드 핸들러를 연결합니다.
        """
        # 6. [디스코드 핸들러] 연결
        discord_handler = DiscordLogHandler(self.bot)
        # 디스코드 알림은 메시지 본문만 깔끔하게 전달 (Embed 내부에서 처리)
        discord_handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(discord_handler)
        
        logging.info(f"✅ 원격 로그 모니터링 활성화 (Target Channel ID: {LOG_CHANNEL_ID})")
        
        # 7. 구동 사유 (Startup Reason) 파악 및 알림 전송
        await self._send_startup_notification()

    async def _send_startup_notification(self):
        """봇이 부팅될 때 알림 채널에 구동 사유를 보냅니다."""
        if LOG_CHANNEL_ID == 0:
            return
            
        reason_file = "data/startup_reason.txt"
        startup_reason = "수동 스크립트 실행 또는 시스템 크래시(Crash) 후 자동 복구"
        color = 0x3498DB # 기본 파란색
        title = "🟢 봇 시스템 구동 시작"
        
        # 파일이 존재하면 auto_update.sh가 남긴 사유를 읽음
        if os.path.exists(reason_file):
            try:
                with open(reason_file, 'r', encoding='utf-8') as f:
                    startup_reason = f.read().strip()
                os.remove(reason_file) # 일회성이므로 읽은 후 바로 삭제
                color = 0x2ECC71 # 자동 업데이트는 초록색
                title = "🔄 자동 업데이트 및 재구동 완료"
            except Exception as e:
                logging.error(f"구동 사유 파일을 읽는 중 오류 발생: {e}")
        
        target_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if target_channel:
            embed = discord.Embed(
                title=title,
                description=f"**원인:** {startup_reason}",
                color=color
            )
            import datetime
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            try:
                await target_channel.send(embed=embed)
            except Exception as e:
                logging.error(f"구동 알림 전송 실패: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(LogAgentCog(bot))