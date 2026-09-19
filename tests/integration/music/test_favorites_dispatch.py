"""Favorites smoke contracts through SDK wire projection and actual dispatch.

Only synthetic SQLite databases and fake Discord transport are used.
"""
import asyncio
from dataclasses import replace
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ui.view import ViewStore

from cogs.music.music_ui import MusicPlayerView
from cogs.music.music_utils import LoopMode as LegacyLoopMode
from discordbot.music.adapters.discord_ui import MusicController, build_dashboard
from discordbot.music.adapters.runtime import MusicResource
from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.music.ports.repository import Favorite
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.telemetry import JsonEventFormatter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from .conftest import song
from .test_discord import interaction
from .test_lifecycle import fake_bot

pytestmark = pytest.mark.asyncio


def wire(view):
    return [item for row in view.to_components() for item in row['components']]


async def dispatch(store, request, custom_id, message_id=500):
    request.message = SimpleNamespace(id=message_id)
    request.data = {'custom_id': custom_id, 'component_type': 2}
    store.dispatch_view(2, custom_id, request)
    tasks = tuple(store._ViewStore__tasks)
    assert tasks, 'SDK could not dispatch the registered component'
    await asyncio.wait_for(asyncio.gather(*tasks), 2)


@pytest.mark.parametrize('playing', [False, True])
async def test_v1_v2_favorite_meaning_matches_serialized_components(rig, playing):
    actor = rig[0]()
    control = SimpleNamespace(action=AsyncMock())
    state = replace(actor.projection(), current=song() if playing else None)
    legacy = MusicPlayerView(MagicMock(), SimpleNamespace(
        current_song=SimpleNamespace(title='Synthetic', webpage_url='synthetic') if playing else None,
        voice_client=None, loop_mode=LegacyLoopMode.NONE, auto_play_enabled=False))
    view = build_dashboard(control, state)
    store = ViewStore(SimpleNamespace())
    try:
        for emoji, identity in (('⭐', 'music:favorite'), ('💾', 'music:favorites')):
            old = next(item for item in wire(legacy) if item.get('emoji', {}).get('name') == emoji)
            new = next(item for item in wire(view) if item['custom_id'] == identity)
            for key in ('type', 'style', 'label', 'emoji', 'disabled'):
                assert new.get(key) == old.get(key)
            assert new['disabled'] is (not playing if emoji == '⭐' else False)
        store.add_view(view, 500)
        await dispatch(store, interaction(), 'music:favorites')
        assert control.action.await_args.args[1:] == ('favorites', state)
        if playing:
            await dispatch(store, interaction(), 'music:favorite')
            assert control.action.await_args.args[1:] == ('favorite', state)
    finally:
        view.stop()
        legacy.stop()


@pytest.mark.parametrize('count', [26, 101])
async def test_sdk_favorites_to_sqlite_global_scope_paging_owner_and_expiry(rig, tmp_path, count):
    database = SqliteDatabase(DatabaseConfig(tmp_path / 'synthetic-favorites.db'))
    await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    await database.start()
    repository = SqliteMusicRepository(database)
    actors = {guild: rig[0](guild) for guild in (100, 200)}
    control = MusicController(AsyncMock(side_effect=lambda guild: actors[guild]), repository, rig[1], {100:55, 200:66}, 99)
    store = ViewStore(SimpleNamespace())
    dashboards = []
    opened = []
    try:
        for index in range(count):
            await repository.put_favorite(10, Favorite(f'https://example.invalid/{index:03}', 'Duplicate'), DatabaseRequest.within(5))
        await repository.put_favorite(20, Favorite('https://example.invalid/other', 'Other owner'), DatabaseRequest.within(5))
        for guild in (100, 200):
            view = build_dashboard(control, actors[guild].projection())
            dashboards.append(view)
            store.add_view(view, guild)
            request = interaction(guild=guild, channel=55 if guild == 100 else 66, voice=None)
            await dispatch(store, request, 'music:favorites', guild)
            request.response.send_message.assert_awaited_once()
            assert request.response.send_message.call_args.kwargs['ephemeral'] is True
            request.followup.send.assert_not_awaited()
            favorites = request.response.send_message.call_args.kwargs['view']
            opened.append(favorites)
            assert len(favorites.songs) == count
            assert favorites.pages.user_id == 10 and favorites.pages.guild_id == guild
            assert len(wire(favorites)[0]['options']) == 25
            assert favorites.timeout == 180 and view.timeout is None
        assert opened[0].songs == opened[1].songs  # same Discord user, different guild
        favorites = opened[0]
        store.add_view(favorites, 700)
        first_ids = {option['value'] for option in wire(favorites)[0]['options']}
        request = interaction()
        await dispatch(store, request, 'music:next', 700)
        request.response.edit_message.assert_awaited_once_with(view=favorites)
        second_ids = {option['value'] for option in wire(favorites)[0]['options']}
        assert not first_ids & second_ids
        assert len(second_ids) == min(25, count-25)
        store.add_view(favorites, 700)  # SDK edit registers the freshly rendered items
        other = interaction(user=20)
        await dispatch(store, other, 'music:previous', 700)
        other.response.send_message.assert_awaited_once()
        other.response.edit_message.assert_not_awaited()
        assert favorites.page_index == 1
        rig[1].value = favorites.pages.expires
        expired = interaction()
        await dispatch(store, expired, 'music:previous', 700)
        expired.response.send_message.assert_awaited_once()
        expired.response.edit_message.assert_not_awaited()
        assert favorites.page_index == 1
        assert len(await repository.list_favorites(20, DatabaseRequest.within(5))) == 1
    finally:
        for view in dashboards:
            view.stop()
        control.close()
        await database.stop()


async def test_ready_storm_replacement_keeps_only_latest_dispatch(rig, tmp_path):
    bot, channel = fake_bot()
    store = ViewStore(SimpleNamespace())
    message = channel.send.return_value
    versions = []

    async def transmit(**kwargs):
        view = kwargs['view']
        assert next(item for item in wire(view) if item['custom_id']=='music:favorites')['disabled'] is False
        store.remove_message_tracking(message.id)
        store.add_view(view, message.id)
        versions.append(view)
        await asyncio.sleep(0)  # ready events can overlap transport delivery
        return message

    message.edit.side_effect = channel.send.side_effect = transmit
    rig[6].get_volume.return_value = None
    rig[6].list_play_counts.return_value = ()
    rig[6].list_favorites.return_value = (Favorite('https://example.invalid/1', 'Synthetic'),)
    executor = BoundedExecutor(workers=1, queue_capacity=8, name='favorites-dispatch')
    runtime = MusicResource(bot, rig[6], rig[1], executor, cache_path=tmp_path/'cache',
        snapshot_path=tmp_path/'synthetic.json', channels={100:55}, master=99,
        provider=rig[5], library=rig[4], audio_factory=lambda _: rig[3])
    try:
        await runtime.start()
        for _ in range(3):
            await asyncio.gather(*(runtime.ready() for _ in range(15)))
            while runtime._refresh_task is not None:
                await asyncio.wait_for(asyncio.shield(runtime._refresh_task), 2)
            current = runtime.dashboard_views[100]
            for old in versions[:-1]:
                assert old.is_finished()
                old.stop()  # delayed stale cleanup cannot remove the new handler
            assert store._synced_message_views == {message.id: current}
            assert {item.view for item in store._views[message.id].values()} == {current}
            request = interaction()
            await dispatch(store, request, 'music:favorites', message.id)
            request.response.send_message.assert_awaited_once()
            assert request.response.send_message.call_args.kwargs['content'] == '💾 보관함'
        assert len(versions) == 3 and channel.send.await_count == 1
    finally:
        await runtime.stop()
        await executor.close(grace_seconds=2)


async def test_sdk_favorites_failure_has_private_ack_and_safe_typed_event(rig, caplog):
    caplog.set_level(logging.WARNING, logger='discordbot.music')
    actor = rig[0]()
    control = MusicController(AsyncMock(return_value=actor), rig[6], rig[1], {100:55}, 99)
    rig[6].list_favorites.side_effect = DatabaseUnavailableError('private synthetic payload', context={'user_id':987654321})
    view = build_dashboard(control, actor.projection())
    store = ViewStore(SimpleNamespace())
    try:
        store.add_view(view, 500)
        request = interaction()
        await dispatch(store, request, 'music:favorites')
        request.response.send_message.assert_awaited_once()
        assert request.response.send_message.call_args.kwargs['ephemeral'] is True
        record = next(record for record in caplog.records if record.msg == 'music.ui_failed')
        assert record.fields == {'stage':'action', 'error_code':'database_unavailable'}
        encoded = JsonEventFormatter().format(record)
        assert 'private synthetic' not in encoded and '987654321' not in encoded
    finally:
        view.stop()
        control.close()
