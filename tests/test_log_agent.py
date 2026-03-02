import pytest
import logging
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cogs.logging.log_agent import DiscordLogHandler

class TestLogAgent:
    
    @pytest.mark.asyncio
    @patch("cogs.logging.log_agent.LOG_CHANNEL_ID", 12345)
    async def test_discord_log_handler_emit(self):
        """디스코드 로깅 핸들러가 ERROR 레벨 이상의 이벤트를 정상 포착하여 비동기 전송하는지 검증"""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        
        # 실제 이벤트 루프를 타게 하려면 MagicMock loop 대신 get_running_loop() 사용
        mock_bot.loop = asyncio.get_running_loop()
        
        mock_channel = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel
        
        handler = DiscordLogHandler(mock_bot)
        
        # log_agent 모듈 내부에 이미 최상단에서 import된 LOG_CHANNEL_ID 값을 겹쳐씌우기 위해 핸들러 인스턴스 전역을 패치
        with patch.object(handler, "target_channel", mock_channel):
            record = logging.LogRecord(
                name="TestLogger", level=logging.ERROR, pathname="test_path.py",
                lineno=10, msg="This is a test error message", args=(), exc_info=None
            )
            handler.format = MagicMock(return_value="[FORMATTED] This is a test error message")
            
            # 여기서 _async_emit를 직접 호출하여 테스트 신뢰성을 높임 (emit은 asyncio.run_coroutine_threadsafe라서 테스트 루크와 충돌 가능)
            await handler._async_emit(record)
            
            mock_channel.send.assert_called_once()
            sent_kwargs = mock_channel.send.call_args.kwargs
            assert "embed" in sent_kwargs
            embed = sent_kwargs["embed"]
            assert "This is a test error message" in embed.description
            assert "Line: 10" in embed.footer.text

    @pytest.mark.asyncio
    @patch("cogs.logging.log_agent.LOG_CHANNEL_ID", 12345)
    async def test_discord_log_handler_truncation(self):
        """로그 메시지가 2000자를 초과할 때 잘림(Truncation) 처리가 되는지 검증"""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        mock_channel = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel
        
        handler = DiscordLogHandler(mock_bot)
        long_message = "A" * 2500
        handler.format = MagicMock(return_value=long_message)
        
        with patch.object(handler, "target_channel", mock_channel):
            record = logging.LogRecord("T", logging.ERROR, "P", 1, "M", (), None)
            
            await handler._async_emit(record)
            
            sent_kwargs = mock_channel.send.call_args.kwargs
            embed = sent_kwargs["embed"]
            
            assert len(embed.description) < 2000
            assert "...(내용이 너무 길어 생략됨)" in embed.description
