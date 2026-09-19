import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.cache import DiskCache
from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.adapters.providers import YtDlpProvider
from discordbot.music.adapters.snapshots import SnapshotStore
from discordbot.platform.errors import AppError, CapacityError, ConflictError, DataIntegrityError
from discordbot.platform.executors import BoundedExecutor
from .conftest import settle, song

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("mode", ["success", "nonzero", "hang", "oversize", "startup", "cancel"])
async def test_cf15_cf20_local_process_reap(rig, mode):
    pool = ProcessPool(rig[7], output_bytes=128, kill_seconds=.2)
    codes = {"success": "print('ok')", "nonzero": "raise SystemExit(3)", "hang": "import time; time.sleep(60)",
             "oversize": "print('x'*1024)", "cancel": "import time; time.sleep(60)"}
    args = [sys.executable, "-c", codes.get(mode, "")] if mode != "startup" else ["no-such-music-executable-ffmpeg"]
    if mode == "cancel":
        task = asyncio.create_task(pool.run(args, seconds=10))
        await settle(lambda: bool(pool.children), turns=2000)
        children = tuple(pool.children)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert all(child.returncode is not None for child in children)
    elif mode == "success":
        assert (await pool.run(args, seconds=2)).strip() == b"ok"
    else:
        with pytest.raises(AppError): await pool.run(args, seconds=.2 if mode == "hang" else 2)
    assert pool.admitted == 0 and not pool.children
    await pool.close()


async def test_kill_escalation_after_terminate_timeout(rig):
    pool = ProcessPool(rig[7], kill_seconds=.01)
    class Child:
        returncode = None
        terminated = killed = False
        def terminate(self): self.terminated = True
        def kill(self): self.killed = True; self.returncode = -9
        async def wait(self):
            if self.returncode is None: await asyncio.Event().wait()
            return self.returncode
    child = Child()
    pool.children.add(child)
    await pool.reap(child)
    assert child.terminated and child.killed and not pool.children


async def test_cf15_cache_same_key_pins_eviction_corruption_and_ttl(rig, tmp_path):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="music-test")
    cache = DiskCache(tmp_path / "cache", executor, rig[1], total_bytes=12, item_bytes=6, items=2, ttl=10)
    count = 0
    async def produce(path, maximum):
        nonlocal count
        count += 1
        path.write_bytes(b"abcdef")
    try:
        await cache.start()
        one, same = await asyncio.gather(cache.acquire("same", produce), cache.acquire("same", produce))
        assert one.path == same.path and one.lease_id != same.lease_id and count == 1
        two = await cache.acquire("two", produce)
        with pytest.raises(CapacityError): await cache.acquire("three", produce)
        await cache.release(one)
        await cache.release(same)
        three = await cache.acquire("three", produce)
        assert not Path(one.path).exists() and cache.bytes == 12
        await cache.release(two)
        await cache.release(three)
        Path(three.path).write_bytes(b"broken")
        recovered = await cache.acquire("three", produce)
        assert Path(recovered.path).read_bytes() == b"abcdef"
        await cache.release(recovered)
        rig[1].value += 11
        await cache.cleanup()
        assert cache.bytes == 0
        await cache.close()
    finally: await executor.close(grace_seconds=2)


@pytest.mark.parametrize("mode", ["disk_full", "permission", "oversize", "zero", "cancel"])
async def test_cache_partial_never_published(rig, tmp_path, mode):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="music-test")
    cache = DiskCache(tmp_path / "cache", executor, rig[1], total_bytes=12, item_bytes=6, items=2)
    async def produce(path, maximum):
        path.write_bytes(b"1234567" if mode == "oversize" else b"")
        if mode == "disk_full": raise OSError(28, "synthetic disk full")
        if mode == "permission": raise PermissionError("synthetic permission")
        if mode == "cancel": raise asyncio.CancelledError
    try:
        await cache.start()
        with pytest.raises((AppError, asyncio.CancelledError)): await cache.acquire("partial", produce)
        assert not list(cache.directory.iterdir()) and cache.admitted == 0
        await cache.close()
    finally: await executor.close(grace_seconds=2)


async def test_cf06_snapshot_atomic_revision_checksum_ack_partial_guild(rig, tmp_path, monkeypatch):
    executor = BoundedExecutor(workers=1, queue_capacity=4, name="snapshot-test")
    store = SnapshotStore(tmp_path / "synthetic-state.json", executor)
    actor = rig[0]()
    await actor.ask("enqueue", tracks=(song(), song(2)))
    try:
        await store.save(actor.projection())
        saved = store.path.read_bytes()
        original = os.replace
        monkeypatch.setattr(os, "replace", lambda *args: (_ for _ in ()).throw(OSError("synthetic crash")))
        with pytest.raises(AppError): await store.save(replace(actor.projection(), revision=9))
        assert store.path.read_bytes() == saved and not list(tmp_path.glob("*.tmp"))
        monkeypatch.setattr(os, "replace", original)
        records, failed = await store.records()
        assert len(records) == 1 and not failed and store.path.exists()
        restored = rig[0](200)
        assert await restored.ask("restore", identity=records[0].identity, data=records[0].data, session_id=records[0].session_id)
        await store.acknowledge(records[0])
        assert json.loads(store.path.read_text()) == {}
        await store.save(replace(actor.projection(), revision=20))
        with pytest.raises(ConflictError): await store.save(actor.projection())
        data = json.loads(store.path.read_text())
        data["200"] = {"_v2": {"version": 99}}
        store.path.write_text(json.dumps(data))
        records, failed = await store.records()
        assert len(records) == 1 and failed == (200,)
        data["100"]["volume"] = .9
        store.path.write_text(json.dumps(data))
        assert (await store.records())[1] == (100, 200)
        store.path.write_text("{broken")
        with pytest.raises(DataIntegrityError): await store.records()
    finally: await executor.close(grace_seconds=2)


@pytest.mark.parametrize("count", [0, 1, 10, 50, 70])
async def test_provider_playlist_bounds_malformed_order(rig, count):
    pool = AsyncMock()
    entries = [{"webpage_url": f"https://youtube.com/watch?v={i}", "title": str(i), "duration": 200} for i in range(count)]
    pool.run.return_value = json.dumps({"entries": entries + [None, {"title": "bad"}]}).encode()
    provider = YtDlpProvider(pool)
    result = await provider.lookup("https://youtube.com/playlist?list=synthetic", 10, limit=50)
    assert [track.title for track in result] == [str(i) for i in range(min(count, 50))]
    assert "--playlist-end" in pool.run.call_args.args[0]


async def test_provider_incompatible_result_boundary(rig):
    pool = AsyncMock()
    pool.run.return_value = b'{"entries": "not an array"}'
    with pytest.raises(DataIntegrityError): await YtDlpProvider(pool).lookup("ytsearch3:test", 10, limit=3)


async def test_tts_child_entrypoint_from_release_working_directory(rig, tmp_path):
    """The immutable app is on the parent's sys.path, not installed in the venv."""
    import os
    import subprocess
    from discordbot.music.adapters.providers import CachedMediaLibrary

    executor = BoundedExecutor(workers=1, queue_capacity=4, name='tts-entrypoint')
    cache = DiskCache(tmp_path/'cache', executor, rig[1])
    pool = AsyncMock()
    library = CachedMediaLibrary(cache, pool)

    async def capture(arguments, path, maximum, seconds, name):
        environment = dict(os.environ, PYTHON_DOTENV_DISABLED='1')
        environment.pop('PYTHONPATH', None)
        # Omit the text: entrypoint must reach argument validation without gTTS I/O.
        result = subprocess.run(arguments[:-1], cwd=tmp_path, env=environment,
            capture_output=True, timeout=10)
        assert result.returncode == 2, 'TTS child cannot import its entrypoint outside the source checkout'
        path.write_bytes(b'synthetic-audio')

    library._capture = capture
    try:
        await cache.start()
        media = await library.speech('synthetic')
        await library.release(media)
    finally:
        await cache.close()
        await executor.close(grace_seconds=2)


async def test_v2_snapshot_is_consumable_by_legacy_reader(rig, tmp_path):
    from collections import deque
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from cogs.music.music_session_restorer import MusicSessionRestorer
    from cogs.music.music_utils import LoopMode

    executor = BoundedExecutor(workers=1, queue_capacity=4, name="legacy-snapshot-test")
    store = SnapshotStore(tmp_path / "synthetic-rollback.json", executor)
    actor = rig[0]()
    data = {"text_channel_id": None, "voice_channel_id": None, "volume": .35, "loop_mode": "QUEUE",
            "auto_play_enabled": True, "current_song": song().legacy(), "elapsed_seconds": 47, "queue": [song(2).legacy()]}
    await actor.ask("restore", identity="synthetic", data=data)
    try:
        assert actor.projection().legacy() == data
        await store.save(actor.projection())
        raw = json.loads(store.path.read_text())["100"]
        assert list(raw) == list(data) + ["_v2"]
        bot, guild = MagicMock(), MagicMock()
        bot.get_channel.return_value = None
        state = SimpleNamespace(volume=.5, loop_mode=LoopMode.NONE, queue=deque(), voice_client=None,
                                play_next_song=asyncio.Event())
        await MusicSessionRestorer(bot).restore(guild, state, raw)
        assert [track.title for track in state.queue] == ["Track 1", "Track 2"]
        assert state.seek_time == 47 and state.volume == .35 and state.loop_mode == LoopMode.QUEUE
        assert state.auto_play_enabled is True
    finally:
        await executor.close(grace_seconds=2)
