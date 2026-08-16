from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

import pytest

import cogs.music.music_playback as music_playback
from cogs.music.music_playback import (
    DirectUrlPlaybackBackend,
    DownloadPlaybackBackend,
    PlaybackPreparationError,
)


@pytest.mark.asyncio
async def test_direct_backend_preserves_headers_and_seek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    song = MagicMock()
    song.webpage_url = "https://example.invalid/watch"
    monkeypatch.setattr(
        music_playback,
        "extract_info",
        lambda *args, **kwargs: {
            "url": "https://media.invalid/audio",
            "http_headers": {"User-Agent": "test-agent"},
        },
    )

    prepared = await DirectUrlPlaybackBackend().prepare(song, 37)

    assert prepared.source == "https://media.invalid/audio"
    assert prepared.stream_url == prepared.source
    assert "-ss 37" in prepared.before_options
    assert "User-Agent: test-agent" in prepared.before_options
    assert "-reconnect 1" in prepared.before_options


def test_download_command_uses_exempt_client_without_url_in_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = DownloadPlaybackBackend(1, cache_root=tmp_path)
    monkeypatch.setattr(music_playback, "_find_deno_path", lambda: None)
    command = backend._build_download_command(
        tmp_path / "track.%(ext)s",
        player_client="android_vr",
    )

    assert "--http-chunk-size" not in command
    assert "--force-ipv4" in command
    extractor_arg = command[command.index("--extractor-args") + 1]
    assert extractor_arg == "youtube:player_client=android_vr"
    assert command[-2:] == ["--batch-file", "-"]
    assert not any("youtube.com" in argument for argument in command)


@pytest.mark.asyncio
async def test_download_backend_reuses_completed_cache_and_supports_seek(
    tmp_path: Path,
) -> None:
    backend = DownloadPlaybackBackend(7, cache_root=tmp_path)
    song = MagicMock()
    song.webpage_url = "https://example.invalid/watch?v=safe"
    cache_key = backend._cache_key(song.webpage_url)
    cached_file = backend.cache_dir / f"{cache_key}.webm"
    cached_file.write_bytes(b"test media")
    backend._download = MagicMock()

    prepared = await backend.prepare(song, 12)

    assert prepared.source == str(cached_file)
    assert prepared.before_options == "-nostdin -ss 12"
    backend._download.assert_not_called()
    await backend.close()


def test_cache_cleanup_removes_oldest_files_over_limit(tmp_path: Path) -> None:
    backend = DownloadPlaybackBackend(
        9,
        cache_root=tmp_path,
        cache_max_bytes=5,
        cache_max_age_seconds=3600,
    )
    oldest = backend.cache_dir / "old.webm"
    newest = backend.cache_dir / "new.webm"
    oldest.write_bytes(b"1234")
    newest.write_bytes(b"5678")
    oldest.touch()
    newest.touch()
    oldest_stat = oldest.stat()
    newest_stat = newest.stat()
    # atime determines eviction order; preserve a current mtime.
    import os

    os.utime(oldest, (oldest_stat.st_atime - 10, oldest_stat.st_mtime))
    os.utime(newest, (newest_stat.st_atime, newest_stat.st_mtime))

    backend.cleanup_cache()

    assert not oldest.exists()
    assert newest.exists()


def test_discard_removes_only_requested_song_cache(tmp_path: Path) -> None:
    backend = DownloadPlaybackBackend(11, cache_root=tmp_path)
    requested_song = MagicMock()
    requested_song.webpage_url = "https://example.invalid/requested"
    other_song = MagicMock()
    other_song.webpage_url = "https://example.invalid/other"
    requested = (
        backend.cache_dir
        / f"{backend._cache_key(requested_song.webpage_url)}.webm"
    )
    other = (
        backend.cache_dir / f"{backend._cache_key(other_song.webpage_url)}.webm"
    )
    requested.write_bytes(b"requested")
    other.write_bytes(b"other")

    backend.discard(requested_song)

    assert not requested.exists()
    assert other.exists()


@pytest.mark.asyncio
async def test_download_falls_back_from_web_embedded_to_android_vr(
    tmp_path: Path,
) -> None:
    backend = DownloadPlaybackBackend(10, cache_root=tmp_path)
    cache_key = "a" * 64

    async def download_once(
        webpage_url: str,
        output_template: Path,
        *,
        player_client: str,
    ) -> bytes:
        if player_client == "web_embedded":
            raise PlaybackPreparationError("client unavailable")
        Path(str(output_template).replace("%(ext)s", "webm")).write_bytes(
            b"media"
        )
        return b""

    backend._download_once = AsyncMock(side_effect=download_once)

    media_path = await backend._download(
        "https://example.invalid/watch",
        cache_key,
    )

    assert media_path.read_bytes() == b"media"
    assert backend._download_once.call_args_list == [
        call(
            "https://example.invalid/watch",
            backend.cache_dir / f"{cache_key}.%(ext)s",
            player_client="web_embedded",
        ),
        call(
            "https://example.invalid/watch",
            backend.cache_dir / f"{cache_key}.%(ext)s",
            player_client="android_vr",
        ),
    ]


def test_backend_factory_can_roll_back_to_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUSIC_PLAYBACK_BACKEND", "direct")

    backend = music_playback.create_playback_backend(1)

    assert isinstance(backend, DirectUrlPlaybackBackend)
