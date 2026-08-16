import pytest
import discord
from unittest.mock import MagicMock, call, patch

import cogs.music.music_utils as music_utils

from cogs.music.music_utils import (
    Song,
    LoopMode,
    URL_REGEX,
    extract_info,
    log_ytdlp_runtime_status,
)

def test_url_regex() -> None:
    assert URL_REGEX.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert URL_REGEX.match("https://youtu.be/dQw4w9WgXcQ")
    assert URL_REGEX.match("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not URL_REGEX.match("https://www.google.com")

def test_song_initialization() -> None:
    mock_member = MagicMock(spec=discord.Member)
    mock_member.display_name = "TestUser"
    mock_member.display_avatar.url = "http://test.url/avatar.png"
    
    data = {
        'webpage_url': 'http://youtube.com/test',
        'url': 'http://stream.url',
        'title': 'Test Song',
        'duration': 130, # 2분 10초
        'thumbnail': 'http://thumb.url',
        'uploader': 'Test Artist'
    }
    
    song = Song(data=data, requester=mock_member)
    assert song.title == "Test Song"
    assert song.duration == 130
    assert song.uploader == "Test Artist"
    assert song.webpage_url == "http://youtube.com/test"
    assert song.requester == mock_member

def test_song_to_embed() -> None:
    mock_member = MagicMock(spec=discord.Member)
    mock_member.display_name = "TestUser"
    mock_member.display_avatar.url = "http://test.url/avatar.png"
    
    data = {
        'webpage_url': 'http://youtube.com/test',
        'url': 'http://stream.url',
        'title': 'Test Song',
        'duration': 130,
        'thumbnail': 'http://thumb.url',
        'uploader': 'Test Artist'
    }
    
    song = Song(data=data, requester=mock_member)
    embed = song.to_embed(title_prefix="[Playing] ")
    
    assert embed.title == "[Playing] Test Song"
    assert embed.url == "http://youtube.com/test"
    assert embed.color.value == 0x2ECC71 # BOT_EMBED_COLOR
    assert embed.thumbnail.url == "http://thumb.url"
    assert len(embed.fields) == 2
    assert embed.fields[0].name == "채널"
    assert embed.fields[0].value == "Test Artist"
    assert embed.fields[1].name == "길이"
    assert embed.fields[1].value == "2:10"
    assert "TestUser" in embed.footer.text

def test_loop_mode() -> None:
    assert LoopMode.NONE.value == 0
    assert LoopMode.SONG.value == 1
    assert LoopMode.QUEUE.value == 2


@patch("cogs.music.music_utils.yt_dlp.YoutubeDL")
def test_extract_info_uses_fresh_ytdlp_session(mock_youtube_dl) -> None:
    first_downloader = MagicMock()
    second_downloader = MagicMock()
    first_downloader.__enter__.return_value = first_downloader
    second_downloader.__enter__.return_value = second_downloader
    first_downloader.extract_info.return_value = {"title": "first"}
    second_downloader.extract_info.return_value = {"title": "second"}
    mock_youtube_dl.side_effect = [first_downloader, second_downloader]

    assert extract_info("first-query") == {"title": "first"}
    assert extract_info("second-query") == {"title": "second"}

    assert mock_youtube_dl.call_count == 2
    first_downloader.extract_info.assert_called_once_with(
        "first-query",
        download=False,
        process=True,
    )
    second_downloader.extract_info.assert_called_once_with(
        "second-query",
        download=False,
        process=True,
    )


def _create_pot_provider_tree(tmp_path):
    server_home = tmp_path / "bgutil-ytdlp-pot-provider" / "server"
    (server_home / "src").mkdir(parents=True)
    (server_home / "src" / "generate_once.ts").write_text(
        "// test provider",
        encoding="utf-8",
    )
    (server_home / "node_modules").mkdir()
    return server_home


def _runtime_version(package_name: str) -> str:
    versions = {
        "yt-dlp-ejs": "0.8.0",
        "bgutil-ytdlp-pot-provider": "1.3.1",
    }
    return versions[package_name]


def test_ytdlp_options_use_mweb_po_token_provider_when_available(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_home = _create_pot_provider_tree(tmp_path)
    monkeypatch.setenv("YTDLP_POT_PROVIDER_DIR", str(server_home))
    monkeypatch.setattr(
        music_utils,
        "_find_deno_path",
        lambda: "/home/os/.local/bin/deno",
    )
    monkeypatch.setattr(music_utils, "version", _runtime_version)

    options = music_utils.build_ytdl_options()

    assert "http_headers" not in options
    assert options["extractor_args"]["youtube"]["player_client"] == ["mweb"]
    assert options["extractor_args"]["youtubepot-bgutilscript"][
        "server_home"
    ] == [str(server_home)]


def test_ytdlp_options_fall_back_when_po_provider_files_are_missing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YTDLP_POT_PROVIDER_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(
        music_utils,
        "_find_deno_path",
        lambda: "/home/os/.local/bin/deno",
    )
    monkeypatch.setattr(music_utils, "version", _runtime_version)

    options = music_utils.build_ytdl_options()

    assert "extractor_args" not in options
    assert "http_headers" not in options


@patch("cogs.music.music_utils.yt_dlp.YoutubeDL")
def test_extract_info_falls_back_after_po_token_generation_failure(
    mock_youtube_dl,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_home = _create_pot_provider_tree(tmp_path)
    monkeypatch.setenv("YTDLP_POT_PROVIDER_DIR", str(server_home))
    monkeypatch.setattr(
        music_utils,
        "_find_deno_path",
        lambda: "/home/os/.local/bin/deno",
    )
    monkeypatch.setattr(music_utils, "version", _runtime_version)

    options_seen = []

    def make_downloader(options):
        options_seen.append(options)
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        if len(options_seen) == 1:
            options["logger"].warning(
                '[youtube] [pot] Error fetching PO Token from '
                '"bgutil:script-deno" provider',
            )
            downloader.extract_info.return_value = {"title": "unsigned"}
        else:
            downloader.extract_info.return_value = {"title": "fallback"}
        return downloader

    mock_youtube_dl.side_effect = make_downloader

    assert extract_info("test-query") == {"title": "fallback"}
    assert "extractor_args" in options_seen[0]
    assert "extractor_args" not in options_seen[1]


@patch("cogs.music.music_utils.version", side_effect=_runtime_version)
@patch("cogs.music.music_utils._find_deno_path", return_value="/home/os/.local/bin/deno")
def test_ytdlp_runtime_status_accepts_deno_and_ejs(
    mock_find_deno,
    mock_version,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_home = _create_pot_provider_tree(tmp_path)
    monkeypatch.setenv("YTDLP_POT_PROVIDER_DIR", str(server_home))

    assert log_ytdlp_runtime_status() is True
    mock_find_deno.assert_called_once_with()
    assert mock_version.call_args_list == [
        call("yt-dlp-ejs"),
        call("bgutil-ytdlp-pot-provider"),
    ]

@pytest.mark.asyncio
async def test_music_states_io(tmp_path) -> None:
    from cogs.music.music_utils import save_music_states, load_music_states
    import cogs.music.music_utils as mu
    import os
    
    # 1. 파일 경로를 임시 경로로 패치
    original_file = mu.MUSIC_STATE_FILE
    temp_file = str(tmp_path / "test_music_state.json")
    mu.MUSIC_STATE_FILE = temp_file
    
    try:
        # 빈 상태 데이터 생성 (Mocking MusicState)
        mock_state = MagicMock()
        mock_state.current_song = None
        mock_state.queue = []
        
        # 아무것도 없을 때 파일이 생성되지 않아야 함
        await save_music_states({12345: mock_state})
        assert not os.path.exists(temp_file)
        
        # 2. 재생 중인 곡이 있는 형태 구성
        mock_song = MagicMock()
        mock_song.webpage_url = "http://test.url"
        mock_song.title = "Test Song"
        mock_song.duration = 100
        mock_song.thumbnail = "thumb"
        mock_song.uploader = "Artist"
        mock_song.requester.id = 999
        
        mock_state.current_song = mock_song
        mock_state.get_current_playback_time.return_value = 50
        mock_state.volume = 0.5
        mock_state.loop_mode.name = "QUEUE"
        mock_state.auto_play_enabled = True
        mock_state.text_channel.id = 111
        mock_state.voice_client.channel.id = 222

        mock_queued_song = MagicMock()
        mock_queued_song.webpage_url = "http://test.url/next"
        mock_queued_song.title = "Next Song"
        mock_queued_song.duration = 200
        mock_queued_song.thumbnail = "next-thumb"
        mock_queued_song.uploader = "Next Artist"
        mock_queued_song.requester.id = 1000
        mock_state.queue = [mock_queued_song]
        
        # 임시 파일 통째로 저장
        await save_music_states({12345: mock_state})
        
        # 저장 확인
        assert os.path.exists(temp_file)
        
        # 3. 로드 및 파일 삭제 처리 확인
        loaded_data = await load_music_states()
        
        # 데이터가 정상 로드되었는지 체크
        assert "12345" in loaded_data
        state_data = loaded_data["12345"]
        
        assert state_data["volume"] == 0.5
        assert state_data["loop_mode"] == "QUEUE"
        assert state_data["auto_play_enabled"] is True
        assert state_data["elapsed_seconds"] == 50
        assert state_data["current_song"]["title"] == "Test Song"
        assert state_data["text_channel_id"] == 111
        assert state_data["voice_channel_id"] == 222
        assert state_data["queue"] == [
            {
                "webpage_url": "http://test.url/next",
                "title": "Next Song",
                "duration": 200,
                "thumbnail": "next-thumb",
                "uploader": "Next Artist",
                "requester_id": 1000,
            }
        ]
        
        # 로드 후 원본 파일이 정상 삭제(`os.remove`)되었는지 검증
        assert not os.path.exists(temp_file)
        
    finally:
        # Restore original
        mu.MUSIC_STATE_FILE = original_file
