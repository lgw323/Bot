import pytest
import discord
from unittest.mock import MagicMock
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    
from cogs.music.music_utils import Song, LoopMode, URL_REGEX

def test_url_regex() -> None:
    assert URL_REGEX.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert URL_REGEX.match("https://youtu.be/dQw4w9WgXcQ")
    assert URL_REGEX.match("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not URL_REGEX.match("https://www.google.com")

def test_song_initialization() -> None:
    mock_member = MagicMock(spec=discord.Member)
    mock_member.display_name = "TestUser"
    mock_member.display_avatar.url = "http://test.url/avatar.png"
    
    data = {
        'webpage_url': 'http://youtube.com/test',
        'url': 'http://stream.url',
        'title': 'Test Song',
        'duration': 130, # 2분 10초
        'thumbnail': 'http://thumb.url',
        'uploader': 'Test Artist'
    }
    
    song = Song(data=data, requester=mock_member)
    assert song.title == "Test Song"
    assert song.duration == 130
    assert song.uploader == "Test Artist"
    assert song.webpage_url == "http://youtube.com/test"
    assert song.requester == mock_member

def test_song_to_embed() -> None:
    mock_member = MagicMock(spec=discord.Member)
    mock_member.display_name = "TestUser"
    mock_member.display_avatar.url = "http://test.url/avatar.png"
    
    data = {
        'webpage_url': 'http://youtube.com/test',
        'url': 'http://stream.url',
        'title': 'Test Song',
        'duration': 130,
        'thumbnail': 'http://thumb.url',
        'uploader': 'Test Artist'
    }
    
    song = Song(data=data, requester=mock_member)
    embed = song.to_embed(title_prefix="[Playing] ")
    
    assert embed.title == "[Playing] Test Song"
    assert embed.url == "http://youtube.com/test"
    assert embed.color.value == 0x2ECC71 # BOT_EMBED_COLOR
    assert embed.thumbnail.url == "http://thumb.url"
    assert len(embed.fields) == 2
    assert embed.fields[0].name == "채널"
    assert embed.fields[0].value == "Test Artist"
    assert embed.fields[1].name == "길이"
    assert embed.fields[1].value == "2:10"
    assert "TestUser" in embed.footer.text

def test_loop_mode() -> None:
    assert LoopMode.NONE.value == 0
    assert LoopMode.SONG.value == 1
    assert LoopMode.QUEUE.value == 2

@pytest.mark.asyncio
async def test_music_states_io(tmp_path) -> None:
    from cogs.music.music_utils import save_music_states, load_music_states
    import cogs.music.music_utils as mu
    import os
    
    # 1. 파일 경로를 임시 경로로 패치
    original_file = mu.MUSIC_STATE_FILE
    temp_file = str(tmp_path / "test_music_state.json")
    mu.MUSIC_STATE_FILE = temp_file
    
    try:
        # 빈 상태 데이터 생성 (Mocking MusicState)
        mock_state = MagicMock()
        mock_state.current_song = None
        mock_state.queue = []
        
        # 아무것도 없을 때 파일이 생성되지 않아야 함
        await save_music_states({12345: mock_state})
        assert not os.path.exists(temp_file)
        
        # 2. 재생 중인 곡이 있는 형태 구성
        mock_song = MagicMock()
        mock_song.webpage_url = "http://test.url"
        mock_song.title = "Test Song"
        mock_song.duration = 100
        mock_song.thumbnail = "thumb"
        mock_song.uploader = "Artist"
        mock_song.requester.id = 999
        
        mock_state.current_song = mock_song
        mock_state.get_current_playback_time.return_value = 50
        mock_state.volume = 0.5
        mock_state.loop_mode.name = "NONE"
        mock_state.auto_play_enabled = False
        mock_state.text_channel.id = 111
        mock_state.voice_client.channel.id = 222
        
        # 임시 파일 통째로 저장
        await save_music_states({12345: mock_state})
        
        # 저장 확인
        assert os.path.exists(temp_file)
        
        # 3. 로드 및 파일 삭제 처리 확인
        loaded_data = await load_music_states()
        
        # 데이터가 정상 로드되었는지 체크
        assert "12345" in loaded_data
        state_data = loaded_data["12345"]
        
        assert state_data["volume"] == 0.5
        assert state_data["loop_mode"] == "NONE"
        assert state_data["elapsed_seconds"] == 50
        assert state_data["current_song"]["title"] == "Test Song"
        assert state_data["text_channel_id"] == 111
        assert state_data["voice_channel_id"] == 222
        
        # 로드 후 원본 파일이 정상 삭제(`os.remove`)되었는지 검증
        assert not os.path.exists(temp_file)
        
    finally:
        # Restore original
        mu.MUSIC_STATE_FILE = original_file
