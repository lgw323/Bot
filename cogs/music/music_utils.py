import asyncio
import json
import os
import re
from enum import Enum
import logging
import statistics
from collections import deque

import discord
import yt_dlp

logger = logging.getLogger("MusicCog")

# --- 상수 설정 ---
BOT_EMBED_COLOR = 0x2ECC71
FAVORITES_FILE = "data/favorites.json"
MUSIC_SETTINGS_FILE = "data/music_settings.json"
MUSIC_CHANNEL_ID = int(os.getenv("MUSIC_CHANNEL_ID", "0"))
URL_REGEX = re.compile(r'https?://(?:www\.)?(?:music\.youtube\.com|youtube\.com|youtu\.be)/.+')
TIMING_HISTORY_LIMIT = 10

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
favorites_lock = asyncio.Lock()
settings_lock = asyncio.Lock()

async def load_favorites():
    async with favorites_lock:
        if not os.path.exists(FAVORITES_FILE): return {}
        try:
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "_guild_settings" in data:
                    del data["_guild_settings"]
                return data
        except (json.JSONDecodeError, IOError):
            return {}

async def save_favorites(data):
    async with favorites_lock:
        with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

async def load_music_settings():
    async with settings_lock:
        if not os.path.exists(MUSIC_SETTINGS_FILE):
            return {}
        try:
            with open(MUSIC_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

async def save_music_settings(data):
    async with settings_lock:
        os.makedirs(os.path.dirname(MUSIC_SETTINGS_FILE), exist_ok=True)
        with open(MUSIC_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

async def update_request_timing(guild_id: int, task_type: str, new_duration_ms: int):
    guild_id_str = str(guild_id)
    settings = await load_music_settings()
    
    guild_settings = settings.setdefault(guild_id_str, {})
    timings_data = guild_settings.setdefault("request_timings", {})
    
    history = deque(timings_data.get(task_type, []), maxlen=TIMING_HISTORY_LIMIT)
    history.append(new_duration_ms)
    
    timings_data[task_type] = list(history)
    await save_music_settings(settings)
    logger.debug(f"[{guild_id_str}] Timing updated for '{task_type}': new duration {new_duration_ms}ms added.")

# [수정] get_network_stats 함수
def get_network_stats(settings: dict, guild_id: int) -> tuple[float | None, float | None]:
    """저장된 기록을 바탕으로 평균과 표준편차(변동폭)를 계산합니다."""
    guild_settings = settings.get(str(guild_id), {})
    timings_data = guild_settings.get("request_timings", {})
    
    # 'search', 'favorites', 'url' 기록을 모두 합쳐서 전체적인 네트워크 상태 평가
    all_timings = (
        timings_data.get("search", []) + 
        timings_data.get("favorites", []) + 
        timings_data.get("url", [])
    )
    
    # [수정] 통계 계산을 위해 최소 2개의 데이터가 필요
    if len(all_timings) < 2:
        return None, None 

    try:
        average = statistics.mean(all_timings)
        stdev = statistics.stdev(all_timings)
        return average, stdev
    except statistics.StatisticsError:
        # 데이터가 1개뿐일 경우 stdev 계산 시 오류가 발생할 수 있음
        return statistics.mean(all_timings), 0.0

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
