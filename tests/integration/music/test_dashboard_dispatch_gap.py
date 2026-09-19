"""Actual SDK dispatch stays available while dashboard HTTP edits are pending."""
import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.music.adapters.discord_ui import build_dashboard
from discordbot.music.adapters.runtime import MusicResource
from discordbot.platform.executors import BoundedExecutor
from .conftest import song
from .test_discord import interaction
from .test_favorites_dispatch import dispatch
from .test_lifecycle import fake_bot


@pytest.mark.asyncio
@pytest.mark.parametrize('transport_failure', [False, True])
async def test_dashboard_dispatch_survives_pending_and_failed_sdk_edit(rig, tmp_path, transport_failure):
    bot, channel = fake_bot()
    client = discord.Client(intents=discord.Intents.none())
    store = client._connection._view_store
    bot.add_view = client.add_view
    payload = {'id': '500', 'type': 0, 'content': '', 'attachments': [], 'embeds': [],
               'edited_timestamp': None, 'pinned': False, 'mention_everyone': False, 'tts': False}
    message = discord.Message(state=client._connection, channel=channel, data=payload)
    entered, release = asyncio.Event(), asyncio.Event()

    async def edit(*args, **kwargs):
        entered.set()
        await release.wait()
        if transport_failure:
            raise RuntimeError('synthetic transport failure')
        return payload

    client.http.edit_message = AsyncMock(side_effect=edit)
    rig[6].list_play_counts.return_value = ()
    executor = BoundedExecutor(workers=1, queue_capacity=8, name='dashboard-dispatch')
    runtime = MusicResource(bot, rig[6], rig[1], executor, cache_path=tmp_path/'cache',
        snapshot_path=tmp_path/'synthetic.json', channels={100:55}, master=99,
        provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    runtime.controller.action = AsyncMock()
    old_state = rig[0]().projection()
    new_state = replace(old_state, current=song(), session_id='synthetic-session', status='playing')
    old = build_dashboard(runtime.controller, old_state)
    client.add_view(old, message_id=message.id)
    runtime.messages[100] = message
    runtime.dashboard_views[100] = old
    refresh = asyncio.create_task(runtime.dashboard(100, new_state))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        request = interaction()
        await dispatch(store, request, 'music:favorites', message.id)
        assert runtime.controller.action.await_args.args[1:] == ('favorites', old_state)
        assert not old.is_finished()
        release.set()
        if transport_failure:
            with pytest.raises(RuntimeError, match='synthetic transport failure'):
                await refresh
        else:
            await refresh
        current = runtime.dashboard_views[100]
        assert store._synced_message_views == {message.id: current}
        if transport_failure:
            assert current is old and not old.is_finished()
        else:
            assert current is not old and old.is_finished()
            old.stop()  # repeated stale cleanup cannot remove replacement handlers
        await dispatch(store, interaction(), 'music:favorites', message.id)
        expected = old_state if transport_failure else new_state
        assert runtime.controller.action.await_args.args[1:] == ('favorites', expected)
        assert {item.view for item in store._views[message.id].values()} == {current}
    finally:
        release.set()
        await asyncio.gather(refresh, return_exceptions=True)
        await runtime.stop()
        await executor.close(grace_seconds=2)
        await client.close()
