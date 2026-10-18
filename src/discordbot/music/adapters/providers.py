"""Cancellable yt-dlp/gTTS child processes; vendor objects never cross ports."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from discordbot.music.adapters.cache import DiskCache
from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.domain.model import Track
from discordbot.music.ports.playback import Media
from discordbot.platform.errors import AppError, CapacityError, DataIntegrityError, ExternalPermanentError, ValidationError


def provider_command() -> tuple[str, ...]:
    """Use the sealed interpreter/runtime; never fetch executable components live."""
    runtime = Path(sys.executable).with_name('deno.exe' if os.name == 'nt' else 'deno')
    return (sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-js-runtimes',
            '--js-runtimes', 'deno:'+str(runtime), '--no-remote-components')


def youtube_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in
            {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
            or parsed.username or parsed.password or parsed.port not in {None, 80, 443} or len(value) > 2048):
        raise ValidationError("unsupported Music URL")
    return value


class YtDlpProvider:
    def __init__(self, pool: ProcessPool) -> None:
        self.pool = pool

    async def lookup(self, query: str, requester_id: int, *, limit: int) -> tuple[Track, ...]:
        if not 1 <= limit <= 50 or not query or len(query) > 2048:
            raise ValidationError("invalid provider query")
        if not query.startswith(("ytsearch3:", "ytsearch10:")):
            youtube_url(query)
        output = await self.pool.run((*provider_command(), "--skip-download",
             "--dump-single-json", "--flat-playlist", "--no-warnings", "--playlist-end", str(limit), "--socket-timeout", "10",
             "--retries", "1", "--", query), seconds=30, name="lookup")
        try:
            data = json.loads(output)
            entries = data.get("entries", [data])
            if not isinstance(entries, list):
                raise ValueError
            result = []
            for entry in entries[:limit]:
                if not isinstance(entry, dict):
                    continue
                try:
                    url = youtube_url(entry.get("webpage_url") or entry.get("url", ""))
                    result.append(Track(uuid4().hex, url, entry["title"], int(entry.get("duration") or 0),
                                        requester_id, entry.get("uploader") or "", entry.get("thumbnail") or ""))
                except (KeyError, TypeError, ValueError, ValidationError):
                    continue
            return tuple(result)
        except (ValueError, AttributeError, TypeError):
            raise DataIntegrityError("yt-dlp metadata contract changed", context={'reason':'invalid_output'}) from None


class CachedMediaLibrary:
    def __init__(self, cache: DiskCache, pool: ProcessPool, *, direct_until: float | None = None) -> None:
        self.cache, self.pool = cache, pool
        if direct_until is not None and not 0 < direct_until - cache.clock.now().timestamp() <= 7 * 86400:
            raise ValueError("direct compatibility window must end within seven days")
        self.direct_until = direct_until

    async def _capture(self, arguments: tuple[str, ...], path: Path, maximum: int, seconds: float, name: str) -> None:
        try:
            target = await self.cache.executor.run_retained(lambda: path.open("xb"))
        except OSError:
            raise ExternalPermanentError('Music cache write failed', context={'reason':'cache_write_failure'}) from None
        written = 0
        async def consume(chunk: bytes) -> None:
            nonlocal written
            if written + len(chunk) > maximum:
                raise CapacityError("Music stream exceeded file limit", context={'reason':'output_limit'})
            written += len(chunk)
            try:
                await self.cache.executor.run_retained(target.write, chunk)
            except OSError:
                raise ExternalPermanentError('Music cache write failed', context={'reason':'cache_write_failure'}) from None
        try:
            await self.pool.run(arguments, seconds=seconds, name=name, consume=consume)
        finally:
            await self.cache.executor.run_retained(target.close)

    async def _direct(self, track: Track) -> Media:
        raw = await self.pool.run((*provider_command(), "--no-playlist", "--skip-download",
            "--dump-single-json", "--socket-timeout", "10", "--retries", "1", "-f", "bestaudio", "--", track.url),
            seconds=25, name="direct")
        try:
            value = json.loads(raw)["url"]
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".googlevideo.com")
                    or parsed.username or parsed.password or parsed.port not in {None, 443} or len(value) > 8192):
                raise ValueError
            return Media(value, "direct:" + uuid4().hex)
        except (ValueError, KeyError, TypeError):
            raise DataIntegrityError("invalid direct compatibility stream") from None

    async def acquire(self, track: Track) -> Media:
        youtube_url(track.url)

        async def produce(path: Path, maximum: int) -> None:
            await self._capture((*provider_command(), "--no-playlist",
                "--no-part", "--no-progress", "--no-warnings", "--quiet", "--max-filesize", str(maximum),
                "--socket-timeout", "10", "--retries", "1", "--fragment-retries", "1",
                "-f", "bestaudio[ext=m4a]/bestaudio", "-o", "-", "--", track.url), path, maximum, 60, "acquire")

        try:
            return await self.cache.acquire("music:" + track.url, produce)
        except AppError:
            if self.direct_until is not None and self.cache.clock.now().timestamp() < self.direct_until:
                return await self._direct(track)
            raise

    async def speech(self, text: str) -> Media:
        if not 0 < len(text) <= 200:
            raise ValidationError("invalid TTS text")

        async def produce(path: Path, maximum: int) -> None:
            # Source is loaded explicitly by the immutable launcher, not installed
            # in site-packages. A child does not inherit the parent's sys.path.
            # Run the colocated standalone worker with the same interpreter.
            await self._capture((sys.executable, "-I", "-B", str(Path(__file__).with_name("tts_worker.py")), text),
                                path, maximum, 20, "tts")

        return await self.cache.acquire("tts:" + text, produce)

    async def release(self, media: Media, *, corrupt: bool = False) -> None:
        await self.cache.release(media, corrupt=corrupt)
