import pytest
import discord
from unittest.mock import MagicMock
from cogs.music.music_utils import Song, LoopMode, URL_REGEX

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
