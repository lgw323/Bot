import asyncio
import json
import os
import re
from enum import Enum
import logging
from collections import deque

import discord
import yt_dlp

logger = logging.getLogger("MusicCog")

# --- 상수 설정 ---
BOT_EMBED_COLOR = 0x2ECC71
FAVORITES_FILE = "data/favorites.json"
MUSIC_SETTINGS_FILE = "data/music_settings.json"
MUSIC_CHANNEL_ID = int(os.getenv("MUSIC_CHANNEL_ID", "0"))
MASTER_USER_ID = int(os.getenv("MASTER_USER_ID", "0"))
URL_REGEX = re.compile(r'https?://(?:www\.)?(?:music\.youtube\.com|youtube\.com|youtu\.be)/.+')

# --- yt-dlp 및 FFmpeg 설정 ---
YTDL_OPTIONS = {
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
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn'
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# --- 데이터 관리 ---
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database_manager import (
    get_favorites as load_favorites,
    add_favorite,
    remove_favorites,
    get_music_settings as load_music_settings,
    update_music_volume,
    increment_play_count_db as increment_play_count,
    get_top_played_songs_db as get_top_played_songs
)

# 이전에 save_favorites, save_music_settings를 사용하던 코드는
# DB 직접 쓰기 방식으로 전부 마이그레이션 해야 하므로 가짜 함수 혹은 에러 발생기로 남김
async def save_favorites(data):
    raise NotImplementedError("Use database_manager functions directly instead of save_favorites")

async def save_music_settings(data):
    raise NotImplementedError("Use database_manager functions directly instead of save_music_settings")


# --- 열거형 및 데이터 클래스 ---
class LoopMode(Enum):
    NONE = 0
    SONG = 1
    QUEUE = 2

LOOP_MODE_DATA = {
    LoopMode.NONE: ("반복 없음", "🔁"),
    LoopMode.SONG: ("한 곡 반복", "🔂"),
    LoopMode.QUEUE: ("전체 반복", "🔁")
}

class Song:
    def __init__(self, data: dict, requester: discord.Member):
        self.webpage_url = data.get('webpage_url')
        self.stream_url = data.get('url')
        self.title = data.get('title', '알 수 없는 제목')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader', '알 수 없는 아티스트')
        self.requester = requester

    def to_embed(self, title_prefix=""):
        embed = discord.Embed(title=f"{title_prefix}{self.title}", color=BOT_EMBED_COLOR, url=self.webpage_url)
        if self.thumbnail: embed.set_thumbnail(url=self.thumbnail)
        minutes, seconds = divmod(self.duration, 60)
        embed.add_field(name="채널", value=self.uploader, inline=True)
        embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
        embed.set_footer(text=f"요청: {self.requester.display_name}", icon_url=self.requester.display_avatar.url)
        return embed