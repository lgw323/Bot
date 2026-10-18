"""The opt-in live smoke latch must close admission before any normal retry."""
import asyncio

import pytest

from discordbot.platform.errors import ExternalPermanentError, ShutdownError
from .conftest import settle, song
from .test_actor import playing

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('stage', ['prepare', 'start', 'tts', 'lookup', 'callback'])
async def test_smoke_first_failure_preserves_current_and_prevents_retry(rig, stage):
    make, _, sleeper, audio, library, provider, _, _ = rig
    actor = make(fail_fast=True)
    error = ExternalPermanentError('synthetic')
    if stage == 'prepare': library.acquire.side_effect = error
    if stage == 'start': audio.start.side_effect = error
    if stage == 'lookup': provider.lookup.side_effect = error
    await actor.ask('connect', channel_id=123)
    if stage == 'lookup':
        future = await actor.ask('lookup', query='synthetic', requester_id=1, request_id='synthetic', enqueue=True)
        with pytest.raises(ShutdownError): await future
    elif stage in {'tts', 'callback'}:
        first = await playing(actor)
        if stage == 'callback': await actor.ask('ended', attempt=first.attempt, failed=True)
        else:
            library.speech.side_effect = error
            await actor.ask('tts', text='synthetic')
    else: await actor.ask('enqueue', tracks=(song(), song(2)))
    await settle(lambda: actor.smoke_failed and actor.projection().attempt is None)
    state = actor.projection()
    assert state.status == 'failed' and state.retry_at is None
    assert not sleeper.pending
    if stage != 'lookup':
        assert state.current.item_id == '1'
        assert [track.item_id for track in state.queue] == ['2']
    with pytest.raises(ShutdownError): await actor.ask('connect', channel_id=123)
    with pytest.raises(ShutdownError): await actor.ask('enqueue', tracks=(song(3),))
    attempts = library.acquire.await_count
    for _ in range(30): await asyncio.sleep(0)
    assert library.acquire.await_count == attempts
    await actor.close()
    audio.disconnect.assert_awaited_once()


async def test_successful_smoke_disarm_restores_normal_retry_without_restart(rig):
    armed = True
    actor = rig[0](fail_fast=lambda: armed)
    first = await playing(actor)
    armed = False
    await actor.ask('ended', attempt=first.attempt, failed=True)
    await settle(lambda: bool(rig[2].pending))
    assert actor.projection().retry_at == rig[1].value+3
    assert not actor.smoke_failed
