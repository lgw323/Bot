"""Independent synthetic contract probe: pause ownership ends with its session."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.runtime import build_music_cog
from discordbot.music.application.actor import MusicActor
from discordbot.music.ports.playback import Media
from discordbot.platform.tasks import TaskSupervisor
from tests.integration.music.conftest import FakeClock, Sleep, settle, song


class SyntheticAudio:
    def __init__(self):
        self.audible = False

    async def connect(self, channel_id):
        pass

    async def start(self, media, attempt, seek, volume, notify):
        self.audible = True

    async def stop(self):
        self.audible = False

    pause = stop
    disconnect = stop

    async def resume(self):
        self.audible = True


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [False, True], ids=["playing-control", "paused-session"])
async def test_exhausted_reconnect_does_not_pause_successor(paused):
    clock, sleeper = FakeClock(), Sleep()
    supervisor = TaskSupervisor(capacity=128, history_capacity=512, clock=clock)
    audio, other_audio = SyntheticAudio(), SyntheticAudio()
    repository, provider, library = AsyncMock(), AsyncMock(), AsyncMock()
    library.acquire.side_effect = lambda track: Media("synthetic", track.item_id)
    library.speech.return_value = Media("synthetic-tts", "tts")
    actors = {
        guild: MusicActor(guild, supervisor=supervisor, clock=clock, sleeper=sleeper,
            provider=provider, library=library, audio=output, repository=repository)
        for guild, output in [(100, audio), (200, other_audio)]
    }
    actor, control = actors[100], actors[200]
    resource = SimpleNamespace(actors=actors,
        bot=SimpleNamespace(user=SimpleNamespace(id=88)), tts_enabled=True)
    cog = build_music_cog(resource)
    member = SimpleNamespace(id=88, guild=SimpleNamespace(id=100))
    connected = SimpleNamespace(channel=SimpleNamespace(id=123))
    disconnected = SimpleNamespace(channel=None)
    failures = []
    try:
        for item in actors.values():
            await item.ask("connect", channel_id=123)
            await item.ask("enqueue", tracks=(song(), song(2)))
            await settle(lambda: item.projection().status == "playing")
        first, other = actor.projection(), control.projection()
        clock.value += 17
        if paused:
            await actor.ask("pause", session_id=first.session_id)
        await actor.ask("tts", text="synthetic announcement")
        await settle(lambda: actor.projection().status == "tts")
        await cog.on_voice_state_update(member, connected, disconnected)

        async def acquire(track):
            if track.item_id == first.current.item_id:
                failures.append(track.item_id)
                raise RuntimeError("synthetic unavailable original track")
            return Media("synthetic", track.item_id)

        library.acquire.side_effect = acquire
        old_timer_events = {event for _, event in sleeper.pending}
        await cog.on_voice_state_update(member, disconnected, connected)
        for attempt, delay in [(1, 3), (2, 8)]:
            await settle(lambda: len(failures) == attempt and actor.projection().status == "retry")
            assert actor.projection().session_id == first.session_id
            assert actor.projection().retry_at == clock.value + delay
            # Sleep retains cancelled timer records. Wait for the new retry,
            # not the already cancelled eight-second disconnect timer.
            await settle(lambda: any(seconds == delay and event not in old_timer_events
                for seconds, event in sleeper.pending))
            clock.value += delay
            sleeper.wake(delay)
        await settle(lambda: actor.projection().current.item_id == "2"
            and actor.projection().status in {"playing", "paused"})
        result = actor.projection()
        assert len(failures) == 3
        assert result.session_id != first.session_id
        assert result.elapsed == 0 and not result.queue
        assert control.projection().session_id == other.session_id
        assert control.projection().status == "playing" and other_audio.audible
        observed = (result.current.item_id, result.status, result.paused, audio.audible)
        assert observed == ("2", "playing", False, True), observed
    finally:
        for item in actors.values():
            await item.close()
        await supervisor.shutdown(grace_seconds=0)
        assert not supervisor.snapshot().active
        assert not audio.audible and not other_audio.audible
