import json
import sys
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.adapters.providers import YtDlpProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("playlist", [False, True], ids=["watch-url", "flat-playlist"])
async def test_lookup_preserves_track_metadata_without_network(rig, tmp_path, playlist):
    link = "https://www.youtube.com/watch?v=offline0001"
    item = {
        "id": "offline0001", "webpage_url": link, "title": '테스트 🎵 "A"\n다음 줄',
        "description": "x" * (1024 * 1024 + 1),
        "duration": 123, "uploader": "합성 가수", "thumbnail": "https://media.invalid/image.jpg",
        "url": "https://media.invalid/audio.m4a", "ext": "m4a",
        "extractor": "synthetic", "extractor_key": "Synthetic",
    }
    if playlist:
        flat = dict(item, _type="url", ie_key="Youtube", url=link)
        del flat["webpage_url"]
        info = {"_type": "playlist", "id": "test", "title": "test", "entries": [flat],
                "extractor": "synthetic", "extractor_key": "Synthetic"}
    else:
        info = item
    fixture = tmp_path / "synthetic.info.json"
    fixture.write_text(json.dumps(info), encoding="utf-8")

    # Exercise the release's CLI and the real stdout cap without an extractor request.
    offline_main = """import sys
def offline(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
        raise RuntimeError('network disabled in fixture')
sys.addaudithook(offline)
from yt_dlp import main
main()
"""
    pool = ProcessPool(rig[7])
    async def local_cli(arguments, **kwargs):
        assert arguments[:3] == (sys.executable, "-m", "yt_dlp")
        assert arguments[-2] == "--"
        return await pool.run((sys.executable, "-c", offline_main, *arguments[3:-2],
                               "--no-cache-dir", "--no-clean-info-json", "--load-info-json", str(fixture)),
                              **kwargs)

    try:
        fake = AsyncMock()
        fake.run.side_effect = local_cli
        tracks = await YtDlpProvider(fake).lookup("ytsearch3:test" if playlist else link, 10, limit=3)
        assert [track.legacy() for track in tracks] == [{
            "webpage_url": link, "title": item["title"], "duration": 123,
            "thumbnail": item["thumbnail"], "uploader": item["uploader"], "requester_id": 10,
        }]
    finally:
        await pool.close()
