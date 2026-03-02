import pytest
import discord
from unittest.mock import AsyncMock, patch, MagicMock

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cogs.application_commands import CommandsCog

class TestApplicationCommands:

    @pytest.mark.asyncio
    async def test_summary_command_routing(self):
        """/요약 명령어가 SummaryListenersCog로 정상 라우팅(분배) 되는지 검증"""
        mock_bot = MagicMock()
        # Summary 봇이 로드되어 있다고 가정
        mock_summary_cog = AsyncMock()
        mock_bot.get_cog.return_value = mock_summary_cog
        
        cog = CommandsCog(mock_bot)
        mock_interaction = AsyncMock()
        
        # 명령어 실행
        await cog.summary_command.callback(cog, mock_interaction, hours=3.0)
        
        # Interaction 과정 검증
        mock_bot.get_cog.assert_called_with("SummaryListenersCog")
        mock_interaction.response.defer.assert_called_once_with(thinking=True, ephemeral=False)
        mock_summary_cog.execute_summary.assert_called_once_with(mock_interaction, 3.0)

    @pytest.mark.asyncio
    async def test_play_command_routing(self):
        """/재생 명령어가 MusicAgentCog로 정상 분배되는지 검증"""
        mock_bot = MagicMock()
        mock_music_cog = AsyncMock()
        mock_bot.get_cog.return_value = mock_music_cog
        
        cog = CommandsCog(mock_bot)
        mock_interaction = AsyncMock()
        
        await cog.play.callback(cog, mock_interaction, 검색어="test song")
        
        mock_bot.get_cog.assert_called_with("MusicAgentCog")
        mock_music_cog.handle_play.assert_called_once_with(mock_interaction, "test song")

    @pytest.mark.asyncio
    async def test_cog_app_command_error(self):
        """명령어 실행 중 예외가 발생할 때 글로벌 에러 핸들러로 동작하는지 검증"""
        mock_bot = MagicMock()
        mock_bot.log = MagicMock()
        cog = CommandsCog(mock_bot)
        
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.command = MagicMock()
        mock_interaction.command.name = "테스트명령어"
        mock_interaction.response.is_done = MagicMock(return_value=False)
        mock_interaction.response.send_message = AsyncMock()
        
        dummy_error = discord.app_commands.AppCommandError("Some Error")
        
        await cog.cog_app_command_error(mock_interaction, dummy_error)
        
        # 에러 로깅이 남았는지 확인
        mock_bot.log.error.assert_called_once()
        # 오류 응답 메시지가 전송되었는지 확인
        mock_interaction.response.send_message.assert_called_once_with(
            "명령어 처리 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
            ephemeral=True
        )
