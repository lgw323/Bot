import asyncio
import hashlib
import logging
import os
import re
import shlex
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .music_utils import (
    Song,
    _find_deno_path,
    extract_info,
)


logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "download"
DEFAULT_CACHE_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_TRACK_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 180.0


class PlaybackPreparationCancelled(RuntimeError):
    """Raised when a user action cancels media preparation."""


class PlaybackPreparationError(RuntimeError):
    """Raised when yt-dlp cannot prepare a playable local media file."""


@dataclass(frozen=True)
class PreparedMedia:
    source: str
    before_options: str
    options: str = "-vn"
    stream_url: Optional[str] = None


class PlaybackBackend(ABC):
    name: str

    @abstractmethod
    async def prepare(self, song: Song, seek_time: int) -> PreparedMedia:
        """Prepare one FFmpeg input without changing queue state."""

    def cancel_current(self) -> bool:
        return False

    def discard(self, song: Song) -> None:
        return None

    async def close(self) -> None:
        return None


class DirectUrlPlaybackBackend(PlaybackBackend):
    """Compatibility backend preserving the original direct-CDN behavior."""

    name = "direct"

    async def prepare(self, song: Song, seek_time: int) -> PreparedMedia:
        data = await asyncio.to_thread(
            extract_info,
            song.webpage_url,
            download=False,
        )
        stream_url = data.get("url")
        if not stream_url:
            raise PlaybackPreparationError("스트림 URL을 찾을 수 없음")

        before_options = (
            "-reconnect 1 -reconnect_streamed 1 "
            "-reconnect_delay_max 5 -nostdin"
        )
        if seek_time > 0:
            before_options += f" -ss {seek_time}"

        headers = data.get("http_headers")
        if headers:
            header_string = "".join(
                f"{key}: {value}\r\n" for key, value in headers.items()
            )
            before_options += f" -headers {shlex.quote(header_string)}"

        return PreparedMedia(
            source=stream_url,
            before_options=before_options,
            stream_url=stream_url,
        )


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("%s 값이 정수가 아니어서 기본값을 사용합니다.", name)
        return default
    if value <= 0:
        logger.warning("%s 값이 0 이하라서 기본값을 사용합니다.", name)
        return default
    return value


class DownloadPlaybackBackend(PlaybackBackend):
    """Download bounded HTTP chunks, then let FFmpeg read a local file."""

    name = "download"

    def __init__(
        self,
        guild_id: int,
        *,
        cache_root: Optional[Path] = None,
        cache_max_bytes: Optional[int] = None,
        track_max_bytes: Optional[int] = None,
        cache_max_age_seconds: Optional[int] = None,
        download_timeout_seconds: Optional[float] = None,
    ) -> None:
        root = cache_root or (
            Path(tempfile.gettempdir()) / "discordbot_music_cache"
        )
        self.cache_dir = root / str(guild_id)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_max_bytes = cache_max_bytes or _positive_int_from_env(
            "MUSIC_CACHE_MAX_BYTES",
            DEFAULT_CACHE_MAX_BYTES,
        )
        self.track_max_bytes = track_max_bytes or _positive_int_from_env(
            "MUSIC_TRACK_MAX_BYTES",
            DEFAULT_TRACK_MAX_BYTES,
        )
        self.cache_max_age_seconds = (
            cache_max_age_seconds
            or _positive_int_from_env(
                "MUSIC_CACHE_MAX_AGE_SECONDS",
                DEFAULT_CACHE_MAX_AGE_SECONDS,
            )
        )
        self.download_timeout_seconds = (
            download_timeout_seconds or DEFAULT_DOWNLOAD_TIMEOUT_SECONDS
        )
        self._download_lock = asyncio.Lock()
        self._active_process: Optional[asyncio.subprocess.Process] = None
        self._cancel_requested = False

    def _cache_key(self, webpage_url: str) -> str:
        return hashlib.sha256(webpage_url.encode("utf-8")).hexdigest()

    def _media_candidates(self, cache_key: str) -> list[Path]:
        return sorted(
            (
                path
                for path in self.cache_dir.glob(f"{cache_key}.*")
                if path.is_file()
                and not path.name.endswith((".part", ".ytdl", ".tmp"))
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _remove_download_files(self, cache_key: str) -> None:
        for path in self.cache_dir.glob(f"{cache_key}.*"):
            path.unlink(missing_ok=True)

    def cleanup_cache(self, *, remove_all: bool = False) -> None:
        now = time.time()
        files: list[Path] = []
        for path in self.cache_dir.glob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                expired = now - stat.st_atime > self.cache_max_age_seconds
                partial = path.name.endswith((".part", ".ytdl", ".tmp"))
                if remove_all or expired or partial:
                    path.unlink(missing_ok=True)
                else:
                    files.append(path)
            except OSError as error:
                logger.warning("음악 cache 파일 정리 실패: %s", error)

        total_size = 0
        sized_files: list[tuple[Path, os.stat_result]] = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            total_size += stat.st_size
            sized_files.append((path, stat))

        for path, stat in sorted(sized_files, key=lambda item: item[1].st_atime):
            if total_size <= self.cache_max_bytes:
                break
            try:
                path.unlink(missing_ok=True)
                total_size -= stat.st_size
            except OSError as error:
                logger.warning("음악 cache 용량 정리 실패: %s", error)

        if remove_all:
            try:
                self.cache_dir.rmdir()
                self.cache_dir.parent.rmdir()
            except OSError:
                pass

    def _build_download_command(
        self,
        output_template: Path,
        *,
        player_client: str,
    ) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--quiet",
            "--no-warnings",
            "--no-progress",
            "--no-playlist",
            "--force-ipv4",
            "--max-filesize",
            str(self.track_max_bytes),
            "--format",
            "bestaudio[ext=opus]/bestaudio/best",
            "--output",
            str(output_template),
        ]

        deno_path = _find_deno_path()
        if deno_path:
            command.extend(("--js-runtimes", f"deno:{deno_path}"))

        command.extend(
            ("--extractor-args", f"youtube:player_client={player_client}")
        )

        # Read the URL from stdin so titles, IDs and query parameters do not
        # appear in the operating system process list.
        command.extend(("--batch-file", "-"))
        return command

    @staticmethod
    def _sanitize_error(raw_error: bytes) -> str:
        text = raw_error.decode("utf-8", errors="replace")
        text = re.sub(r"https?://\S+", "[URL 생략]", text)
        text = re.sub(
            r"(?<=\[youtube\] )[A-Za-z0-9_-]{11}",
            "[video-id]",
            text,
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return " | ".join(lines[-4:])[:800]

    async def _terminate_process(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def _download_once(
        self,
        webpage_url: str,
        output_template: Path,
        *,
        player_client: str,
    ) -> bytes:
        command = self._build_download_command(
            output_template,
            player_client=player_client,
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_process = process
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate((webpage_url + "\n").encode("utf-8")),
                timeout=self.download_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            await self._terminate_process(process)
            raise PlaybackPreparationError(
                f"음악 다운로드가 {self.download_timeout_seconds:.0f}초를 초과함"
            ) from error
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        finally:
            if self._active_process is process:
                self._active_process = None

        if self._cancel_requested:
            raise PlaybackPreparationCancelled("음악 다운로드가 취소됨")
        if process.returncode != 0:
            details = self._sanitize_error(stderr)
            raise PlaybackPreparationError(
                details or f"yt-dlp가 코드 {process.returncode}로 종료됨"
            )
        return stderr

    async def _download(self, webpage_url: str, cache_key: str) -> Path:
        output_template = self.cache_dir / f"{cache_key}.%(ext)s"
        last_error: Optional[PlaybackPreparationError] = None
        # These clients currently do not require a GVS PO Token. android_vr
        # cannot serve made-for-kids videos, while web_embedded cannot serve
        # videos whose owner disabled embedding, so each is the other's
        # deliberate compatibility fallback.
        for player_client in ("web_embedded", "android_vr"):
            self._remove_download_files(cache_key)
            try:
                await self._download_once(
                    webpage_url,
                    output_template,
                    player_client=player_client,
                )
                break
            except PlaybackPreparationCancelled:
                raise
            except PlaybackPreparationError as error:
                last_error = error
                logger.warning(
                    "YouTube %s client로 음악 준비 실패; 다음 client를 시도합니다.",
                    player_client,
                )
        else:
            assert last_error is not None
            raise last_error

        candidates = self._media_candidates(cache_key)
        if not candidates:
            raise PlaybackPreparationError(
                "yt-dlp가 성공했지만 완성된 음악 파일을 찾을 수 없음"
            )
        media_path = candidates[0]
        if media_path.stat().st_size <= 0:
            media_path.unlink(missing_ok=True)
            raise PlaybackPreparationError("다운로드한 음악 파일이 비어 있음")
        return media_path

    async def prepare(self, song: Song, seek_time: int) -> PreparedMedia:
        async with self._download_lock:
            self._cancel_requested = False
            self.cleanup_cache()
            cache_key = self._cache_key(song.webpage_url)
            candidates = self._media_candidates(cache_key)
            if candidates:
                media_path = candidates[0]
                try:
                    os.utime(media_path, None)
                except OSError:
                    pass
            else:
                media_path = await self._download(song.webpage_url, cache_key)
                self.cleanup_cache()
                if not media_path.exists():
                    raise PlaybackPreparationError(
                        "cache 제한 적용 중 준비된 음악 파일이 제거됨"
                    )

            if self._cancel_requested:
                raise PlaybackPreparationCancelled("음악 준비가 취소됨")

            before_options = "-nostdin"
            if seek_time > 0:
                before_options += f" -ss {seek_time}"
            return PreparedMedia(
                source=str(media_path),
                before_options=before_options,
            )

    def cancel_current(self) -> bool:
        process = self._active_process
        if process is None or process.returncode is not None:
            return False
        self._cancel_requested = True
        try:
            process.terminate()
        except ProcessLookupError:
            return False
        return True

    def discard(self, song: Song) -> None:
        self._remove_download_files(self._cache_key(song.webpage_url))

    async def close(self) -> None:
        process = self._active_process
        if process is not None:
            await self._terminate_process(process)
        await asyncio.to_thread(self.cleanup_cache, remove_all=True)


def create_playback_backend(guild_id: int) -> PlaybackBackend:
    backend_name = os.getenv("MUSIC_PLAYBACK_BACKEND", DEFAULT_BACKEND).lower()
    if backend_name == "direct":
        return DirectUrlPlaybackBackend()
    if backend_name != "download":
        logger.warning(
            "알 수 없는 MUSIC_PLAYBACK_BACKEND=%s; download를 사용합니다.",
            backend_name,
        )
    return DownloadPlaybackBackend(guild_id)
