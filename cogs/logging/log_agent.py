# -*- coding: utf-8 -*-
import os
import sys
import logging
import traceback
from dotenv import load_dotenv

import discord
from discord.ext import commands
from discord import app_commands
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- Rich 라이브러리를 사용한 고급 로깅 핸들러 ---
console = Console()
command_logger = logging.getLogger("Commands")

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
    """에러 발생 시 traceback 정보를 포함한 패널을 출력하는 커스텀 핸들러."""
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

class LogAgentCog(commands.Cog, name="LogAgent"):
    """봇의 모든 로깅 설정과 명령어 사용 기록을 담당합니다."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._setup_logging()
        # [신규] 봇 객체에 중앙 로거를 추가합니다.
        # 이제 다른 Cog에서는 self.bot.log 로 접근할 수 있습니다.
        self.bot.log = logging.getLogger("MyBot")


    def _setup_logging(self):
        """봇의 전역 로깅 시스템을 설정합니다."""
        is_debug_mode = os.getenv('DEBUG_MODE', 'False').upper() == 'TRUE'
        log_level = logging.DEBUG if is_debug_mode else logging.INFO

        # force=True를 사용하여 기존 핸들러를 제거하고 새로 설정합니다.
        logging.basicConfig(
            level=log_level,
            format="[%(name)-12s] %(message)s",
            handlers=[CustomRichHandler(show_path=False, console=console)],
            force=True
        )

        logging.getLogger("discord").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)

        logger = logging.getLogger("LogAgent")
        if is_debug_mode:
            logger.warning("🐛 디버그 모드가 활성화되었습니다. 상세 로그가 출력됩니다.")
        else:
            logger.info("✅ 중앙화된 로깅 시스템이 활성화되었습니다. (일반 모드)")

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        """슬래시 명령어가 성공적으로 실행되었을 때 호출됩니다."""
        # interaction.data에서 사용자가 입력한 옵션(인자)을 가져옵니다.
        options = interaction.data.get('options', [])
        
        args_str = ""
        if options:
            # 옵션들을 "이름: '값'" 형태의 문자열로 예쁘게 만듭니다.
            args_list = [f"{opt['name']}: '{opt['value']}'" for opt in options]
            args_str = f" (인자: {', '.join(args_list)})"
            
        # 채널이 DM이거나 스레드인 경우를 대비하여 안전하게 채널 이름을 가져옵니다.
        channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else 'DM'

        log_message = (
            f"사용자 '{interaction.user.display_name}'가 "
            f"'#{channel_name}' 채널에서 '/{command.name}' 명령어를 사용했습니다.{args_str}"
        )
        
        # 위에서 만든 'Commands' 로거를 사용하여 로그를 남깁니다.
        command_logger.info(log_message)


async def setup(bot: commands.Bot):
    """봇에 LogAgentCog를 추가하기 위한 설정 함수입니다."""
    await bot.add_cog(LogAgentCog(bot))
