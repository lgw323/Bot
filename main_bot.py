import os
import sys
import logging
import asyncio
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

import database_manager

# Rich 관련 임포트는 UI 표시에 필요하므로 유지합니다.
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeRemainingColumn

# --- .env 파일 로드 ---
# Prod 환경(Linux) 기준 절대 경로 혹은 스크립트 위치 기반 경로 설정
ENV_PATH: Path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# --- 로거 가져오기 ---
# 이제 설정은 LogAgent가 담당하므로, 여기서는 로거 객체만 가져옵니다.
logger: logging.Logger = logging.getLogger("MyBot")

# --- 나머지 모듈 임포트 ---
try:
    import discord
    from discord.ext import commands
    from discord.ext.commands.errors import ExtensionFailed, ExtensionNotFound
except ImportError as e:
    logger.critical(f"필수 라이브러리 임포트 실패: {e}", exc_info=True)
    sys.exit("라이브러리 로드 실패")

# --- Bot 클래스 정의 ---
class MyBot(commands.Bot):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Cog 로드 경로 (LogAgent가 가장 먼저 오도록 유지)
        self.initial_extensions: List[str] = [
            "cogs.logging.log_agent",
            "cogs.summary.summary_listeners",
            "cogs.music.music_agent",
            "cogs.leveling.leveling_core",
            "cogs.application_commands"
        ]
        # UI에 사용할 Rich Console 객체를 봇 인스턴스에 저장
        self.console: Console = Console()

    async def setup_hook(self) -> None:
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
                    logger.info(f"✅ '{extension}' 로드 성공.")
                    progress.update(task, advance=1, description=f"[cyan]{extension:<30}")
                    await asyncio.sleep(0.1)
                except ExtensionNotFound:
                    logger.error(f"'{extension}' 모듈을 찾을 수 없습니다 (ExtensionNotFound).", exc_info=True)
                    progress.update(task, advance=1, description=f"[red]{extension:<30}")
                except ExtensionFailed:
                    logger.error(f"'{extension}' 로드 중 내부 실행 오류가 발생했습니다 (ExtensionFailed).", exc_info=True)
                    progress.update(task, advance=1, description=f"[red]{extension:<30}")
                except Exception as e:
                    logger.error(f"'{extension}' 로드 중 알 수 없는 예외 발생: {e}", exc_info=True)
                    progress.update(task, advance=1, description=f"[red]{extension:<30}")

        logger.info("✅ 모든 기능(Cog)이 성공적으로 로드 시도 완료되었습니다.")
        
        try:
            logger.info("슬래시 커맨드 동기화를 시작합니다...")
            synced: List[Any] = await self.tree.sync()
            logger.info(f"✅ {len(synced)}개의 슬래시 커맨드 동기화 완료.")
        except discord.DiscordException as e:
            logger.error(f"슬래시 커맨드 동기화 중 Discord 예외 발생: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"슬래시 커맨드 동기화 중 일반 오류 발생: {e}", exc_info=True)

# --- 메인 실행 함수 ---
def main() -> None:
    try:
        DISCORD_TOKEN: Optional[str] = os.getenv("DISCORD_TOKEN")
        if not DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN이 .env 파일에 설정되지 않았습니다.")

        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        bot: MyBot = MyBot(command_prefix=commands.when_mentioned, intents=intents)

        @bot.event
        async def on_ready() -> None:
            # TODO: [SRP 위배] DB 초기화 및 데이터 마이그레이션(business logic)은 main_bot.py의 책임이 아님.
            # 추후 별도의 초기화 스크립트나 관리자(Cog) 내부 로직으로 구조적 분리 및 의존성 주입이 필요함.
            try:
                database_manager.init_db()
                database_manager.migrate_json_to_db()
            except Exception as e:
                logger.error(f"DB 초기화 중 예외 발생: {e}", exc_info=True)

            # on_ready UI 패널은 그대로 유지합니다.
            if bot.user:
                panel: Panel = Panel(
                    Text(f"{bot.user.name} (ID: {bot.user.id})\n모든 기능 정상 작동 중", justify="center"),
                    title="[bold green]✅ 봇 온라인",
                    border_style="green"
                )
                bot.console.print(panel) 

            game: discord.Game = discord.Game("펜타곤 침입")
            await bot.change_presence(status=discord.Status.online, activity=game)
            logger.info("봇 상태 및 활동 설정 완료.")

        logger.info("Discord 봇 실행 준비 중...")
        bot.run(DISCORD_TOKEN)

    except Exception:
        # 이 부분은 LogAgent가 상주하지 않거나 시작 전 예외 발생을 대비한 전역 예외 처리입니다.
        logger.critical("봇 초기화 중 심각한 오류가 발생하여 프로그램을 종료합니다.", exc_info=True)
        sys.exit("초기화 실패")

if __name__ == "__main__":
    main()
