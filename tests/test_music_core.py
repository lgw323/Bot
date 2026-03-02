import pytest
import discord
from unittest.mock import MagicMock
from cogs.music.music_core import MusicState

@pytest.fixture
def mock_guild() -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.name = "Test Guild"
    guild.id = 12345
    return guild

@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.loop = MagicMock()
    bot.loop.create_task.return_value = MagicMock()
    return bot

@pytest.fixture
def mock_cog() -> MagicMock:
    return MagicMock()

def test_music_state_initialization(mock_bot: MagicMock, mock_cog: MagicMock, mock_guild: MagicMock) -> None:
    state = MusicState(bot=mock_bot, cog=mock_cog, guild=mock_guild, initial_volume=0.7)
    assert state.volume == 0.7
    assert state.guild == mock_guild
    assert state.bot == mock_bot
    assert state.cog == mock_cog
    assert len(state.queue) == 0

def test_normalize_title(mock_bot: MagicMock, mock_cog: MagicMock, mock_guild: MagicMock) -> None:
    state = MusicState(bot=mock_bot, cog=mock_cog, guild=mock_guild)
    
    # 괄호 제거 확인
    assert state._normalize_title("Official MV - Song Name [1080p]") == "song name"
    # 소문자 변환 및 키워드 제거 확인
    assert state._normalize_title("Artist - Title (Live Performance)") == "artist title"
    assert state._normalize_title("Song Name 가사 영상") == "song name 영상"
    # 빈 값 확인
    assert state._normalize_title("") == ""
