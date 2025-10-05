import os
import sys
import logging
import asyncio
from dotenv import load_dotenv

# Rich 관련 임포트는 UI 표시에 필요하므로 유지합니다.
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeRemainingColumn


# --- .env 파일 로드 ---
load_dotenv()

# --- 로거 가져오기 ---
# 이제 설정은 LogAgent가 담당하므로, 여기서는 로거 객체만 가져옵니다.
logger = logging.getLogger("MyBot")

# --- 나머지 모듈 임포트 ---
try:
    import discord
    from discord.ext import commands
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
            # Cog 로드 경로 (LogAgent가 가장 먼저 오도록 유지)
            self.initial_extensions = [
                "cogs.logging.log_agent",
                "cogs.summary.summary_listeners",
                "cogs.finance.finance_agent",
                "cogs.music.music_agent",
                "cogs.application_commands",
                "cogs.mining.mining_agent"
            ]
            # UI에 사용할 Rich Console 객체를 봇 인스턴스에 저장
            self.console = Console()

        async def setup_hook(self):
            with Progress(
                TextColumn("[bold blue]>[/bold blue]", justify="right"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None), MofNCompleteColumn(),
                TextColumn("•"), TimeRemainingColumn(),
                console=self.console  # self.console 사용
            ) as progress:
                task = progress.add_task("[green]기능 로드 중...", total=len(self.initial_extensions))
                for extension in self.initial_extensions:
                    try:
                        await self.load_extension(extension)
                        # LogAgent가 로드되면서 로깅 설정이 적용됩니다.
                        logging.info(f"✅ '{extension}' 로드 성공.")
                        progress.update(task, advance=1, description=f"[cyan]{extension:<30}")
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logging.error(f"'{extension}' 로드 실패.", exc_info=True)
                        progress.update(task, advance=1, description=f"[red]{extension:<30}")

            logging.info("✅ 모든 기능(Cog)이 성공적으로 로드되었습니다.")
            try:
                logging.info("슬래시 커맨드 동기화를 시작합니다...")
                synced = await self.tree.sync()
                logging.info(f"✅ {len(synced)}개의 슬래시 커맨드 동기화 완료.")
            except Exception as e:
                logging.error("슬래시 커맨드 동기화 중 오류 발생:", exc_info=True)

    bot = MyBot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        # on_ready UI 패널은 그대로 유지합니다.
        panel = Panel(
            Text(f"{bot.user.name} (ID: {bot.user.id})\n모든 기능 정상 작동 중", justify="center"),
            title="[bold green]✅ 봇 온라인",
            border_style="green"
        )
        bot.console.print(panel) # bot.console 사용

        game = discord.Game("모든 기능 정상 작동 중")
        await bot.change_presence(status=discord.Status.online, activity=game)

    # 이 파일의 최상단에서 로거를 가져왔으므로, bot.run 전에도 사용 가능합니다.
    logger.info("Discord 봇 실행 준비 중...")
    bot.run(DISCORD_TOKEN)

except Exception:
    # 이 부분은 LogAgent가 로드되기 전에 발생할 수 있으므로,
    # traceback이 포함된 기본 로깅으로 출력됩니다.
    logging.critical("봇 초기화 중 심각한 오류가 발생하여 프로그램을 종료합니다.", exc_info=True)
    sys.exit("초기화 실패")
