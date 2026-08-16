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
POT_PROVIDER_PACKAGE: str = "bgutil-ytdlp-pot-provider"
POT_PROVIDER_VERSION: str = "1.3.1"

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

    def __init__(self) -> None:
        self.po_token_failed: bool = False

    def debug(self, message: str) -> None:
        logger.debug("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def info(self, message: str) -> None:
        logger.info("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def warning(self, message: str) -> None:
        lowered = message.lower()
        if "[pot]" in lowered and "po token" in lowered and any(
            marker in lowered
            for marker in ("error", "failed", "not available", "not provided", "unable")
        ):
            self.po_token_failed = True
        logger.warning("[yt-dlp] %s", _sanitize_ytdlp_message(message))

    def error(self, message: str) -> None:
        logger.error("[yt-dlp] %s", _sanitize_ytdlp_message(message))


YTDL_OPTIONS: Dict[str, Any] = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'noplaylist': False,
    'playlistend': 50,
    'quiet': True,
    'no_warnings': False,
    'ignoreerrors': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}
FFMPEG_OPTIONS: Dict[str, str] = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn'
}

def _get_pot_provider_home() -> Path:
    configured_path = os.getenv("YTDLP_POT_PROVIDER_DIR")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".local" / "share" / POT_PROVIDER_PACKAGE / "server"


def _get_package_version(package_name: str) -> Optional[str]:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _pot_provider_is_available() -> bool:
    server_home = _get_pot_provider_home()
    return bool(
        _find_deno_path()
        and _get_package_version(POT_PROVIDER_PACKAGE) == POT_PROVIDER_VERSION
        and (server_home / "src" / "generate_once.ts").is_file()
        and (server_home / "node_modules").is_dir()
    )


def build_ytdl_options(*, enable_po_token: bool = True) -> Dict[str, Any]:
    """Build request-local yt-dlp options with an optional PO Token provider."""

    options = copy.deepcopy(YTDL_OPTIONS)
    deno_path = _find_deno_path()
    options["logger"] = YtDlpLogBridge()
    options["js_runtimes"] = {
        "deno": {"path": deno_path} if deno_path else {},
    }

    if enable_po_token and _pot_provider_is_available():
        server_home = _get_pot_provider_home()
        options["extractor_args"] = {
            "youtube": {"player_client": ["mweb"]},
            "youtubepot-bgutilscript": {
                "server_home": [str(server_home)],
            },
        }

    return options


def _extract_info_once(
    query: str,
    *,
    download: bool = False,
    process: bool = True,
    enable_po_token: bool = True,
) -> Tuple[Any, YtDlpLogBridge]:
    options = build_ytdl_options(enable_po_token=enable_po_token)
    log_bridge = options["logger"]
    with yt_dlp.YoutubeDL(options) as downloader:
        result = downloader.extract_info(
            query,
            download=download,
            process=process,
        )
    return result, log_bridge


def extract_info(
    query: str,
    *,
    download: bool = False,
    process: bool = True,
) -> Any:
    """Extract one request with a fresh YouTube session and safe POT fallback.

    Long-lived YoutubeDL instances keep visitor and challenge state that can
    become invalid while the bot remains online. A request-scoped instance
    avoids requiring a process restart when YouTube rotates that state.
    """

    use_po_token = _pot_provider_is_available()
    result, log_bridge = _extract_info_once(
        query,
        download=download,
        process=process,
        enable_po_token=use_po_token,
    )
    if use_po_token and log_bridge.po_token_failed:
        logger.warning(
            "PO Token 생성에 실패하여 현재 yt-dlp 기본 추출 방식으로 폴백합니다."
        )
        result, _ = _extract_info_once(
            query,
            download=download,
            process=process,
            enable_po_token=False,
        )
    return result


def log_ytdlp_runtime_status() -> bool:
    """Log whether the supported YouTube JavaScript runtime is complete."""

    deno_path = _find_deno_path()
    ejs_version = _get_package_version("yt-dlp-ejs")
    pot_plugin_version = _get_package_version(POT_PROVIDER_PACKAGE)
    server_home = _get_pot_provider_home()
    pot_script = server_home / "src" / "generate_once.ts"
    pot_dependencies = server_home / "node_modules"

    if (
        not deno_path
        or not ejs_version
        or pot_plugin_version != POT_PROVIDER_VERSION
        or not pot_script.is_file()
        or not pot_dependencies.is_dir()
    ):
        missing = []
        if not deno_path:
            missing.append("Deno")
        if not ejs_version:
            missing.append("yt-dlp-ejs")
        if pot_plugin_version != POT_PROVIDER_VERSION:
            missing.append(f"{POT_PROVIDER_PACKAGE} {POT_PROVIDER_VERSION}")
        if not pot_script.is_file() or not pot_dependencies.is_dir():
            missing.append("PO Token 생성 스크립트")
        logger.error(
            "YouTube 재생 런타임이 불완전합니다: %s 누락. "
            "PO Token 없이 기존 추출 방식으로 폴백하며 HTTP 403이 발생할 수 있습니다.",
            ", ".join(missing),
        )
        return False

    logger.info(
        "YouTube 재생 런타임 확인 완료: Deno=%s, yt-dlp-ejs=%s, "
        "PO-Token=%s",
        deno_path,
        ejs_version,
        pot_plugin_version,
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
