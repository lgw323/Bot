import asyncio
import logging
import subprocess
import time
from typing import Any

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from cogs.music.music_core import (
    ErrorAwarePCMVolumeTransformer,
    MusicState,
)
from cogs.music.music_playback import PlaybackBackend, PreparedMedia
from cogs.music.music_utils import LoopMode

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


def test_volume_transformer_exposes_wrapped_ffmpeg_error() -> None:
    class FakeAudioSource(discord.AudioSource):
        def read(self) -> bytes:
            return b""

    source = FakeAudioSource()
    source._current_error = RuntimeError("FFmpeg exited with code 8")
    transformer = ErrorAwarePCMVolumeTransformer(source, volume=0.5)

    assert transformer._current_error is source._current_error


def test_volume_transformer_detects_delayed_ffmpeg_failure_at_eof() -> None:
    class DelayedExitProcess:
        def __init__(self) -> None:
            self.wait_calls = 0

        def wait(self, timeout: float) -> int:
            self.wait_calls += 1
            assert timeout > 0
            return 8

    class FakeFFmpegSource(discord.AudioSource):
        def __init__(self) -> None:
            self._current_error = None
            self._stopped = False
            self._process = DelayedExitProcess()

        def read(self) -> bytes:
            # FFmpeg stdout can reach EOF just before poll() observes its exit.
            return b""

    source = FakeFFmpegSource()
    transformer = ErrorAwarePCMVolumeTransformer(source, volume=0.5)

    assert transformer.read() == b""
    assert source._process.wait_calls == 1
    assert transformer._current_error is not None
    assert "code 8" in str(transformer._current_error)


def test_volume_transformer_does_not_fail_for_clean_ffmpeg_exit() -> None:
    process = MagicMock()
    process.wait.return_value = 0

    class FakeFFmpegSource(discord.AudioSource):
        def __init__(self) -> None:
            self._current_error = None
            self._stopped = False
            self._process = process

        def read(self) -> bytes:
            return b""

    source = FakeFFmpegSource()
    transformer = ErrorAwarePCMVolumeTransformer(source, volume=0.5)

    assert transformer.read() == b""
    assert transformer._current_error is None


def test_volume_transformer_treats_ffmpeg_eof_timeout_as_failure() -> None:
    process = MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", timeout=1.0)

    class FakeFFmpegSource(discord.AudioSource):
        def __init__(self) -> None:
            self._current_error = None
            self._stopped = False
            self._process = process

        def read(self) -> bytes:
            return b""

    source = FakeFFmpegSource()
    transformer = ErrorAwarePCMVolumeTransformer(source, volume=0.5)

    assert transformer.read() == b""
    assert transformer._current_error is not None
    assert "did not exit" in str(transformer._current_error)


@pytest.mark.asyncio
async def test_playback_error_requeues_song_for_fresh_extraction(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MagicMock(spec=PlaybackBackend)
    state = MusicState(
        mock_bot,
        mock_cog,
        mock_guild,
        playback_backend=backend,
    )
    song = MagicMock()
    state.current_song = song
    state.loop_mode = LoopMode.NONE
    monkeypatch.setattr("cogs.music.music_core.time.monotonic", lambda: 100.0)

    with caplog.at_level(logging.ERROR):
        await state._complete_playback(
            RuntimeError("FFmpeg exited with code 8"),
            "HTTP error 403 Forbidden",
        )

    assert state.consecutive_play_failures == 1
    assert list(state.queue) == [song]
    assert state.play_next_song.is_set()
    assert state.playback_retry_song is song
    assert state.playback_retry_not_before == 103.0
    assert "3초" in state.current_task
    assert "자동 재시도" in caplog.text
    assert "403 Forbidden" in caplog.text
    backend.discard.assert_called_once_with(song)


@pytest.mark.asyncio
async def test_second_playback_failure_uses_longer_backoff(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = MusicState(mock_bot, mock_cog, mock_guild)
    song = MagicMock()
    song.webpage_url = "https://example.invalid/second-failure"
    state.current_song = song
    state.queue.append(song)
    state.consecutive_play_failures = 1
    monkeypatch.setattr("cogs.music.music_core.time.monotonic", lambda: 200.0)

    await state._complete_playback(RuntimeError("code 8"), "403 Forbidden")

    assert state.consecutive_play_failures == 2
    assert state.playback_retry_song is song
    assert state.playback_retry_not_before == 208.0
    assert list(state.queue) == [song]
    assert "8초" in state.current_task


@pytest.mark.asyncio
async def test_playback_loop_waits_for_retry_deadline(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = MusicState(mock_bot, mock_cog, mock_guild)
    song = MagicMock()
    state.playback_retry_song = song
    state.playback_retry_not_before = 103.0
    monkeypatch.setattr("cogs.music.music_core.time.monotonic", lambda: 100.0)

    async def timeout_after_delay(awaitable: Any, timeout: float) -> None:
        awaitable.close()
        assert timeout == 3.0
        raise TimeoutError

    monkeypatch.setattr(
        "cogs.music.music_core.asyncio.wait_for",
        timeout_after_delay,
    )

    assert await state._wait_for_playback_retry(song) is True
    assert state.playback_retry_song is None
    assert state.playback_retry_not_before == 0.0


@pytest.mark.asyncio
async def test_pending_retry_can_be_skipped_immediately(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    state = MusicState(mock_bot, mock_cog, mock_guild)
    song = MagicMock()
    state.current_song = song
    state.queue.append(song)
    state.consecutive_play_failures = 1
    state.playback_retry_song = song
    state.playback_retry_not_before = time.monotonic() + 8.0

    assert state.cancel_pending_playback_retry() is True
    assert state.current_song is None
    assert list(state.queue) == []
    assert state.consecutive_play_failures == 0
    assert state.playback_retry_cancelled.is_set()
    assert state.play_next_song.is_set()


def test_pending_retry_selection_ignores_loop_mode_changes(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    state = MusicState(mock_bot, mock_cog, mock_guild)
    retry_song = MagicMock()
    another_song = MagicMock()
    state.current_song = retry_song
    state.queue.extend([retry_song, another_song])
    state.playback_retry_song = retry_song
    state.loop_mode = LoopMode.SONG

    assert state._select_next_song() is retry_song
    assert list(state.queue) == [another_song]


def test_active_download_preparation_can_be_skipped(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    backend = MagicMock(spec=PlaybackBackend)
    state = MusicState(
        mock_bot,
        mock_cog,
        mock_guild,
        playback_backend=backend,
    )
    song = MagicMock()
    state.current_song = song
    state.preparing_song = song

    assert state.cancel_active_preparation() is True
    assert state.preparation_skipped_song is song
    backend.cancel_current.assert_called_once_with()


@pytest.mark.asyncio
async def test_play_loop_uses_prepared_backend_media(
    mock_guild: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = MagicMock()
    bot.loop = asyncio.get_running_loop()
    bot.wait_until_ready = AsyncMock()
    bot.is_closed.side_effect = [False, True]
    cog = MagicMock()
    cog.cleanup_channel_messages = AsyncMock()
    backend = MagicMock(spec=PlaybackBackend)
    backend.prepare = AsyncMock(
        return_value=PreparedMedia(
            source="/tmp/cached-track.webm",
            before_options="-nostdin -ss 14",
        )
    )
    backend.close = AsyncMock()
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    song = MagicMock()
    song.webpage_url = "https://example.invalid/watch"
    song.title = "Track"
    fake_ffmpeg_source = MagicMock()
    fake_volume_source = MagicMock()
    ffmpeg_constructor = MagicMock(return_value=fake_ffmpeg_source)
    volume_constructor = MagicMock(return_value=fake_volume_source)
    increment_play_count = AsyncMock()
    monkeypatch.setattr(
        "cogs.music.music_core.discord.FFmpegPCMAudio",
        ffmpeg_constructor,
    )
    monkeypatch.setattr(
        "cogs.music.music_core.ErrorAwarePCMVolumeTransformer",
        volume_constructor,
    )
    monkeypatch.setattr(
        "cogs.music.music_core.increment_play_count",
        increment_play_count,
    )

    state = MusicState(
        bot,
        cog,
        mock_guild,
        playback_backend=backend,
    )
    state.voice_client = voice_client
    state.seek_time = 14
    state.schedule_ui_update = AsyncMock()
    state.queue.append(song)
    await asyncio.sleep(0)
    state.play_next_song.set()
    assert state.main_task is not None
    await state.main_task
    await asyncio.sleep(0)

    backend.prepare.assert_awaited_once_with(song, 14)
    ffmpeg_constructor.assert_called_once_with(
        "/tmp/cached-track.webm",
        stderr=state.ffmpeg_stderr,
        before_options="-nostdin -ss 14",
        options="-vn",
    )
    voice_client.play.assert_called_once()
    assert voice_client.play.call_args.args[0] is fake_volume_source


@pytest.mark.asyncio
async def test_third_playback_error_skips_song_and_notifies_channel(
    mock_bot: MagicMock,
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    state = MusicState(mock_bot, mock_cog, mock_guild)
    song = MagicMock()
    song.webpage_url = "https://example.invalid/third-failure"
    state.current_song = song
    state.queue.append(song)
    state.consecutive_play_failures = 2
    state.text_channel = AsyncMock()

    await state._complete_playback(
        RuntimeError("FFmpeg exited with code 8"),
        "HTTP error 403 Forbidden",
    )

    assert state.current_song is None
    assert list(state.queue) == []
    assert state.consecutive_play_failures == 0
    state.text_channel.send.assert_awaited_once()


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
async def test_ui_update_burst_is_coalesced(
    mock_cog: MagicMock,
    mock_guild: MagicMock,
) -> None:
    bot = MagicMock()
    bot.loop = asyncio.get_running_loop()
    bot.wait_until_ready = AsyncMock()
    bot.is_closed.return_value = False
    state = MusicState(bot=bot, cog=mock_cog, guild=mock_guild)
    state.UI_UPDATE_COOLDOWN = 0.0
    state._execute_ui_update = AsyncMock()

    await state.schedule_ui_update()
    await state.schedule_ui_update()
    await state.schedule_ui_update()
    update_task = state.ui_update_task
    assert update_task is not None
    await update_task

    state._execute_ui_update.assert_awaited_once_with()
    assert state.ui_update_task is None
    await state.cleanup(leave=True, update_ui=False)


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
