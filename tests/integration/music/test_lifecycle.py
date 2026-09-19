import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from discordbot.music.adapters.audio import DiscordAudio
from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.adapters.runtime import MusicResource
from discordbot.music.ports.playback import Media
from discordbot.platform.executors import BoundedExecutor
from .conftest import settle, song

pytestmark = pytest.mark.asyncio


def fake_bot():
    async def history(**kwargs):
        for item in (): yield item
    message = SimpleNamespace(id=500, edit=AsyncMock())
    channel = SimpleNamespace(id=55, guild=SimpleNamespace(id=100, me=object()), history=history,
        send=AsyncMock(return_value=message), permissions_for=lambda _: SimpleNamespace(manage_messages=False))
    bot = SimpleNamespace(user=SimpleNamespace(id=88), get_channel=lambda _: channel, add_cog=AsyncMock(),
                          remove_cog=AsyncMock(), add_view=MagicMock())
    return bot, channel


async def test_cf16_ready_storm_dashboard_coalesce_and_cf20_shutdown(rig, tmp_path):
    bot, channel = fake_bot()
    executor = BoundedExecutor(workers=1, queue_capacity=8, name="music-runtime-test")
    repo = rig[6]
    repo.get_volume.return_value = .35
    repo.list_play_counts.return_value = ()
    runtime = MusicResource(bot, repo, rig[1], executor, cache_path=tmp_path/"cache", snapshot_path=tmp_path/"synthetic.json",
                            channels={100:55}, master=99, provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    try:
        await runtime.start()
        await runtime.start()
        await asyncio.gather(*(runtime.ready() for _ in range(10)))
        actor = await runtime.actor(100)
        assert len(runtime.actors) == 1 and actor.projection().volume == .35
        await actor.ask("enqueue", tracks=(song(), song(2)))
        await asyncio.wait_for(asyncio.shield(runtime._refresh_task), 2)
        assert channel.send.await_count == 1
        assert len(runtime.dashboard_views) == 1
        await runtime.stop()
        saved = json.loads((tmp_path/"synthetic.json").read_text())
        assert saved["100"]["current_song"]["title"] == "Track 1"
        assert not runtime.supervisor.snapshot().active and not runtime.processes.children
        bot.add_cog.assert_awaited_once()
    finally:
        await runtime.stop()
        await executor.close(grace_seconds=2)


async def test_partial_restore_source_retained_until_successful_actor_ack(rig, tmp_path):
    bot, _ = fake_bot()
    executor = BoundedExecutor(workers=1, queue_capacity=8, name="music-restore-test")
    path = tmp_path/"synthetic.json"
    path.write_text(json.dumps({"100": {"current_song": song().legacy(), "queue": [], "volume": .35},
                                "200": {"current_song": {"invalid": True}, "queue": []}}))
    repo = rig[6]
    repo.get_volume.return_value = None
    runtime = MusicResource(bot, repo, rig[1], executor, cache_path=tmp_path/"cache", snapshot_path=path,
                            channels={100:55,200:66}, master=99, provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    try:
        await runtime.start()
        assert runtime.failed_restore == {200}
        assert (await runtime.actor(100)).projection().volume == .35
        assert json.loads(path.read_text())["200"]["current_song"] == {"invalid": True}
    finally:
        await runtime.stop()
        await executor.close(grace_seconds=2)


async def test_dashboard_delete_recovery_failure_health_and_cleanup_timing(rig, tmp_path):
    bot, channel = fake_bot()
    channel.permissions_for = lambda _: SimpleNamespace(manage_messages=True)
    channel.purge = AsyncMock()
    executor = BoundedExecutor(workers=1, queue_capacity=8, name="dashboard-failure")
    rig[6].get_volume.return_value = None
    rig[6].list_play_counts.return_value = ()
    runtime = MusicResource(bot, rig[6], rig[1], executor, cache_path=tmp_path/"cache", snapshot_path=tmp_path/"synthetic.json",
                            channels={100:55}, master=99, provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    try:
        await runtime.start()
        actor = await runtime.actor(100)
        await runtime.dashboard(100, actor.projection())
        assert channel.purge.await_count == 1
        await runtime.dashboard(100, actor.projection())
        assert channel.purge.await_count == 1  # elapsed refresh is not channel cleanup
        class Missing(Exception): status=404
        runtime.messages[100].edit.side_effect = Missing()
        await runtime.dashboard(100, actor.projection())
        assert channel.send.await_count == 2
        runtime.messages[100].edit.side_effect = RuntimeError("synthetic delivery failure")
        runtime.changed(actor.projection())
        await asyncio.wait_for(asyncio.shield(runtime._refresh_task), 2)
        assert runtime.error == "dashboard_failed"
        bot.remove_cog.side_effect = RuntimeError("synthetic cog removal failure")
        await runtime.stop()
        assert not runtime.supervisor.snapshot().active
    finally:
        await runtime.stop()
        await executor.close(grace_seconds=2)


async def test_dashboard_refresh_retains_real_discord_component_dispatch(rig, tmp_path):
    """Use the SDK registry; AsyncMock.edit alone misses removal of new callbacks."""
    from discord.ui.view import ViewStore

    bot, channel = fake_bot()
    store = ViewStore(SimpleNamespace())
    bot.add_view = lambda view, *, message_id: store.add_view(view, message_id)
    message = channel.send.return_value

    async def edit(**kwargs):
        store.remove_message_tracking(message.id)
        store.add_view(kwargs['view'], message.id)
        return message

    async def send(**kwargs):
        store.add_view(kwargs['view'], message.id)
        return message

    message.edit.side_effect = edit
    channel.send.side_effect = send
    executor = BoundedExecutor(workers=1, queue_capacity=8, name='dashboard-dispatch')
    rig[6].get_volume.return_value = None
    rig[6].list_play_counts.return_value = ()
    runtime = MusicResource(bot, rig[6], rig[1], executor, cache_path=tmp_path/'cache',
        snapshot_path=tmp_path/'synthetic.json', channels={100:55}, master=99,
        provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    try:
        actor = await runtime.actor(100)
        for _ in range(3):
            await runtime.dashboard(100, actor.projection())
            current = runtime.dashboard_views[100]
            registered = store._views.get(message.id, {})
            for action in ('favorites', 'search', 'leave'):
                item = registered.get((2, 'music:'+action))
                assert item is not None, 'dashboard refresh removed the replacement callback'
                assert item.view is current and not item.disabled
            assert store._synced_message_views[message.id] is current
    finally:
        await runtime.stop()
        await executor.close(grace_seconds=2)


@pytest.mark.parametrize("mode", ["normal", "nonzero", "hung", "immediate_stop", "start_failure", "empty_audio"])
async def test_cf02_cf20_ffmpeg_adapter_local_child_ownership(rig, tmp_path, monkeypatch, mode):
    # Substitute only the executable, retaining the real async child/pipe/reap
    # path. No FFmpeg installation, network, Gateway, Voice or token is used.
    spawn = asyncio.create_subprocess_exec
    code = "import sys; sys.stdout.buffer.write(b'x'*7680); sys.stdout.flush()"
    if mode == "nonzero": code += "; import time; time.sleep(.1); raise SystemExit(3)"
    if mode in {"hung", "immediate_stop"}: code += "; import time; time.sleep(60)"
    if mode == "empty_audio": code = "raise SystemExit(0)"
    async def child(*args, **kwargs):
        if mode == "start_failure": raise FileNotFoundError("synthetic missing ffmpeg")
        return await spawn(sys.executable, "-c", code, **kwargs)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", child)
    pool = ProcessPool(rig[7], active=1, waiting=0, kill_seconds=.2)
    voice = MagicMock()
    voice.is_connected.return_value = True
    bot = SimpleNamespace()
    audio = DiscordAudio(bot, 100, pool)
    audio.voice = voice
    notify = MagicMock()
    executor = BoundedExecutor(workers=1, queue_capacity=1, name="pcm-test")
    try:
        if mode == "start_failure":
            with pytest.raises(FileNotFoundError): await audio.start(Media("synthetic", "k"), "attempt", 0, .5, notify)
        elif mode == "empty_audio":
            from discordbot.platform.errors import ExternalPermanentError
            with pytest.raises(ExternalPermanentError): await audio.start(Media("synthetic", "k"), "attempt", 0, .5, notify)
            voice.play.assert_not_called()
        else:
            await audio.start(Media("synthetic", "k"), "attempt", 0, .5, notify)
            if mode in {"normal", "nonzero"}:
                await asyncio.wait_for(asyncio.shield(audio._decoder), 3)
                source = voice.play.call_args.args[0]
                assert len(await executor.run(source.read)) == 3840
                assert len(await executor.run(source.read)) == 3840
                assert await executor.run(source.read) == b""
                voice.play.call_args.kwargs["after"](None)
                await asyncio.sleep(0)
                notify.assert_called_once_with("attempt", mode == "nonzero")
            await audio.stop()
        assert not pool.children and pool.admitted == 0
    finally:
        await audio.stop()
        await pool.close()
        await executor.close(grace_seconds=2)
