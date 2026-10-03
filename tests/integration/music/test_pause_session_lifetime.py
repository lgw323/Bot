"""Pause intent belongs to one logical session, including failed recovery attempts."""
from collections.abc import Callable

import pytest

from discordbot.music.domain.model import LoopMode
from discordbot.music.ports.playback import Media

from .conftest import settle, song
from .test_actor import playing
from .test_tts_reconnect import voice_events

pytestmark = pytest.mark.asyncio


class AudioEffects:
    def __init__(self) -> None:
        self.audible = False
        self.callbacks: list[tuple[str, Callable[[str, bool], None]]] = []
        self.failures = 0
        self.remaining_failures = 0

    async def start(self, media, attempt, seek, volume, notify) -> None:
        self.callbacks.append((attempt, notify))
        if media.key == "1" and self.remaining_failures:
            self.remaining_failures -= 1
            self.failures += 1
            raise RuntimeError("synthetic audio start failure")
        self.audible = True

    async def silence(self) -> None:
        self.audible = False

    async def resume(self) -> None:
        self.audible = True


async def wake_retry(actor, clock, sleeper, delay, seen, session, paused) -> None:
    await settle(lambda: actor.projection().status == "retry")
    state = actor.projection()
    assert (state.session_id, state.elapsed, state.paused) == (session, 17, paused)
    assert state.retry_at == clock.value + delay
    await settle(lambda: any(seconds == delay and event not in seen
                             for seconds, event in sleeper.pending))
    seen.update(event for _, event in sleeper.pending)
    clock.value += delay
    sleeper.wake(delay)


@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize("tts", [False, True], ids=["ordinary", "tts"])
@pytest.mark.parametrize("fault", ["acquire", "start"])
@pytest.mark.parametrize("destination", ["queued", "later", "same-session"])
async def test_recovery_pause_lifetime(rig, paused, tts, fault, destination):
    make, clock, sleeper, audio, library, _, repository, _ = rig
    effects = AudioEffects()
    audio.start.side_effect = effects.start
    audio.stop.side_effect = audio.pause.side_effect = audio.disconnect.side_effect = effects.silence
    audio.resume.side_effect = effects.resume
    actor = make()
    disconnect, reconnect = voice_events(actor)
    tracks = (song(),) if destination == "later" else (song(), song(2))
    original = await playing(actor, tracks)
    clock.value += 17
    if paused:
        await actor.ask("pause", session_id=original.session_id)
    if tts:
        await actor.ask("tts", text="synthetic announcement")
        await settle(lambda: actor.projection().status == "tts")
    await disconnect()
    assert actor.projection().paused is paused and not effects.audible
    failures = 2 if destination == "same-session" else 3

    async def acquire(track):
        nonlocal failures
        if track.item_id == "1" and failures:
            failures -= 1
            effects.failures += 1
            raise RuntimeError("synthetic acquisition failure")
        return Media("synthetic", track.item_id)

    if fault == "acquire":
        library.acquire.side_effect = acquire
    else:
        effects.remaining_failures = failures
    seen = {event for _, event in sleeper.pending}
    await reconnect()
    for count, delay in [(1, 3), (2, 8)]:
        await settle(lambda: effects.failures == count)
        await wake_retry(actor, clock, sleeper, delay, seen, original.session_id, paused)
        assert effects.failures == count
    if destination == "later":
        await settle(lambda: actor.projection().current is None)
        empty = actor.projection()
        assert (empty.session_id, empty.status, empty.elapsed, empty.paused) == (None, "idle", 0, False)
        assert not effects.audible and not empty.queue
        await actor.ask("enqueue", tracks=(song(2),))
    await settle(lambda: actor.projection().status in {"playing", "paused"})
    await settle(lambda: "start" not in actor._jobs)
    result = actor.projection()
    same = destination == "same-session"
    expected_paused = paused and same
    assert effects.failures == (2 if same else 3)
    assert (result.status, result.paused, effects.audible) == (
        "paused" if expected_paused else "playing", expected_paused, not expected_paused)
    assert (result.session_id == original.session_id) is same
    assert result.current.item_id == ("1" if same else "2")
    assert result.elapsed == (17 if same else 0)
    assert tuple(track.item_id for track in result.queue) == (("2",) if same else ())
    assert result.retry_at is None

    # Old music/TTS/failed-start callbacks cannot mutate the recovered or new session.
    for attempt, notify in effects.callbacks[:-1]:
        notify(attempt, False)
        notify(attempt, True)
        assert not await actor.ask("ended", attempt=attempt, failed=True)
        assert not await actor.ask("ended", attempt=attempt, failed=False)
    assert await actor.ask("inspect") == result
    assert [(call.args[1], call.args[2]) for call in repository.record_start.await_args_list] == [
        (original.session_id, original.current.url), (result.session_id, result.current.url)]

    # A later TTS completion must preserve this session's own intent, not the old one.
    await actor.ask("tts", text="successor announcement")
    await settle(lambda: actor.projection().status == "tts")
    assert actor.projection().paused is expected_paused and effects.audible
    await actor.ask("ended", attempt=actor.projection().attempt, failed=False)
    await settle(lambda: actor.projection().status in {"playing", "paused"})
    assert actor.projection().session_id == result.session_id
    assert (actor.projection().paused, effects.audible) == (expected_paused, not expected_paused)
    await actor.close()
    assert not effects.audible


@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize("mode", list(LoopMode))
async def test_completion_starts_new_session_with_fresh_pause_intent(rig, paused, mode):
    actor = rig[0]()
    original = await playing(actor)
    for _ in range(mode.value):
        await actor.ask("loop")
    if paused:
        await actor.ask("pause", session_id=original.session_id)
    await actor.ask("disconnected")
    await actor.ask("connect", channel_id=123)
    await settle(lambda: actor.projection().status in {"playing", "paused"})
    resumed = actor.projection()
    assert resumed.paused is paused and resumed.session_id == original.session_id
    if paused:
        await actor.ask("resume", session_id=original.session_id)
    await actor.ask("ended", attempt=resumed.attempt, failed=False)
    await settle(lambda: actor.projection().status == "playing")
    await settle(lambda: "start" not in actor._jobs)
    successor = actor.projection()
    assert successor.current.item_id == ("1" if mode == LoopMode.SONG else "2")
    assert successor.session_id != original.session_id
    assert not successor.paused and successor.elapsed == 0
    assert not await actor.ask("ended", attempt=resumed.attempt, failed=False)
    assert actor.projection() == successor
