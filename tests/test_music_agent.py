import pytest
import os
from unittest.mock import MagicMock
from cogs.music.music_agent import MusicAgentCog

def test_music_agent_initialization() -> None:
    mock_bot = MagicMock()
    agent = MusicAgentCog(bot=mock_bot)
    
    assert agent.bot == mock_bot
    assert callable(getattr(agent, '_get_tts_filepath', None))

def test_get_tts_filepath() -> None:
    mock_bot = MagicMock()
    agent = MusicAgentCog(bot=mock_bot)
    
    path = agent._get_tts_filepath("테스트 텍스트")
    assert path is not None
    assert str(path).endswith(".opus")
    assert "bot_tts_cache" in str(path)
