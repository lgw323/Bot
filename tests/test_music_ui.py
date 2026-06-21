import pytest
import discord
from unittest.mock import MagicMock
from cogs.music.music_ui import SearchSelect, QueueManagementView

def test_search_select_initialization() -> None:
    mock_cog = MagicMock()
    
    search_results = [
        {"title": "Test Title 1", "uploader": "Test Uploader 1", "duration": 185},
        {"title": "Test Title 2", "uploader": "Test Uploader 2", "duration": 220}
    ]
    
    select = SearchSelect(cog=mock_cog, search_results=search_results)
    
    assert len(select.options) == 2
    assert select.options[0].label == "Test Title 1"
    assert "3:05" in select.options[0].description
    
    assert select.options[1].label == "Test Title 2"
    assert "3:40" in select.options[1].description

@pytest.mark.asyncio
async def test_queue_management_view_initialization() -> None:
    mock_cog = MagicMock()
    mock_state = MagicMock()
    mock_state.queue = [MagicMock(), MagicMock(), MagicMock()] # mock 3 songs
    
    view = QueueManagementView(cog=mock_cog, state=mock_state)
    
    assert len(view.children) > 0
    # QueueSelect, move_top_button, remove_button, shuffle_button, clear_button
    assert len(view.children) == 5

def test_music_player_view_initialization() -> None:
    from cogs.music.music_ui import MusicPlayerView
    from cogs.music.music_utils import LoopMode
    mock_cog = MagicMock()
    mock_state = MagicMock()
    mock_state.voice_client = MagicMock()
    mock_state.voice_client.is_paused.return_value = False
    mock_state.current_song = MagicMock()
    mock_state.loop_mode = LoopMode.NONE
    mock_state.auto_play_enabled = False
    
    top_songs = [
        {"url": "https://url1", "title": "Top 1", "count": 10},
        {"url": "https://url2", "title": "Top 2", "count": 5},
        {"url": "https://url3", "title": "Top 3", "count": 2}
    ]
    
    view = MusicPlayerView(cog=mock_cog, state=mock_state, top_songs=top_songs)
    
    # 5 (Row 0) + 4 (Row 1) + 3 (Row 2, 3, 4 top songs) = 12 buttons
    assert len(view.children) == 12
    
    labels = [child.label for child in view.children if isinstance(child, discord.ui.Button) and child.label]
    assert "노래 검색" in labels
    assert "시청방" not in labels
    assert "요약" not in labels
    assert "내 정보" not in labels
    assert "랭킹" not in labels
    assert "생일 목록" not in labels
