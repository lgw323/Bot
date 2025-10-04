import os
import sys
import logging
import asyncio
import traceback
from dotenv import load_dotenv

from rich.logging import RichHandler
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# --- .env 파일 로드 ---
load_dotenv()

# --- 새로운 로깅 시스템 설정 ---
LOG_LEVEL = logging.INFO
console = Console()

# 에러 발생 시 출력될 패널을 생성하는 함수
def create_error_panel(record: logging.LogRecord) -> Panel:
    """로그 레코드를 받아 에러 패널을 생성합니다."""
    error_type = ""
    error_message = str(record.msg)
    
    if record.exc_info:
        exc_type, exc_value, _ = record.exc_info
        error_type = exc_type.__name__
        error_message = str(exc_value)

    error_text = Text()
    error_text.append(f"모듈: {record.name}\n", style="bold white")
    error_text.append(f"위치: {record.filename}:{record.lineno}\n", style="white")
    if error_type:
        error_text.append(f"종류: {error_type}\n", style="bold magenta")
    error_text.append(f"내용: {error_message}", style="magenta")

    return Panel(
        error_text,
        title=f"[bold red]❌ 에러 발생 ({record.levelname})",
        border_style="red",
        expand=False
    )

class CustomRichHandler(RichHandler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            if not record.exc_info:
                exc_type, exc_value, tb = sys.exc_info()
                if exc_type and tb:
                    last_frame = traceback.extract_tb(tb)[-1]
                    record.filename = os.path.basename(last_frame.filename)
                    record.lineno = last_frame.lineno
                    record.exc_info = (exc_type, exc_value, tb)
            
            self.console.print(create_error_panel(record))
        else:
            super().emit(record)

# 로거 설정
logging.basicConfig(
    level=LOG_LEVEL,
    format="[%(name)-12s] %(message)s",
    handlers=[CustomRichHandler(show_path=False, console=console)]
)

# 불필요한 라이브러리 로그 줄이기
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

logger = logging.getLogger("MyBot")

# --- 나머지 모듈 임포트 ---
try:
    import discord
    from discord.ext import commands
    from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeRemainingColumn
except ImportError as e:
    logger.critical(f"필수 라이브러리 임포트 실패: {e}", exc_info=True)
    sys.exit("라이브러리 로드 실패")

# --- Bot 클래스 및 실행 ---
try:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN이 .env 파일에 설정되지 않았습니다.")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True


    class MyBot(commands.Bot):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # 'moderation_agent'를 리스트에서 제거했습니다.
            self.initial_extensions = [
                "summary_listeners",
                "finance_agent",
                "music_agent",
                "application_commands",
                "mining_agent"
            ]

        async def setup_hook(self):
            with Progress(
                TextColumn("[bold blue]>[/bold blue]", justify="right"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None), MofNCompleteColumn(),
                TextColumn("•"), TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[green]기능 로드 중...", total=len(self.initial_extensions))
                for extension in self.initial_extensions:
                    try:
                        await self.load_extension(extension)
                        logger.info(f"✅ '{extension}' 로드 성공.")
                        progress.update(task, advance=1, description=f"[cyan]{extension:<20}")
                        await asyncio.sleep(0.1)
                    except Exception:
                        logger.error(f"'{extension}' 로드 실패.", exc_info=True)
                        progress.update(task, advance=1, description=f"[red]{extension:<20}")

            logger.info("✅ 모든 기능(Cog)이 성공적으로 로드되었습니다.")
            try:
                logger.info("슬래시 커맨드 동기화를 시작합니다...")
                synced = await self.tree.sync()
                logger.info(f"✅ {len(synced)}개의 슬래시 커맨드 동기화 완료.")
            except Exception as e:
                logger.error("슬래시 커맨드 동기화 중 오류 발생:", exc_info=True)

    bot = MyBot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        panel = Panel(
            Text(f"{bot.user.name} (ID: {bot.user.id})\n모든 기능 정상 작동 중", justify="center"),
            title="[bold green]✅ 봇 온라인",
            border_style="green"
        )
        console.print(panel)
        game = discord.Game("모든 기능 정상 작동 중")
        await bot.change_presence(status=discord.Status.online, activity=game)

    logger.info("Discord 봇 실행 준비 중...")
    bot.run(DISCORD_TOKEN)

except Exception:
    logger.critical("봇 초기화 중 심각한 오류가 발생하여 프로그램을 종료합니다.", exc_info=True)
    sys.exit("초기화 실패")
