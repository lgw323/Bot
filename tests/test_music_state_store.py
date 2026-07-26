import json
from unittest.mock import MagicMock, patch

import pytest

from cogs.music.music_state_store import MusicStateStore


def make_song(
    *,
    url: str,
    title: str,
    requester_id: int,
) -> MagicMock:
    song = MagicMock()
    song.webpage_url = url
    song.title = title
    song.duration = 180
    song.thumbnail = "thumbnail"
    song.uploader = "Artist"
    song.requester.id = requester_id
    return song


def make_music_state() -> MagicMock:
    state = MagicMock()
    state.current_song = make_song(
        url="https://youtube.com/watch?v=current",
        title="Current Song",
        requester_id=10,
    )
    state.queue = [
        make_song(
            url="https://youtube.com/watch?v=next",
            title="Next Song",
            requester_id=20,
        )
    ]
    state.get_current_playback_time.return_value = 47
    state.text_channel.id = 111
    state.voice_client.channel.id = 222
    state.volume = 0.35
    state.loop_mode.name = "QUEUE"
    state.auto_play_enabled = True
    return state


@pytest.mark.asyncio
async def test_store_preserves_existing_json_contract_and_loads_once(
    tmp_path,
) -> None:
    state_path = tmp_path / "music_state.json"
    store = MusicStateStore(state_path)

    await store.save({12345: make_music_state()})

    saved_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved_data == {
        "12345": {
            "text_channel_id": 111,
            "voice_channel_id": 222,
            "volume": 0.35,
            "loop_mode": "QUEUE",
            "auto_play_enabled": True,
            "current_song": {
                "webpage_url": "https://youtube.com/watch?v=current",
                "title": "Current Song",
                "duration": 180,
                "thumbnail": "thumbnail",
                "uploader": "Artist",
                "requester_id": 10,
            },
            "elapsed_seconds": 47,
            "queue": [
                {
                    "webpage_url": "https://youtube.com/watch?v=next",
                    "title": "Next Song",
                    "duration": 180,
                    "thumbnail": "thumbnail",
                    "uploader": "Artist",
                    "requester_id": 20,
                }
            ],
        }
    }

    assert await store.load_once() == saved_data
    assert not state_path.exists()


@pytest.mark.asyncio
async def test_failed_write_preserves_previous_snapshot(tmp_path) -> None:
    state_path = tmp_path / "music_state.json"
    previous_snapshot = '{"previous": "valid"}'
    state_path.write_text(previous_snapshot, encoding="utf-8")
    store = MusicStateStore(state_path)

    with patch(
        "cogs.music.music_state_store.json.dump",
        side_effect=OSError("disk write failed"),
    ):
        await store.save({12345: make_music_state()})

    assert state_path.read_text(encoding="utf-8") == previous_snapshot
    assert list(tmp_path.glob(".music_state.*.tmp")) == []


@pytest.mark.asyncio
async def test_invalid_json_is_kept_for_diagnosis(tmp_path) -> None:
    state_path = tmp_path / "music_state.json"
    state_path.write_text("{invalid json", encoding="utf-8")
    store = MusicStateStore(state_path)

    assert await store.load_once() == {}
    assert state_path.exists()


@pytest.mark.asyncio
async def test_empty_states_remove_previous_valid_snapshot(tmp_path) -> None:
    state_path = tmp_path / "music_state.json"
    state_path.write_text('{"12345": {"queue": []}}', encoding="utf-8")
    store = MusicStateStore(state_path)
    empty_state = MagicMock()
    empty_state.current_song = None
    empty_state.queue = []

    await store.save({12345: empty_state})

    assert not state_path.exists()


@pytest.mark.asyncio
async def test_empty_states_keep_invalid_snapshot_for_diagnosis(
    tmp_path,
) -> None:
    state_path = tmp_path / "music_state.json"
    state_path.write_text("{invalid json", encoding="utf-8")
    store = MusicStateStore(state_path)
    empty_state = MagicMock()
    empty_state.current_song = None
    empty_state.queue = []

    await store.save({12345: empty_state})

    assert state_path.read_text(encoding="utf-8") == "{invalid json"
