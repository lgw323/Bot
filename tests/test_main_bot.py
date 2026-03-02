import pytest
import asyncio
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main_bot import MyBot
import discord

class TestMainBot:

    @pytest.mark.asyncio
    async def test_bot_initialization_and_intents(self):
        """봇 초기 객체 생성 시 기본 인텐트 설정 여부 검증 (메시지, 멤버)"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        bot = MyBot(command_prefix="!", intents=intents)
        
        assert bot.intents.message_content is True
        assert bot.intents.members is True
        # 기본 탑재되어야 할 Cogs 리스트가 있는지 확인
        assert "cogs.logging.log_agent" in bot.initial_extensions

    @pytest.mark.asyncio
    @patch("database_manager.init_db")
    @patch("database_manager.migrate_json_to_db")
    async def test_setup_hook_loads_extensions(self, mock_migrate, mock_init):
        """setup_hook에서 Cog들과 DB 초기화 작업이 연결(호출)되는지 시뮬레이션"""
        bot = MyBot(command_prefix="!", intents=discord.Intents.default())
        # load_extension, tree.sync 등의 비동기 동작 모방
        bot.load_extension = AsyncMock()
        bot.tree.sync = AsyncMock(return_value=["Command1", "Command2"])
        
        # 실제 환경에서는 GUI 패널이 돌아가므로 시간 소요 제거 대신 호출 여부만 확인
        await bot.setup_hook()
        
        # 모든 extesnsion이 로드 시도되었는지 확인
        assert bot.load_extension.call_count == len(bot.initial_extensions)
        for ext in bot.initial_extensions:
            bot.load_extension.assert_any_call(ext)
        
        bot.tree.sync.assert_called_once()

# 모의 함수를 위한 AsyncMock 보조
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
