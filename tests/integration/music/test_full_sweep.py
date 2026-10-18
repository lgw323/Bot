"""Validation-only failures stop automatic work, not independent explicit requests."""
import asyncio

import pytest

from discordbot.platform.errors import DataIntegrityError, ExternalPermanentError, ShutdownError
from .conftest import settle, song
from .test_actor import playing

pytestmark=pytest.mark.asyncio


@pytest.mark.parametrize('stage',['lookup','prepare','start','tts','callback'])
async def test_soft_failure_allows_next_independent_path_without_automatic_retry(rig,stage):
    make,_,sleep,audio,library,provider,_,_=rig
    actor=make(fail_fast=True,full_sweep=True)
    error=ExternalPermanentError('synthetic')
    if stage=='prepare': library.acquire.side_effect=error
    if stage=='start': audio.start.side_effect=error
    if stage=='lookup': provider.lookup.side_effect=error
    await actor.ask('connect',channel_id=123)
    if stage=='lookup':
        future=await actor.ask('lookup',query='synthetic-url',requester_id=1,request_id='first')
        with pytest.raises(ShutdownError): await future
    elif stage in {'tts','callback'}:
        first=await playing(actor)
        if stage=='callback': await actor.ask('ended',attempt=first.attempt,failed=True)
        else:
            library.speech.side_effect=error
            await actor.ask('tts',text='synthetic')
    else: await actor.ask('enqueue',tracks=(song(),song(2)))
    await settle(lambda: actor.projection().status=='failed' and actor.projection().attempt is None)
    assert not actor.smoke_failed and not sleep.pending
    counts=(provider.lookup.await_count,library.acquire.await_count,library.speech.await_count)
    for _ in range(30): await asyncio.sleep(0)
    assert counts==(provider.lookup.await_count,library.acquire.await_count,library.speech.await_count)
    # Search is independent of the failed acquisition. No retry of the original input.
    provider.lookup.side_effect=None
    future=await actor.ask('lookup',query='different-search',requester_id=1,request_id='second',enqueue=False)
    assert await future==(song(),)
    assert not actor.smoke_failed
    # Ordinary stop/disconnect clears that failed playback before a fresh path.
    await actor.ask('leave')
    library.acquire.side_effect=lambda track: rig[4].speech.return_value
    library.speech.side_effect=None
    audio.start.side_effect=None
    await actor.ask('connect',channel_id=123)
    await actor.ask('tts',text='independent announcement')
    await settle(lambda: actor.projection().status=='tts')


@pytest.mark.parametrize('path',['lookup','prepare','record_start'])
async def test_integrity_still_latches_admission_in_full_sweep(rig,path):
    actor=rig[0](fail_fast=True,full_sweep=True)
    class CorruptData(DataIntegrityError): pass
    if path=='lookup': rig[5].lookup.side_effect=CorruptData('synthetic')
    elif path=='prepare': rig[4].acquire.side_effect=CorruptData('synthetic')
    else: rig[6].record_start.side_effect=CorruptData('synthetic')
    await actor.ask('connect',channel_id=123)
    if path=='lookup':
        future=await actor.ask('lookup',query='synthetic',requester_id=1,request_id='first')
        with pytest.raises(ShutdownError): await future
    else: await actor.ask('enqueue',tracks=(song(),))
    await settle(lambda: actor.smoke_failed)
    with pytest.raises(ShutdownError): await actor.ask('lookup',query='other',requester_id=1,request_id='second')


async def test_standalone_tts_after_music_failure_does_not_retry_failed_media(rig):
    actor=rig[0](full_sweep=True)
    rig[4].acquire.side_effect=ExternalPermanentError('synthetic')
    await actor.ask('connect',channel_id=123)
    await actor.ask('enqueue',tracks=(song(),))
    await settle(lambda: actor.projection().status=='failed')
    await actor.ask('tts',text='independent')
    await settle(lambda: actor.projection().status=='tts')
    await actor.ask('ended',attempt=actor.projection().attempt,failed=False)
    for _ in range(30): await asyncio.sleep(0)
    assert rig[4].acquire.await_count==1 and not rig[2].pending


async def test_full_sweep_expiry_returns_to_fail_stop_not_normal_retry(rig):
    active=True
    actor=rig[0](fail_fast=True,full_sweep=lambda: active)
    first=await playing(actor)
    active=False
    await actor.ask('ended',attempt=first.attempt,failed=True)
    assert actor.smoke_failed and not rig[2].pending
