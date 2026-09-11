import asyncio
import json
import sys
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.cache import DiskCache
from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.adapters.providers import CachedMediaLibrary
from discordbot.music.adapters.snapshots import SnapshotStore
from discordbot.music.domain.model import Bounds, Track
from discordbot.platform.errors import AppError, CapacityError, ConflictError
from discordbot.platform.executors import BoundedExecutor
from .conftest import settle, song
from .test_actor import playing

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("operation", ["leave", "close", "skip"])
async def test_cf03_cf20_pending_retry_cannot_resurrect_after_cancellation(rig, operation):
    actor = rig[0]()
    first = await playing(actor)
    await actor.ask("ended", attempt=first.attempt, failed=True)
    await settle(lambda: bool(rig[2].pending))
    if operation == "close": await actor.close()
    else: await actor.ask(operation, session_id=first.session_id)
    rig[2].wake(3)
    await asyncio.sleep(0)
    assert actor.projection().current is None if operation != "skip" else actor.projection().current.item_id == "2"


async def test_cf02_duplicate_failure_and_full_public_mailbox_preserves_callback(rig):
    actor = rig[0](bounds=Bounds(mailbox=1))
    first = await playing(actor)
    pending = actor.post("inspect")
    actor._notify(first.attempt, True)
    actor._notify(first.attempt, True)
    await pending
    await settle(lambda: actor.projection().status == "retry")
    assert actor.projection().retry_at == 103


async def test_cf04_provider_ignoring_one_cancel_returns_stale_media_lease(rig):
    actor = rig[0]()
    entered, release = asyncio.Event(), asyncio.Event()
    result = rig[4].acquire.side_effect(song())
    async def delayed(track):
        if track.item_id != "1": return rig[4].speech.return_value
        entered.set()
        try: await release.wait()
        except asyncio.CancelledError: await release.wait()
        return result
    rig[4].acquire.side_effect = delayed
    await actor.ask("connect", channel_id=123)
    await actor.ask("enqueue", tracks=(song(), song(2)))
    await entered.wait()
    await actor.ask("skip", session_id=actor.projection().session_id)
    release.set()
    await settle(lambda: any(call.args[0] == result for call in rig[4].release.call_args_list))
    assert actor.projection().current.item_id == "2"


@pytest.mark.parametrize("failure", [TimeoutError, CapacityError, RuntimeError])
async def test_autoplay_failure_is_local_and_no_retry_storm(rig, failure):
    actor = rig[0]()
    first = await playing(actor, (song(),))
    rig[5].lookup.side_effect = failure("synthetic")
    await actor.ask("autoplay", enabled=True)
    await actor.ask("ended", attempt=first.attempt, failed=False)
    await settle(lambda: actor.projection().error == "music_autoplay_failed")
    assert actor.projection().current is None and not actor.projection().queue
    assert rig[5].lookup.await_count == 1


async def test_join_tts_disabled_delay_and_failure_preserve_playback(rig):
    actor = rig[0]()
    first = await playing(actor)
    assert not await actor.ask("tts", text="join", enabled=False)
    assert rig[4].speech.await_count == 0
    await actor.ask("bot_join", enabled=True)
    await settle(lambda: any(n == 1.5 for n, _ in rig[2].pending))
    rig[4].speech.side_effect = TimeoutError("synthetic")
    rig[2].wake(1.5)
    await settle(lambda: actor.projection().error == "music_tts_failed")
    assert actor.projection().session_id == first.session_id and actor.projection().status == "playing"


@pytest.mark.parametrize("value", [0, .35, .5, 1., 3.5])
async def test_legacy_volume_values_and_nullable_thumbnail_preserved(rig, value):
    actor = rig[0]()
    data = {"volume": value, "current_song": {**song().legacy(), "thumbnail": None}, "queue": []}
    await actor.ask("restore", identity="legacy", data=data)
    assert actor.projection().legacy()["volume"] == value
    assert actor.projection().legacy()["current_song"]["thumbnail"] is None


async def test_queue_only_restore_connect_starts_head(rig):
    actor = rig[0]()
    await actor.ask("restore", identity="queue-only", data={"queue": [song().legacy(), song(2).legacy()]})
    await actor.ask("connect", channel_id=123)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.title == "Track 1" and actor.projection().queue[0].title == "Track 2"


async def test_cache_retained_publish_cancel_transfers_lease_before_cleanup(rig, tmp_path, monkeypatch):
    import os
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="atomic-publish")
    cache = DiskCache(tmp_path/"cache", executor, rig[1], total_bytes=12, item_bytes=6, items=2)
    entered, release = threading.Event(), threading.Event()
    original = os.replace
    def replace_file(*args):
        entered.set()
        release.wait(2)
        return original(*args)
    async def produce(path, maximum): path.write_bytes(b"123456")
    try:
        await cache.start()
        monkeypatch.setattr(os, "replace", replace_file)
        task = asyncio.create_task(cache.acquire("same", produce))
        for _ in range(200):
            if entered.is_set(): break
            await asyncio.sleep(.001)
        assert entered.is_set()
        task.cancel()
        release.set()
        media = await task
        assert cache.bytes == 6 and Path(media.path).exists()
        await cache.release(media)
        await cache.release(media)
        assert not cache._leases
        await cache.close()
    finally:
        release.set()
        await executor.close(grace_seconds=2)


async def test_cf15_stream_writer_rejects_before_exceeding_disk_budget(rig, tmp_path):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="bounded-stream")
    pool = ProcessPool(rig[7], kill_seconds=.2)
    cache = DiskCache(tmp_path/"cache", executor, rig[1], total_bytes=12, item_bytes=6, items=2)
    library = CachedMediaLibrary(cache, pool)
    try:
        await cache.start()
        async def produce(path, maximum):
            await library._capture((sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*65536)"), path, maximum, 2, "acquire")
        with pytest.raises(CapacityError): await cache.acquire("oversize-stream", produce)
        assert not list(cache.directory.iterdir()) and not pool.children
        await cache.close()
    finally:
        await pool.close()
        await executor.close(grace_seconds=2)


async def test_direct_compatibility_expiry_and_stream_validation(rig):
    cache, pool = AsyncMock(), AsyncMock()
    cache.clock = rig[1]
    cache.acquire.side_effect = CapacityError("synthetic disk unavailable")
    library = CachedMediaLibrary(cache, pool, direct_until=rig[1].value+10)
    pool.run.return_value = b'{"url":"https://synthetic.googlevideo.com/audio?opaque=value"}'
    track = replace(song(), url="https://youtube.com/watch?v=synthetic")
    media = await library.acquire(track)
    assert media.key.startswith("direct:")
    rig[1].value += 11
    with pytest.raises(CapacityError): await library.acquire(track)
    assert pool.run.await_count == 1


async def test_snapshot_ack_rejects_changed_source(rig, tmp_path):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="snapshot-ack")
    store = SnapshotStore(tmp_path/"synthetic.json", executor)
    actor = rig[0]()
    try:
        await store.save(actor.projection())
        records, _ = await store.records()
        await actor.ask("enqueue", tracks=(song(),))
        await store.save(actor.projection())
        with pytest.raises(ConflictError): await store.acknowledge(records[0])
        assert json.loads(store.path.read_text())["100"]["current_song"]["title"] == "Track 1"
    finally: await executor.close(grace_seconds=2)
