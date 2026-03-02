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
