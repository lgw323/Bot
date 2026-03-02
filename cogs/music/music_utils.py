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