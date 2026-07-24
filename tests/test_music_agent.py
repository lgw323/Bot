import pytest
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.music.music_agent import MusicAgentCog
from cogs.music.music_state_store import MusicStateStore
from cogs.music.music_utils import LoopMode

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


@pytest.mark.asyncio
async def test_cog_unload_delegates_snapshot_and_cleanup() -> None:
    bot = MagicMock()
    state_store = MagicMock(spec=MusicStateStore)
    state_store.save = AsyncMock()
    state = MagicMock()
    state.cleanup = AsyncMock()
    agent = MusicAgentCog(bot=bot, state_store=state_store)
    agent.music_states = {12345: state}

    await agent.cog_unload()

    state_store.save.assert_awaited_once_with(agent.music_states)
    state.cleanup.assert_awaited_once_with(leave=True, update_ui=False)


@pytest.mark.asyncio
async def test_on_ready_restores_complete_music_session() -> None:
    """재시작 후 채널, 위치, 대기열, 반복 및 자동 재생 상태를 복원합니다."""
    guild_id = 12345
    text_channel_id = 111
    voice_channel_id = 222

    bot = MagicMock()
    guild = MagicMock()
    guild.id = guild_id
    guild.name = "Test Guild"
    requester = MagicMock()
    guild.get_member.return_value = requester
    bot.guilds = [guild]

    text_channel = object()
    connected_voice_client = MagicMock()

    class FakeVoiceChannel:
        name = "Music"

        async def connect(self, timeout: float, self_deaf: bool):
            assert timeout == 20.0
            assert self_deaf is True
            return connected_voice_client

    voice_channel = FakeVoiceChannel()
    bot.get_channel.side_effect = lambda channel_id: {
        text_channel_id: text_channel,
        voice_channel_id: voice_channel,
    }.get(channel_id)

    state = MagicMock()
    state.queue = deque()
    state.voice_client = None

    state_store = MagicMock(spec=MusicStateStore)
    agent = MusicAgentCog(bot=bot, state_store=state_store)
    agent.initial_setup_done = True
    agent.get_music_state = AsyncMock(return_value=state)

    restored_states = {
        str(guild_id): {
            "text_channel_id": text_channel_id,
            "voice_channel_id": voice_channel_id,
            "volume": 0.35,
            "loop_mode": "QUEUE",
            "auto_play_enabled": True,
            "elapsed_seconds": 47,
            "current_song": {
                "webpage_url": "https://youtube.com/watch?v=current",
                "title": "Current Song",
                "duration": 180,
                "thumbnail": "current-thumb",
                "uploader": "Current Artist",
                "requester_id": 10,
            },
            "queue": [
                {
                    "webpage_url": "https://youtube.com/watch?v=next",
                    "title": "Next Song",
                    "duration": 200,
                    "thumbnail": "next-thumb",
                    "uploader": "Next Artist",
                    "requester_id": 20,
                }
            ],
        }
    }
    state_store.load_once = AsyncMock(return_value=restored_states)

    with patch("cogs.music.music_agent.MUSIC_CHANNEL_ID", text_channel_id), \
         patch(
             "cogs.music.music_agent.discord.VoiceChannel",
             FakeVoiceChannel,
         ):
        await agent.on_ready()

    state_store.load_once.assert_awaited_once_with()
    assert state.volume == 0.35
    assert state.loop_mode is LoopMode.QUEUE
    assert state.auto_play_enabled is True
    assert state.seek_time == 47
    assert state.text_channel is text_channel
    assert state.voice_client is connected_voice_client
    assert [song.title for song in state.queue] == ["Current Song", "Next Song"]
    state.play_next_song.set.assert_called_once_with()
