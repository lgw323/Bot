"""Pause intent across real Cog/Actor voice events; all audio and IO are synthetic."""
import asyncio
from types import SimpleNamespace

import pytest

from discordbot.music.adapters.runtime import build_music_cog
from discordbot.music.ports.playback import Media

from .conftest import settle
from .test_actor import playing

pytestmark = pytest.mark.asyncio


def voice_events(actor):
    resource = SimpleNamespace(actors={100: actor},
        bot=SimpleNamespace(user=SimpleNamespace(id=88)), tts_enabled=True)
    cog = build_music_cog(resource)
    member = SimpleNamespace(id=88, guild=SimpleNamespace(id=100))
    connected = SimpleNamespace(channel=SimpleNamespace(id=123))
    disconnected = SimpleNamespace(channel=None)

    async def disconnect():
        await cog.on_voice_state_update(member, connected, disconnected)

    async def reconnect():
        await cog.on_voice_state_update(member, disconnected, connected)

    return disconnect, reconnect


@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize("phase", ["generating", "starting", "playing", "completed", "failed", "between-announcements"])
async def test_tts_disconnect_preserves_music_intent_and_rejects_old_callbacks(rig, paused, phase):
    make, clock, sleeper, audio, library, _, repository, _ = rig
    audible = False
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    callbacks = []

    async def blocked():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def speech(text):
        if phase == "generating" or (phase == "between-announcements" and text == "second"):
            await blocked()
        return Media("synthetic-tts", text)

    async def start(media, attempt, seek, volume, notify):
        nonlocal audible
        callbacks.append((attempt, notify))
        if phase == "starting" and media.key == "first":
            await blocked()
        audible = True

    async def silence():
        nonlocal audible
        audible = False

    async def resume():
        nonlocal audible
        audible = True

    library.speech.side_effect = speech
    audio.start.side_effect = start
    audio.stop.side_effect = audio.pause.side_effect = audio.disconnect.side_effect = silence
    audio.resume.side_effect = resume
    actor = make()
    disconnect, reconnect = voice_events(actor)
    try:
        original = await playing(actor)
        await actor.ask("loop")
        await actor.ask("autoplay", enabled=True)
        await actor.ask("volume", value=.35)
        clock.value += 17
        if paused:
            await actor.ask("pause", session_id=original.session_id)
        await actor.ask("tts", text="first")
        if phase in {"generating", "starting"}:
            await asyncio.wait_for(entered.wait(), 1)
        else:
            await settle(lambda: actor.projection().status == "tts")
            if phase == "between-announcements":
                await actor.ask("tts", text="second")
            if phase in {"completed", "failed", "between-announcements"}:
                await actor.ask("ended", attempt=actor.projection().attempt, failed=phase == "failed")
                if phase == "between-announcements":
                    await asyncio.wait_for(entered.wait(), 1)
                else:
                    await settle(lambda: actor.projection().status in {"playing", "paused"})
        before_disconnect = actor.projection()
        old_callbacks = list(callbacks)
        for _ in range(2):
            await disconnect()
            assert actor.projection().paused is paused
            assert not audible
        if phase in {"generating", "starting", "between-announcements"}:
            await asyncio.wait_for(cancelled.wait(), 1)
        release.set()
        for attempt, notify in old_callbacks:
            notify(attempt, False)
            notify(attempt, True)
        await actor.ask("inspect")
        clock.value += 2
        assert actor.projection().elapsed == 17
        await reconnect()
        await reconnect()
        # A cancelled disconnect timer must not expire the restored session.
        sleeper.wake(8)
        await settle(lambda: actor.projection().status in {"playing", "paused"})
        for attempt, notify in old_callbacks:
            notify(attempt, False)
            notify(attempt, True)
            assert not await actor.ask("ended", attempt=attempt, failed=False)
        result = await actor.ask("inspect")
        assert (result.status, result.paused, audible) == (
            "paused" if paused else "playing", paused, not paused)
        assert (result.session_id, result.current, result.queue, result.elapsed) == (
            original.session_id, original.current, original.queue, 17)
        assert (result.loop, result.autoplay, result.volume) == (
            before_disconnect.loop, True, .35)
        assert result.attempt not in {attempt for attempt, _ in old_callbacks}

        # The real reconnect Cog schedules another announcement after 1.5s.
        await settle(lambda: any(seconds == 1.5 for seconds, _ in sleeper.pending))
        sleeper.wake(1.5)
        await settle(lambda: actor.projection().status == "tts")
        announcement = actor.projection().attempt
        assert actor.projection().paused is paused and audible
        await actor.ask("ended", attempt=announcement, failed=False)
        await settle(lambda: actor.projection().status in {"playing", "paused"})
        assert (actor.projection().paused, audible) == (paused, not paused)
        clock.value += 3
        assert actor.projection().elapsed == (17 if paused else 20)
        if paused:
            await actor.ask("resume", session_id=original.session_id)
            assert audible and not actor.projection().paused
            clock.value += 3
            assert actor.projection().elapsed == 20
        assert {call.args[1] for call in repository.record_start.await_args_list} == {original.session_id}
    finally:
        release.set()
        await actor.close()
        assert not audible


@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize("phase", ["preparing", "starting"])
async def test_second_disconnect_during_music_recovery_retains_intent(rig, paused, phase):
    actor = rig[0]()
    original = await playing(actor)
    rig[1].value += 17
    if paused:
        await actor.ask("pause", session_id=original.session_id)
    await actor.ask("tts", text="synthetic")
    await settle(lambda: actor.projection().status == "tts")
    disconnect, reconnect = voice_events(actor)
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def barrier(*args):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return Media("synthetic", "recovered")

    if phase == "preparing":
        rig[4].acquire.side_effect = barrier
    else:
        rig[3].start.side_effect = barrier
    try:
        await disconnect()
        await reconnect()
        await asyncio.wait_for(entered.wait(), 1)
        assert actor.projection().status == phase
        await disconnect()
        await asyncio.wait_for(cancelled.wait(), 1)
        assert actor.projection().paused is paused
        release.set()
        await reconnect()
        await settle(lambda: actor.projection().status in {"playing", "paused"})
        result = actor.projection()
        assert (result.status, result.paused) == ("paused" if paused else "playing", paused)
        assert (result.session_id, result.current, result.queue, result.elapsed) == (
            original.session_id, original.current, original.queue, 17)
    finally:
        release.set()


@pytest.mark.parametrize("termination", ["skip", "leave", "expiry", "close"])
async def test_disconnected_tts_pause_intent_does_not_leak_after_session_termination(rig, termination):
    actor = rig[0]()
    original = await playing(actor)
    await actor.ask("pause", session_id=original.session_id)
    await actor.ask("tts", text="synthetic")
    await settle(lambda: actor.projection().status == "tts")
    await actor.ask("disconnected")
    assert actor.projection().paused
    if termination == "expiry":
        await settle(lambda: any(seconds == 8 for seconds, _ in rig[2].pending))
        rig[2].wake(8)
        await settle(lambda: actor.projection().current is None)
    elif termination == "close":
        await actor.close()
    else:
        await actor.ask(termination, session_id=original.session_id)
    assert not actor.projection().paused
    if termination == "skip":
        await actor.ask("connect", channel_id=123)
        await settle(lambda: actor.projection().status == "playing")
        assert actor.projection().current.item_id == "2"
        assert actor.projection().session_id != original.session_id
    else:
        assert actor.projection().current is None and not actor.projection().queue
