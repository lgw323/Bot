import os
import sys
import logging
import traceback
import asyncio
import subprocess
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Any

import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- 현재 파일 위치를 기준으로 봇 루트 디렉토리 산출 ---
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

# .env 파일 로드
ENV_PATH: Path = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# --- 설정값 ---
# 로그를 저장할 로컬 디렉토리 (data 폴더 내부에 logs 폴더 생성)
LOG_DIR: Path = BASE_DIR / "data" / "logs"
# 디스코드 로그 채널 ID (로그 전용 서버의 채널 ID)
LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))
MASTER_USER_ID: int = int(os.getenv("MASTER_USER_ID", "0"))

class RestartControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None) # 상시 유지

    @discord.ui.button(label="🔄 수동 업데이트 및 재시작", style=discord.ButtonStyle.green, custom_id="log_agent:restart_bot")
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != MASTER_USER_ID:
            await interaction.response.send_message("이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return
            
        await interaction.response.send_message("🔄 수동 업데이트 및 재시작 스크립트를 서버에서 실행합니다. 잠시 후 봇이 갱신 후 재구동됩니다.", ephemeral=True)
        try:
            # Prod 환경(Raspberry Pi)을 기준으로 작성됨
            subprocess.Popen(['bash', '/home/os/bot/scripts/auto_update.sh'])
        except Exception as e:
            logging.error(f"수동 업데이트 스크립트 실행 실패: {e}")

class DiscordLogHandler(logging.Handler):
    """
    [커스텀 핸들러]
    ERROR 레벨 이상의 로그를 감지하면, 지정된 디스코드 채널로 비동기 전송합니다.
    """
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot: commands.Bot = bot
        self.target_channel: Optional[discord.TextChannel] = None

    def emit(self, record: logging.LogRecord) -> None:
        """
        로깅 이벤트가 발생했을 때 호출되는 함수입니다.
        """
        try:
            # 1. 봇이 준비되지 않았거나, 로그 채널 ID가 설정되지 않았다면 무시
            if LOG_CHANNEL_ID == 0 or not self.bot.is_ready():
                return

            # 2. ERROR 이상의 심각한 문제만 필터링 (INFO, DEBUG는 무시)
            if record.levelno >= logging.ERROR:
                # logging 모듈은 동기(sync) 방식이지만, discord.py는 비동기(async)입니다.
                # 다른 스레드에서 들어올 수 있으므로 run_coroutine_threadsafe를 사용합니다.
                asyncio.run_coroutine_threadsafe(self._async_emit(record), self.bot.loop)
        except Exception:
            # 재귀적인 예외 발생을 방지하기 위해 로거 대신 stderr에만 출력
            sys.stderr.write("[DiscordLogHandler] 로그 emit 중 내부 오류 발생\\n")

    async def _async_emit(self, record: logging.LogRecord) -> None:
        """
        실제로 디스코드 메시지를 전송하는 비동기 함수입니다.
        """
        try:
            # 채널 객체 캐싱 (최초 1회만 가져옴)
            if not self.target_channel:
                channel = self.bot.get_channel(LOG_CHANNEL_ID)
                if isinstance(channel, discord.TextChannel):
                    self.target_channel = channel
            
            if self.target_channel:
                # 로그 메시지 포맷팅
                msg: str = self.format(record)
                
                # 디스코드 메시지 길이 제한(2000자) 처리
                if len(msg) > 1900:
                    msg = msg[:1900] + "...(내용이 너무 길어 생략됨)"
                
                # 가독성을 위한 Embed 생성
                embed: discord.Embed = discord.Embed(
                    title="🚨 시스템 오류 발생 (System Error)", 
                    description=f"```log\\n{msg}\\n```",
                    color=0xFF0000  # 빨간색
                )
                
                # 발생 위치 정보 (모듈명, 라인 번호)
                footer_text: str = f"Module: {record.module} | Line: {record.lineno}"
                embed.set_footer(text=footer_text)
                
                await self.target_channel.send(embed=embed)
                
                if hasattr(self, 'cog') and getattr(self, 'cog'):
                    await self.cog.send_control_panel(self.target_channel)

        except Exception:
            # 재귀 에러 방지용 내부 try-except (디스코드 전송 실패 또는 예외 처리 시 조용히 무시)
            pass

class LogAgentCog(commands.Cog, name="LogAgent"):
    """
    봇의 전역 로깅 시스템을 초기화하고 관리하는 Cog입니다.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self._setup_logging()
        # 다른 Cog에서 self.bot.log.info(...) 형태로 사용할 수 있도록 주입
        self.bot.log: logging.Logger = logging.getLogger("MyBot")
        self.control_message: Optional[discord.Message] = None

    async def send_control_panel(self, channel: discord.TextChannel) -> None:
        if self.control_message:
            try:
                await self.control_message.delete()
            except Exception:
                pass
        try:
            self.control_message = await channel.send(
                "**[ 🛠️ 시스템 제어 패널 ]**\\n아래 버튼을 눌러 봇 최신화 및 강제 재시작을 수행할 수 있습니다.", 
                view=RestartControlView()
            )
        except Exception as e:
            logging.error(f"컨트롤 패널 메시지 갱신 실패: {e}")

    def _setup_logging(self) -> None:
        """
        Python의 logging 모듈을 설정합니다.
        """
        try:
            # 1. 로그 디렉토리 생성 (pathlib 활용)
            if not LOG_DIR.exists():
                LOG_DIR.mkdir(parents=True, exist_ok=True)

            # 2. 루트 로거 가져오기 및 초기화
            logger: logging.Logger = logging.getLogger()
            logger.setLevel(logging.WARNING) # SD카드 수명 및 메모리 절약을 위해 WARNING 레벨 이상만 포착
            
            # 기존 핸들러가 있다면 제거 (중복 출력 방지)
            if logger.hasHandlers():
                logger.handlers.clear()

            # 3. 포매터 정의 (로그의 모양 결정)
            standard_formatter: logging.Formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 4. [파일 핸들러] 설정
            log_file_path: Path = LOG_DIR / "system.log"
            file_handler: TimedRotatingFileHandler = TimedRotatingFileHandler(
                filename=str(log_file_path),
                when="midnight",
                interval=1,
                backupCount=30, # 30일치 로그 보관
                encoding="utf-8"
            )
            file_handler.setFormatter(standard_formatter)
            file_handler.setLevel(logging.INFO) # 파일에는 모든 정보 기록
            logger.addHandler(file_handler)

            # 5. [콘솔 핸들러] 설정 (터미널 출력용)
            console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(standard_formatter)
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)

            logging.info("✅ 로깅 시스템 초기화 완료 (File + Console)")
        except Exception:
            # 로깅 시스템 자체 초기화 실패 시 시스템 에러 출력 후 회피
            sys.stderr.write("[LogAgentCog] 로깅 시스템 초기화 중 심각한 오류 발생\\n")
            traceback.print_exc(file=sys.stderr)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        봇이 준비되면 디스코드 핸들러를 연결합니다.
        """
        try:
            # 6. [디스코드 핸들러] 연결
            discord_handler: DiscordLogHandler = DiscordLogHandler(self.bot)
            discord_handler.cog = self
            # 디스코드 알림은 메시지 본문만 깔끔하게 전달 (Embed 내부에서 처리)
            discord_handler.setFormatter(logging.Formatter('%(message)s'))
            logging.getLogger().addHandler(discord_handler)
            
            logging.info(f"✅ 원격 로그 모니터링 활성화 (Target Channel ID: {LOG_CHANNEL_ID})")
            
            # 7. 구동 사유 (Startup Reason) 파악 및 알림 전송
            await self._send_startup_notification()
        except Exception as e:
            # 핸들러 부착 실패 시 로컬 로그 기록
            logging.error(f"[LogAgentCog] on_ready 실행 중 에러 발생: {e}", exc_info=True)

    async def _send_startup_notification(self) -> None:
        """봇이 부팅될 때 알림 채널에 구동 사유를 보냅니다."""
        try:
            if LOG_CHANNEL_ID == 0:
                return
                
            reason_file: Path = BASE_DIR / "data" / "startup_reason.txt"
            startup_reason: str = "수동 스크립트 실행 또는 시스템 크래시(Crash) 후 자동 복구"
            color: int = 0x3498DB # 기본 파란색
            title: str = "🟢 봇 시스템 구동 시작"
            
            # 파일이 존재하면 auto_update.sh가 남긴 사유를 읽음
            if reason_file.exists():
                try:
                    with open(reason_file, 'r', encoding='utf-8') as f:
                        startup_reason = f.read().strip()
                    reason_file.unlink() # 일회성이므로 읽은 후 바로 삭제
                    color = 0x2ECC71 # 자동 업데이트는 초록색
                    title = "🔄 자동 업데이트 및 재구동 완료"
                except Exception as e:
                    logging.error(f"구동 사유 파일을 읽는 중 오류 발생: {e}")
            
            target_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if isinstance(target_channel, discord.TextChannel):
                embed: discord.Embed = discord.Embed(
                    title=title,
                    description=f"**원인:** {startup_reason}",
                    color=color,
                    timestamp=discord.utils.utcnow()
                )
                try:
                    await target_channel.send(embed=embed)
                    await self.send_control_panel(target_channel)
                except Exception as e:
                    logging.error(f"구동 알림 전송 실패: {e}")
        except Exception as e:
            logging.error(f"[_send_startup_notification] 전체 예외 발생: {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogAgentCog(bot))