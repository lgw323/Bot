import copy
import logging
import os
import re
import shutil
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import discord
import yt_dlp

from .music_state_store import (
    DEFAULT_MUSIC_STATE_FILE,
    MusicStateStore,
)
from database_manager import (
    get_favorites as load_favorites,
    add_favorite,
    remove_favorites,
    get_music_settings as load_music_settings,
    update_music_volume,
    increment_play_count_db as increment_play_count,
    get_top_played_songs_db as get_top_played_songs
)

# --- 상수 설정 ---
logger: logging.Logger = logging.getLogger(__name__)
BOT_EMBED_COLOR: int = 0x2ECC71
MUSIC_CHANNEL_ID: int = int(os.getenv("MUSIC_CHANNEL_ID", "0"))
MASTER_USER_ID: int = int(os.getenv("MASTER_USER_ID", "0"))
URL_REGEX: re.Pattern = re.compile(r'https?://(?:www\.)?(?:music\.youtube\.com|youtube\.com|youtu\.be)/.+')

# --- yt-dlp 및 FFmpeg 설정 ---
def _find_deno_path() -> Optional[str]:
    system_path = shutil.which("deno")
    if system_path:
        return system_path

    user_path = Path.home() / ".local" / "bin" / "deno"
    if user_path.is_file() and os.access(user_path, os.X_OK):
        return str(user_path)
    return None


def _sanitize_ytdlp_message(message: str) -> str:
    sanitized = re.sub(r"https?://\S+", "[URL 생략]", message)
    return re.sub(
        r"(?<=\[youtube\] )[A-Za-z0-9_-]{11}",
        "[video-id]",
        sanitized,
    )


class YtDlpLogBridge:
    """Route yt-dlp diagnostics through the bot logger without media URLs."""

    def debug(self, message: str) -> None:
        logger.debug("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def info(self, message: str) -> None:
        logger.info("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def warning(self, message: str) -> None:
        logger.warning("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def error(self, message: str) -> None:
        logger.error("[yt-dlp] %s", _sanitize_ytdlp_message(message))


_DENO_PATH = _find_deno_path()

YTDL_OPTIONS: Dict[str, Any] = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'noplaylist': False,
    'playlistend': 50,
    'quiet': True,
    'no_warnings': False,
    'ignoreerrors': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.5',
    },
    'logger': YtDlpLogBridge(),
    'js_runtimes': {
        'deno': {'path': _DENO_PATH} if _DENO_PATH else {},
    },
}
FFMPEG_OPTIONS: Dict[str, str] = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn'
}

def extract_info(
    query: str,
    *,
    download: bool = False,
    process: bool = True,
) -> Any:
    """Extract one request with a fresh YouTube session.

    Long-lived YoutubeDL instances keep visitor and challenge state that can
    become invalid while the bot remains online. A request-scoped instance
    avoids requiring a process restart when YouTube rotates that state.
    """

    with yt_dlp.YoutubeDL(copy.deepcopy(YTDL_OPTIONS)) as downloader:
        return downloader.extract_info(
            query,
            download=download,
            process=process,
        )


def log_ytdlp_runtime_status() -> bool:
    """Log whether the supported YouTube JavaScript runtime is complete."""

    deno_path = _find_deno_path()
    try:
        ejs_version = version("yt-dlp-ejs")
    except PackageNotFoundError:
        ejs_version = None

    if not deno_path or not ejs_version:
        missing = []
        if not deno_path:
            missing.append("Deno")
        if not ejs_version:
            missing.append("yt-dlp-ejs")
        logger.error(
            "YouTube 재생 런타임이 불완전합니다: %s 누락. "
            "YouTube 스트림이 HTTP 403으로 종료될 수 있습니다.",
            ", ".join(missing),
        )
        return False

    logger.info(
        "YouTube 재생 런타임 확인 완료: Deno=%s, yt-dlp-ejs=%s",
        deno_path,
        ejs_version,
    )
    return True

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

# 기존 import 경로를 사용하는 코드와 테스트를 위한 호환 연결부입니다.
MUSIC_STATE_FILE: str = str(DEFAULT_MUSIC_STATE_FILE)


async def save_music_states(states_dict: Dict[int, Any]) -> None:
    await MusicStateStore(MUSIC_STATE_FILE).save(states_dict)


async def load_music_states() -> Dict[str, Any]:
    return await MusicStateStore(MUSIC_STATE_FILE).load_once()
