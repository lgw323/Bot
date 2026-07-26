import pytest
import logging
import asyncio
import io
from unittest.mock import MagicMock, AsyncMock, patch

from cogs.logging.log_agent import (
    DiscordLogHandler,
    LogAgentCog,
    WatchSessionControlView,
)

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

    @pytest.mark.asyncio
    @patch("cogs.logging.log_agent.MASTER_USER_ID", 777)
    async def test_watch_close_button_rejects_non_master_user(self):
        view = WatchSessionControlView("session-123")
        interaction = MagicMock()
        interaction.user.id = 999
        interaction.response.send_message = AsyncMock()

        button = next(
            child
            for child in view.children
            if child.custom_id == "log_agent:close_watch_session"
        )
        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        assert "권한" in interaction.response.send_message.call_args.args[0]

    @pytest.mark.asyncio
    @patch("cogs.logging.log_agent.MASTER_USER_ID", 777)
    @patch(
        "cogs.watch_together.watch_server.close_watch_session",
        new_callable=AsyncMock,
    )
    async def test_watch_close_button_closes_session(
        self,
        mock_close_session,
    ):
        mock_close_session.return_value = True
        view = WatchSessionControlView("session-123")
        interaction = MagicMock()
        interaction.user.id = 777
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        button = next(
            child
            for child in view.children
            if child.custom_id == "log_agent:close_watch_session"
        )
        await button.callback(interaction)

        mock_close_session.assert_awaited_once_with(
            "session-123",
            reason="관리자 강제 종료",
        )
        interaction.edit_original_response.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cogs.logging.log_agent.LOG_CHANNEL_ID", 12345)
    async def test_watch_session_control_is_sent_to_private_log_channel(self):
        bot = MagicMock()
        bot.get_channel.return_value = None
        channel = AsyncMock()
        bot.fetch_channel = AsyncMock(return_value=channel)
        cog = object.__new__(LogAgentCog)
        cog.bot = bot

        await cog.send_watch_session_control(
            session_id="session-123",
            guild_id=456,
            channel_id=789,
            created_by=321,
        )

        channel.send.assert_awaited_once()
        sent = channel.send.call_args.kwargs
        assert sent["embed"].title == "🎬 Watch Together 세션 생성"
        assert isinstance(sent["view"], WatchSessionControlView)

    def test_setup_logging_preserves_foreign_handlers(self, tmp_path):
        root_logger = logging.getLogger()
        original_level = root_logger.level
        project_logger_names = (
            "MyBot",
            "DatabaseManager",
            "Commands",
            "LevelingCog",
            "WatchAgent",
            "WatchServer",
            "cogs",
        )
        original_project_levels = {
            name: logging.getLogger(name).level
            for name in project_logger_names
        }
        foreign_handler = logging.StreamHandler(io.StringIO())
        root_logger.addHandler(foreign_handler)
        before_handlers = set(root_logger.handlers)
        cog = object.__new__(LogAgentCog)

        try:
            with patch(
                "cogs.logging.log_agent.LOG_DIR",
                tmp_path / "logs",
            ):
                cog._setup_logging()

            assert foreign_handler in root_logger.handlers
            owned_handlers = [
                handler
                for handler in root_logger.handlers
                if getattr(
                    handler,
                    "_discordbot_owned_handler",
                    False,
                )
            ]
            assert len(owned_handlers) == 2

            logging.getLogger("MyBot").info("project-info-marker")
            for handler in owned_handlers:
                handler.flush()
            log_text = (tmp_path / "logs" / "system.log").read_text(
                encoding="utf-8",
            )
            assert "project-info-marker" in log_text
        finally:
            for handler in list(root_logger.handlers):
                if handler not in before_handlers:
                    root_logger.removeHandler(handler)
                    handler.close()
            root_logger.removeHandler(foreign_handler)
            foreign_handler.close()
            root_logger.setLevel(original_level)
            for name, level in original_project_levels.items():
                logging.getLogger(name).setLevel(level)

    @pytest.mark.asyncio
    async def test_on_ready_adds_one_discord_handler_across_reconnects(self):
        root_logger = logging.getLogger()
        bot = MagicMock()
        cog = object.__new__(LogAgentCog)
        cog.bot = bot
        cog.discord_handler = None
        cog._ready_initialized = False
        cog._send_startup_notification = AsyncMock()

        try:
            await cog.on_ready()
            await cog.on_ready()

            handlers = [
                handler
                for handler in root_logger.handlers
                if isinstance(handler, DiscordLogHandler)
                and handler.bot is bot
            ]
            assert len(handlers) == 1
            cog._send_startup_notification.assert_awaited_once_with()
        finally:
            cog.cog_unload()
