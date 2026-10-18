"""Announcements retain the audio slot while Music requests finish concurrently."""
import asyncio

import pytest

from discordbot.music.ports.playback import Media

from .conftest import settle, song

pytestmark = pytest.mark.asyncio


async def test_lookup_completion_waits_for_idle_announcement_to_end(rig):
    make, _, sleeper, audio, library, provider, repository, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def lookup(*args, **kwargs):
        entered.set()
        await release.wait()
        return (song(),)

    provider.lookup.side_effect = lookup
    actor = make()
    await actor.ask('connect', channel_id=123)
    request = await actor.ask('lookup', request_id='synthetic', query='synthetic', requester_id=10)
    await entered.wait()
    await actor.ask('bot_join', enabled=True)
    await settle(lambda: any(seconds == 1.5 for seconds, _ in sleeper.pending))
    sleeper.wake(1.5)
    await settle(lambda: actor.projection().status == 'tts')
    announcement = actor.projection().attempt
    release.set()
    await request
    await actor.ask('inspect')

    assert actor.projection().status == 'tts', 'Lookup must not replace the active announcement'
    assert actor.projection().attempt == announcement
    assert audio.start.await_count == 1
    assert library.acquire.await_count == 0
    assert repository.record_start.await_count == 0

    await actor.ask('ended', attempt=announcement, failed=False)
    await settle(lambda: actor.projection().status == 'playing')
    assert actor.projection().current.item_id == '1'
    assert audio.start.await_count == 2
    assert repository.record_start.await_count == 1
    assert library.release.await_args_list[0].args[0].key == 'tts'


async def test_idle_announcements_drain_and_return_to_idle(rig):
    actor = rig[0]()
    await actor.ask('connect', channel_id=123)
    await actor.ask('tts', text='첫 번째 안내')
    await settle(lambda: actor.projection().status == 'tts')
    first = actor.projection().attempt
    await actor.ask('tts', text='두 번째 안내')
    await actor.ask('ended', attempt=first, failed=False)
    await settle(lambda: rig[4].speech.await_count == 2 and actor.projection().status == 'tts')
    assert actor.projection().attempt != first
    await actor.ask('ended', attempt=actor.projection().attempt, failed=False)
    assert actor.projection().status == 'idle'
    assert actor.projection().attempt is None
    assert rig[6].record_start.await_count == 0


@pytest.mark.parametrize('phase', ['generating', 'starting', 'playing'])
async def test_enqueue_and_repeated_connect_preserve_announcement_in_each_phase(rig, phase):
    make, _, _, audio, library, _, repository, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def speech(text):
        if phase == 'generating':
            entered.set()
            await release.wait()
        return Media('synthetic-tts', 'tts')

    async def start(media, *args):
        if phase == 'starting' and media.key == 'tts':
            entered.set()
            await release.wait()

    library.speech.side_effect = speech
    audio.start.side_effect = start
    actor = make()
    await actor.ask('connect', channel_id=123)
    await actor.ask('tts', text='안내')
    if phase == 'playing':
        await settle(lambda: actor.projection().status == 'tts')
    else:
        await entered.wait()
    await actor.ask('enqueue', tracks=(song(), song(2)))
    await actor.ask('connect', channel_id=123)
    assert library.acquire.await_count == 0
    release.set()
    await settle(lambda: actor.projection().status == 'tts')
    assert audio.start.await_count == 1
    assert repository.record_start.await_count == 0
    await actor.ask('ended', attempt=actor.projection().attempt, failed=False)
    await settle(lambda: actor.projection().status == 'playing')
    assert actor.projection().current.item_id == '1'
    assert [item.item_id for item in actor.projection().queue] == ['2']
    assert audio.start.await_count == 2


async def test_idle_announcement_generation_failure_unblocks_queued_music(rig):
    make, _, _, _, library, _, repository, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def speech(text):
        entered.set()
        await release.wait()
        raise TimeoutError('synthetic generation failure')

    library.speech.side_effect = speech
    actor = make()
    await actor.ask('connect', channel_id=123)
    await actor.ask('tts', text='안내')
    await entered.wait()
    await actor.ask('enqueue', tracks=(song(),))
    assert library.acquire.await_count == 0
    release.set()
    await settle(lambda: actor.projection().status == 'playing')
    assert actor.projection().error == 'music_tts_failed'
    assert repository.record_start.await_count == 1


async def test_queued_announcements_finish_before_pending_music(rig):
    actor = rig[0]()
    await actor.ask('connect', channel_id=123)
    await actor.ask('tts', text='첫 번째 안내')
    await settle(lambda: actor.projection().status == 'tts')
    first = actor.projection().attempt
    await actor.ask('enqueue', tracks=(song(),))
    await actor.ask('tts', text='두 번째 안내')
    await actor.ask('ended', attempt=first, failed=False)
    await settle(lambda: rig[4].speech.await_count == 2 and actor.projection().status == 'tts')
    assert rig[4].acquire.await_count == 0
    await actor.ask('ended', attempt=actor.projection().attempt, failed=False)
    await settle(lambda: actor.projection().status == 'playing')
    assert rig[3].start.await_count == 3
    assert rig[4].release.await_count == 2
    assert rig[6].record_start.await_count == 1


async def test_consecutive_announcements_preserve_paused_music_intent(rig):
    actor = rig[0]()
    await actor.ask('connect', channel_id=123)
    await actor.ask('enqueue', tracks=(song(),))
    await settle(lambda: actor.projection().status == 'playing')
    original = actor.projection()
    rig[1].value += 17
    await actor.ask('pause', session_id=original.session_id)
    await actor.ask('tts', text='첫 번째 안내')
    await settle(lambda: actor.projection().status == 'tts')
    first = actor.projection().attempt
    await actor.ask('tts', text='두 번째 안내')
    await actor.ask('ended', attempt=first, failed=False)
    await settle(lambda: rig[4].speech.await_count == 2 and actor.projection().status == 'tts')
    await actor.ask('ended', attempt=actor.projection().attempt, failed=False)
    await settle(lambda: actor.projection().status in {'playing', 'paused'})
    assert actor.projection().status == 'paused'
    assert actor.projection().session_id == original.session_id
    assert actor.projection().elapsed == 17
