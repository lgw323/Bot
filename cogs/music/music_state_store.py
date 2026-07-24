import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping


logger: logging.Logger = logging.getLogger(__name__)

DEFAULT_MUSIC_STATE_FILE = Path("data/music_state.json")


def _serialize_song(song: Any) -> Dict[str, Any]:
    return {
        "webpage_url": song.webpage_url,
        "title": song.title,
        "duration": song.duration,
        "thumbnail": song.thumbnail,
        "uploader": song.uploader,
        "requester_id": song.requester.id,
    }


def serialize_music_states(
    states: Mapping[int, Any],
) -> Dict[str, Dict[str, Any]]:
    """Convert active music sessions to the existing JSON contract."""
    export_data: Dict[str, Dict[str, Any]] = {}

    for guild_id, state in states.items():
        if not state.current_song and not state.queue:
            continue

        current_song = (
            _serialize_song(state.current_song)
            if state.current_song
            else None
        )
        export_data[str(guild_id)] = {
            "text_channel_id": (
                state.text_channel.id if state.text_channel else None
            ),
            "voice_channel_id": (
                state.voice_client.channel.id
                if state.voice_client and state.voice_client.channel
                else None
            ),
            "volume": state.volume,
            "loop_mode": state.loop_mode.name,
            "auto_play_enabled": state.auto_play_enabled,
            "current_song": current_song,
            "elapsed_seconds": state.get_current_playback_time(),
            "queue": [_serialize_song(song) for song in state.queue],
        }

    return export_data


class MusicStateStore:
    """Persist one-use music restart snapshots independently of playback."""

    def __init__(
        self,
        state_file: Path = DEFAULT_MUSIC_STATE_FILE,
    ) -> None:
        self.state_file = Path(state_file)

    def _save(self, states: Mapping[int, Any]) -> None:
        temp_path: Path | None = None

        try:
            export_data = serialize_music_states(states)
            if not export_data:
                return

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.state_file.parent,
                prefix=f".{self.state_file.stem}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(export_data, temp_file, ensure_ascii=False)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, self.state_file)
            temp_path = None
            logger.info("Music states saved to %s", self.state_file)
        except Exception as e:
            logger.error("Failed to save music states: %s", e)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    async def save(self, states: Mapping[int, Any]) -> None:
        await asyncio.to_thread(self._save, states)

    def _load_once(self) -> Dict[str, Any]:
        try:
            if not self.state_file.exists():
                return {}

            with self.state_file.open("r", encoding="utf-8") as state_file:
                data = json.load(state_file)

            try:
                self.state_file.unlink()
            except Exception as e:
                logger.warning("Failed to delete state file: %s", e)

            return data
        except Exception as e:
            logger.error("Failed to load music states: %s", e)
            return {}

    async def load_once(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._load_once)
