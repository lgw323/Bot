import asyncio
import json
import os
import re
from enum import Enum
import logging
from typing import Any, Dict, Optional, Tuple

import discord
import yt_dlp

from database_manager import (
    get_favorites as load_favorites,
    add_favorite,
    remove_favorites,
    get_music_settings as load_music_settings,
    update_music_volume,
    increment_play_count_db as increment_play_count,
    get_top_played_songs_db as get_top_played_songs
)

# --- 로깅 설정 ---
logger: logging.Logger = logging.getLogger(__name__)

# --- 상수 설정 ---
BOT_EMBED_COLOR: int = 0x2ECC71
FAVORITES_FILE: str = "data/favorites.json"
MUSIC_SETTINGS_FILE: str = "data/music_settings.json"
MUSIC_CHANNEL_ID: int = int(os.getenv("MUSIC_CHANNEL_ID", "0"))
MASTER_USER_ID: int = int(os.getenv("MASTER_USER_ID", "0"))
URL_REGEX: re.Pattern = re.compile(r'https?://(?:www\.)?(?:music\.youtube\.com|youtube\.com|youtu\.be)/.+')

# --- yt-dlp 및 FFmpeg 설정 ---
YTDL_OPTIONS: Dict[str, Any] = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'noplaylist': False,
    'playlistend': 50,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.5',
    }
}
FFMPEG_OPTIONS: Dict[str, str] = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn'
}
ytdl: yt_dlp.YoutubeDL = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# --- 열거형 및 데이터 클래스 ---
class LoopMode(Enum):
    NONE = 0
    SONG = 1
    QUEUE = 2

LOOP_MODE_DATA: Dict[LoopMode, Tuple[str, str]] = {
    LoopMode.NONE: ("반복 없음", "🔁"),
    LoopMode.SONG: ("한 곡 반복", "🔂"),
    LoopMode.QUEUE: ("전체 반복", "🔁")
}

class Song:
    def __init__(self, data: Dict[str, Any], requester: discord.Member) -> None:
        self.webpage_url: Optional[str] = data.get('webpage_url')
        self.stream_url: Optional[str] = data.get('url')
        self.title: str = data.get('title', '알 수 없는 제목')
        self.duration: int = data.get('duration', 0)
        self.thumbnail: Optional[str] = data.get('thumbnail')
        self.uploader: str = data.get('uploader', '알 수 없는 아티스트')
        self.requester: discord.Member = requester

    def to_embed(self, title_prefix: str = "") -> discord.Embed:
        embed: discord.Embed = discord.Embed(
            title=f"{title_prefix}{self.title}",
            color=BOT_EMBED_COLOR,
            url=self.webpage_url
        )
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        minutes, seconds = divmod(self.duration, 60)
        embed.add_field(name="채널", value=self.uploader, inline=True)
        embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
        embed.set_footer(
            text=f"요청: {self.requester.display_name}",
            icon_url=self.requester.display_avatar.url if self.requester.display_avatar else None
        )
        return embed

# --- 오디오 세션 복원(State Saver) 관련 함수 선언 ---
MUSIC_STATE_FILE: str = "data/music_state.json"

async def save_music_states(states_dict: Dict[int, Any]) -> None:
    """각 길드별 현재 MusicState를 추려 디스크에 임시 저장(Overwrite/Truncate)합니다."""
    # 삭제(os.remove) 후 생성 방식은 파일 시스템 메타데이터 변경을 수반하므로, 단순히 열어 내용만 덮어쓰는(Truncate, 'w' 모드) 방식이 SD카드 I/O 및 블록 덮어쓰기에 있어 아주 미세하게 더 효율적입니다.
    def _save() -> None:
        try:
            os.makedirs(os.path.dirname(MUSIC_STATE_FILE), exist_ok=True)
            export_data = {}
            for guild_id, state in states_dict.items():
                if not state.current_song and not state.queue:
                    continue # 재생 중인게 없으면 스킵

                # 현재 위치 (초)
                elapsed_seconds = state.get_current_playback_time()
                
                # 큐 직렬화 (간소화된 딕셔너리로 저장)
                queue_data = []
                for song in state.queue:
                    queue_data.append({
                        'webpage_url': song.webpage_url,
                        'title': song.title,
                        'duration': song.duration,
                        'thumbnail': song.thumbnail,
                        'uploader': song.uploader,
                        'requester_id': song.requester.id
                    })
                
                current_song_data = None
                if state.current_song:
                    current_song_data = {
                        'webpage_url': state.current_song.webpage_url,
                        'title': state.current_song.title,
                        'duration': state.current_song.duration,
                        'thumbnail': state.current_song.thumbnail,
                        'uploader': state.current_song.uploader,
                        'requester_id': state.current_song.requester.id
                    }

                export_data[str(guild_id)] = {
                    'text_channel_id': state.text_channel.id if state.text_channel else None,
                    'voice_channel_id': state.voice_client.channel.id if state.voice_client and state.voice_client.channel else None,
                    'volume': state.volume,
                    'loop_mode': state.loop_mode.name,
                    'auto_play_enabled': state.auto_play_enabled,
                    'current_song': current_song_data,
                    'elapsed_seconds': elapsed_seconds,
                    'queue': queue_data
                }
            
            if export_data:
                with open(MUSIC_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False)
                logger.info(f"Music states saved to {MUSIC_STATE_FILE}")
                
        except Exception as e:
            logger.error(f"Failed to save music states: {e}")

    await asyncio.to_thread(_save)

async def load_music_states() -> Dict[str, Any]:
    """저장된 MusicState JSON을 읽어오고 파일을 삭제합니다."""
    def _load_and_delete() -> Dict[str, Any]:
        try:
            if not os.path.exists(MUSIC_STATE_FILE):
                return {}
                
            with open(MUSIC_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 읽었으면 일회성 스냅샷이므로 제거 (디스크 정리)
            try:
                os.remove(MUSIC_STATE_FILE)
            except Exception as e:
                logger.warning(f"Failed to delete state file: {e}")
                
            return data
        except Exception as e:
            logger.error(f"Failed to load music states: {e}")
            return {}

    return await asyncio.to_thread(_load_and_delete)