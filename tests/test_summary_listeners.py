import pytest
import discord
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from cogs.summary.summary_listeners import SummaryListenersCog

@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    return bot

@pytest.fixture
def summary_cog(mock_bot: MagicMock) -> Generator[SummaryListenersCog, None, None]:
    with patch("cogs.summary.summary_listeners.initialize_gemini_client"):
        with patch("cogs.summary.summary_listeners.SUMMARY_CHANNEL_ID", 12345):
            cog = SummaryListenersCog(mock_bot)
            yield cog

@pytest.mark.asyncio
async def test_on_message_adds_to_log(summary_cog: SummaryListenersCog) -> None:
    # Setup
    summary_cog.initial_load_done = True
    mock_message = MagicMock(spec=discord.Message)
    mock_message.author.bot = False
    mock_message.channel.id = 12345
    mock_message.content = "Test message"
    mock_message.guild.id = 111
    mock_message.author.id = 222
    mock_message.author.display_name = "User"
    mock_message.created_at = datetime.now(timezone.utc)
    
    # Act
    await summary_cog.on_message(mock_message)
    
    # Assert
    assert len(summary_cog.message_log) == 1
    log_tuple = summary_cog.message_log[0]
    assert log_tuple[1] == 111
    assert log_tuple[3] == "User"
    assert log_tuple[4] == "Test message"

@pytest.mark.asyncio
async def test_prune_old_messages(summary_cog: SummaryListenersCog) -> None:
    # Setup
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=25)
    recent_time = now - timedelta(hours=1)
    
    summary_cog.message_log.append((old_time, 111, 222, "User1", "Old Msg"))
    summary_cog.message_log.append((recent_time, 111, 333, "User2", "New Msg"))
    
    # Act
    await summary_cog.prune_old_messages()
    
    # Assert
    assert len(summary_cog.message_log) == 1
    assert summary_cog.message_log[0][4] == "New Msg"

@pytest.mark.asyncio
async def test_execute_summary_no_messages(summary_cog: SummaryListenersCog) -> None:
    # Setup
    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.guild.id = 111
    
    # AsyncMock for followup.send
    mock_followup = MagicMock()
    mock_followup.send = AsyncMock()
    mock_interaction.followup = mock_followup
    
    # Setup response.is_done
    mock_response = MagicMock()
    mock_response.is_done.return_value = True
    mock_interaction.response = mock_response
    
    mock_channel = MagicMock()
    mock_channel.name = "summary-channel"
    summary_cog.bot.get_channel = MagicMock(return_value=mock_channel)
    
    # Act
    await summary_cog.execute_summary(mock_interaction, hours=1.0)
    
    # Assert
    mock_interaction.followup.send.assert_called_once()
    args, kwargs = mock_interaction.followup.send.call_args
    assert "요약할 메시지가 없습니다" in args[0]
