import asyncio
from collections import deque
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.music import music_core
from cogs.music.music_core import MusicState
from cogs.music.music_playback import PlaybackBackend
from cogs.music.music_session_restorer import MusicSessionRestorer
from cogs.music.music_state_store import serialize_music_states
from cogs.music.music_utils import LoopMode, Song


def _state() -> MusicState:
    bot = MagicMock()
    bot.user = None
    bot.loop = MagicMock()

    def close_unscheduled_coroutine(coroutine: Any) -> MagicMock:
        coroutine.close()
        task = MagicMock()
        task.done.return_value = True
        return task

    bot.loop.create_task.side_effect = close_unscheduled_coroutine
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.name = "테스트 서버"
    guild.me = MagicMock(spec=discord.Member)
    backend = MagicMock(spec=PlaybackBackend)
    state = MusicState(bot, MagicMock(), guild, playback_backend=backend)
    state.schedule_ui_update = AsyncMock()
    return state


def _song(title: str) -> Song:
    requester = MagicMock(spec=discord.Member)
    requester.id = 10
    requester.display_name = "테스터"
    return Song(
        {
            "webpage_url": f"https://youtube.invalid/{title}",
            "title": title,
            "duration": 180,
            "thumbnail": "thumbnail",
            "uploader": "Artist",
        },
        requester,
    )


def test_f022_f023_fr016_fr018_preserve_queue_and_loop_selection() -> None:
    """Features F022/F023; FR-016/FR-018; PRESERVE."""
    first, second = _song("first"), _song("second")

    state = _state()
    state.queue.extend([first, second])
    state.loop_mode = LoopMode.NONE
    assert state._select_next_song() is first
    assert list(state.queue) == [second]

    state.current_song = first
    state.loop_mode = LoopMode.SONG
    assert state._select_next_song() is first
    assert list(state.queue) == [second]

    state.loop_mode = LoopMode.QUEUE
    assert state._select_next_song() is second
    assert list(state.queue) == []


@pytest.mark.asyncio
async def test_f018_fr015_preserve_retry_3s_8s_then_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature F018; FR-015; PRESERVE."""
    state = _state()
    song = _song("retry")
    state.current_song = song
    state.text_channel = None
    monkeypatch.setattr(music_core.time, "monotonic", lambda: 100.0)

    await state._complete_playback(RuntimeError("first"))
    assert state.playback_retry_song is song
    assert state.playback_retry_not_before == 103.0
    assert list(state.queue) == [song]

    await state._complete_playback(RuntimeError("second"))
    assert state.playback_retry_song is song
    assert state.playback_retry_not_before == 108.0
    assert list(state.queue) == [song]

    await state._complete_playback(RuntimeError("third"))
    assert state.current_song is None
    assert state.playback_retry_song is None
    assert list(state.queue) == []
    assert state.consecutive_play_failures == 0


@pytest.mark.asyncio
async def test_f024_fr018_fr019_correct_autoplay_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature F024; FR-018/FR-019; CORRECT; never accepts V1 NameError."""
    state = _state()
    previous = _song("Previous Track")
    candidate = {
        "webpage_url": "https://youtube.invalid/recommended",
        "title": "Fresh Recommendation",
        "duration": 200,
        "thumbnail": "thumbnail",
        "uploader": "Artist",
    }

    def extract(query: str, *, download: bool, process: bool) -> dict:
        assert query == "ytsearch10:Artist"
        assert download is False
        assert process is True
        return {"entries": [candidate]}

    async def run_in_executor(_executor: object, callback: object) -> dict:
        return callback()  # type: ignore[operator]

    monkeypatch.setattr(music_core, "extract_ytdlp_info", extract, raising=False)
    monkeypatch.setattr(music_core.random, "choice", lambda values: values[0])
    monkeypatch.setattr(music_core.random, "random", lambda: 1.0)
    state.bot.loop.run_in_executor = run_in_executor

    await state._prefetch_autoplay_song(previous)

    assert len(state.queue) == 1
    assert state.queue[0].title == "Fresh Recommendation"
    assert state.queue[0].webpage_url == "https://youtube.invalid/recommended"
    assert state.autoplay_history == deque(["previous track"], maxlen=20)


@pytest.mark.asyncio
async def test_f024_fr019_correct_autoplay_provider_failure_is_local() -> None:
    """Feature F024; FR-019; CORRECT."""
    state = _state()
    previous = _song("Previous Track")

    async def run_in_executor(_executor: object, _callback: object) -> dict:
        raise TimeoutError("provider timeout")

    state.bot.loop.run_in_executor = run_in_executor
    await state._prefetch_autoplay_song(previous)

    assert list(state.queue) == []
    assert state.autoplay_history == deque(["previous track"], maxlen=20)


def test_f028_f045_fr024_fr025_preserve_snapshot_shape() -> None:
    """Features F028/F045; FR-024/FR-025; PRESERVE compatibility shape."""
    current, queued = _song("current"), _song("queued")
    state = SimpleNamespace(
        current_song=current,
        queue=deque([queued]),
        text_channel=SimpleNamespace(id=111),
        voice_client=SimpleNamespace(channel=SimpleNamespace(id=222)),
        volume=0.35,
        loop_mode=LoopMode.QUEUE,
        auto_play_enabled=True,
        get_current_playback_time=lambda: 47,
    )

    snapshot = serialize_music_states({123: state})["123"]

    assert list(snapshot) == [
        "text_channel_id",
        "voice_channel_id",
        "volume",
        "loop_mode",
        "auto_play_enabled",
        "current_song",
        "elapsed_seconds",
        "queue",
    ]
    assert snapshot["loop_mode"] == "QUEUE"
    assert snapshot["auto_play_enabled"] is True
    assert snapshot["elapsed_seconds"] == 47
    assert snapshot["current_song"]["requester_id"] == 10
    assert snapshot["queue"][0]["title"] == "queued"


@pytest.mark.asyncio
async def test_f028_fr024_preserve_restore_order_and_session_settings() -> None:
    """Feature F028; FR-024; PRESERVE compatibility reader."""
    bot = MagicMock()
    bot.get_channel.return_value = None
    guild = MagicMock(spec=discord.Guild)
    guild.name = "테스트 서버"
    guild.me = MagicMock(spec=discord.Member)
    guild.get_member.return_value = guild.me
    state = SimpleNamespace(
        volume=0.5,
        loop_mode=LoopMode.NONE,
        auto_play_enabled=False,
        seek_time=0,
        text_channel=None,
        queue=deque(),
        voice_client=None,
        play_next_song=asyncio.Event(),
    )
    data = {
        "volume": 0.35,
        "loop_mode": "QUEUE",
        "auto_play_enabled": True,
        "elapsed_seconds": 47,
        "voice_channel_id": None,
        "current_song": {
            "webpage_url": "https://youtube.invalid/current",
            "title": "current",
            "duration": 180,
            "uploader": "Artist",
            "requester_id": 10,
        },
        "queue": [
            {
                "webpage_url": "https://youtube.invalid/next",
                "title": "next",
                "duration": 180,
                "uploader": "Artist",
                "requester_id": 10,
            }
        ],
    }

    await MusicSessionRestorer(bot).restore(guild, state, data)

    assert state.volume == 0.35
    assert state.loop_mode is LoopMode.QUEUE
    assert state.auto_play_enabled is True
    assert state.seek_time == 47
    assert [song.title for song in state.queue] == ["current", "next"]


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: legacy snapshots without volume must use the single 0.5 default",
)
@pytest.mark.asyncio
async def test_f045_fr025_correct_legacy_snapshot_uses_half_volume_default() -> None:
    """Feature F045; FR-025; CORRECT."""
    bot = MagicMock()
    bot.get_channel.return_value = None
    guild = MagicMock(spec=discord.Guild)
    guild.name = "테스트 서버"
    state = SimpleNamespace(
        volume=0.5,
        loop_mode=LoopMode.NONE,
        auto_play_enabled=False,
        seek_time=0,
        text_channel=None,
        queue=deque(),
        voice_client=None,
        play_next_song=asyncio.Event(),
    )

    await MusicSessionRestorer(bot).restore(guild, state, {})

    assert state.volume == 0.5
