import asyncio
from typing import Any

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
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

    def close_unscheduled_coroutine(coroutine: Any) -> MagicMock:
        coroutine.close()
        task = MagicMock()
        task.done.return_value = True
        return task

    bot.loop.create_task.side_effect = close_unscheduled_coroutine
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


@pytest.mark.asyncio
async def test_cleanup_waits_for_all_background_tasks(
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    bot = MagicMock()
    bot.loop = asyncio.get_running_loop()
    bot.wait_until_ready = AsyncMock()
    bot.is_closed.return_value = False
    state = MusicState(
        bot=bot,
        cog=mock_cog,
        guild=mock_guild,
    )
    autoplay_task = asyncio.create_task(asyncio.sleep(3600))
    ui_update_task = asyncio.create_task(asyncio.sleep(3600))
    state.autoplay_task = autoplay_task
    state.ui_update_task = ui_update_task
    state.now_playing_message = MagicMock()
    state.schedule_ui_update = AsyncMock()
    await asyncio.sleep(0)

    await state.cleanup(leave=True, update_ui=False)

    assert state.main_task is None
    assert state.autoplay_task is None
    assert state.ui_update_task is None
    assert autoplay_task.done()
    assert ui_update_task.done()
    state.schedule_ui_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_keeps_final_ui_update_for_user_disconnect(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    state = MusicState(
        bot=mock_bot,
        cog=mock_cog,
        guild=mock_guild,
    )
    state.now_playing_message = MagicMock()
    state.schedule_ui_update = AsyncMock()

    await state.cleanup(leave=True)

    state.schedule_ui_update.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cancel_autoplay_task_is_safe_and_idempotent(
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    bot = MagicMock()
    bot.loop = asyncio.get_running_loop()
    bot.wait_until_ready = AsyncMock()
    bot.is_closed.return_value = False
    state = MusicState(
        bot=bot,
        cog=mock_cog,
        guild=mock_guild,
    )
    autoplay_task = asyncio.create_task(asyncio.sleep(3600))
    state.autoplay_task = autoplay_task
    await asyncio.sleep(0)

    state.cancel_autoplay_task()
    state.cancel_autoplay_task()
    await asyncio.sleep(0)

    assert state.autoplay_task is None
    assert autoplay_task.done()
    assert autoplay_task.cancelled()
    await state.cleanup(leave=True, update_ui=False)


@pytest.mark.asyncio
async def test_cancelled_autoplay_task_cannot_clear_new_task_reference(
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    bot = MagicMock()
    bot.loop = asyncio.get_running_loop()
    bot.wait_until_ready = AsyncMock()
    bot.is_closed.return_value = False
    state = MusicState(
        bot=bot,
        cog=mock_cog,
        guild=mock_guild,
    )
    old_task = asyncio.create_task(asyncio.sleep(3600))
    state.autoplay_task = old_task
    state.cancel_autoplay_task()
    new_task = asyncio.create_task(asyncio.sleep(3600))
    state.autoplay_task = new_task
    await asyncio.sleep(0)

    assert old_task.cancelled()
    assert state.autoplay_task is new_task
    await state.cleanup(leave=True, update_ui=False)
