"""Synthetic audio effects, frozen Views and delayed dashboard transport."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.discord_ui import MusicController, build_dashboard
from discordbot.music.adapters.runtime import MusicResource
from discordbot.platform.executors import BoundedExecutor
from .conftest import song
from .test_actor import playing
from .test_discord import interaction
from .test_lifecycle import fake_bot

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('captured_status', ['playing', 'paused'])
async def test_frozen_pause_callback_controls_current_audio_once_per_click(rig, captured_status):
    actor = rig[0]()
    state = await playing(actor)
    audible = [True]
    rig[3].pause.side_effect = lambda: audible.__setitem__(0, False)
    rig[3].resume.side_effect = lambda: audible.__setitem__(0, True)
    control = MusicController(AsyncMock(return_value=actor), rig[6], rig[1], {100:55}, 99)
    # The callback remains installed during an edit/rate-limit wait. Its captured
    # projection can precede the currently playing state, or the previous click.
    frozen = build_dashboard(control, replace(state, status=captured_status))
    button = next(b for b in frozen.children if b.custom_id == 'music:pause')
    try:
        for expected_audio, expected_state, icon in [(False, 'paused', '▶️'), (True, 'playing', '⏸️')]:
            await button.callback(interaction())
            assert audible[0] is expected_audio, 'one click must affect actual audio, even with a stale View'
            assert actor.projection().status == expected_state
            projected = build_dashboard(control, actor.projection())
            try:
                assert str(next(b for b in projected.children if b.custom_id == 'music:pause').emoji) == icon
            finally:
                projected.stop()
        assert rig[3].pause.await_count == rig[3].resume.await_count == 1
    finally:
        frozen.stop()
        await control.stop()


async def test_pause_projection_waits_for_audio_effect_and_stale_session_cannot_toggle(rig):
    actor = rig[0]()
    state = await playing(actor)
    entered, release = asyncio.Event(), asyncio.Event()
    async def pause():
        entered.set()
        await release.wait()
    rig[3].pause.side_effect = pause
    control = MusicController(AsyncMock(return_value=actor), rig[6], rig[1], {100:55}, 99)
    task = asyncio.create_task(control.action(interaction(), 'pause', state))
    try:
        await entered.wait()
        assert actor.projection().status == 'playing'
        release.set()
        await task
        assert actor.projection().status == 'paused'
        await actor.ask('skip', session_id=state.session_id)
        rig[3].pause.reset_mock()
        rig[3].resume.reset_mock()
        await control.action(interaction(), 'pause', state)
        assert rig[3].pause.await_count == rig[3].resume.await_count == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await control.stop()


async def test_late_dashboard_edit_cannot_replace_newer_playback_controls(rig, tmp_path):
    bot, channel = fake_bot()
    first_entered, release = asyncio.Event(), asyncio.Event()
    published = []
    async def edit(**kwargs):
        view = kwargs['view']
        icon = str(next(b for b in view.children if b.custom_id == 'music:pause').emoji)
        if icon == '⏸️':
            first_entered.set()
            await release.wait()
        published.append(icon)
    message = SimpleNamespace(id=500, edit=AsyncMock(side_effect=edit))
    rig[6].list_play_counts.return_value = ()
    executor = BoundedExecutor(workers=1, queue_capacity=8, name='pause-dashboard')
    runtime = MusicResource(bot, rig[6], rig[1], executor, cache_path=tmp_path/'cache',
        snapshot_path=tmp_path/'synthetic.json', channels={100:55}, master=99,
        provider=rig[5], library=rig[4], audio_factory=lambda _:rig[3])
    runtime.messages[100] = message
    state = replace(rig[0]().projection(), current=song(), session_id='synthetic', status='playing', revision=1)
    older = asyncio.create_task(runtime.dashboard(100, state))
    newer = None
    try:
        await first_entered.wait()
        newer = asyncio.create_task(runtime.dashboard(100, replace(state, status='paused', revision=2)))
        for _ in range(20): await asyncio.sleep(0)
        release.set()
        await asyncio.gather(older, newer)
        assert published[-1] == '▶️', 'late old HTTP edit must not overwrite paused controls'
        await runtime.dashboard(100, state)
        assert published[-1] == '▶️', 'already superseded projection must not be republished'
    finally:
        release.set()
        await asyncio.gather(*[t for t in (older,newer) if t], return_exceptions=True)
        await runtime.stop()
        await executor.close(grace_seconds=2)
