"""A7 contract probe: synthetic voice events, no network, DB or media files."""
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
        self.pauses = 0

    async def connect(self, channel_id):
        pass

    async def start(self, media, attempt, seek, volume, notify):
        self.audible = True

    async def stop(self):
        self.audible = False

    async def pause(self):
        self.audible = False
        self.pauses += 1

    async def resume(self):
        self.audible = True

    async def disconnect(self):
        self.audible = False


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt_tts", [False, True], ids=["ordinary-reconnect-control", "disconnect-during-tts"])
async def test_paused_intent_survives_voice_reconnect(interrupt_tts):
    clock, sleeper = FakeClock(), Sleep()
    supervisor = TaskSupervisor(capacity=128, history_capacity=512, clock=clock)
    actors, audio = {}, {}
    repository, provider, library = AsyncMock(), AsyncMock(), AsyncMock()
    library.acquire.side_effect = lambda track: Media("synthetic", track.item_id)
    library.speech.return_value = Media("synthetic-tts", "tts")
    for guild in (100, 200):
        audio[guild] = SyntheticAudio()
        actors[guild] = MusicActor(guild, supervisor=supervisor, clock=clock,
            sleeper=sleeper, provider=provider, library=library,
            audio=audio[guild], repository=repository)
    actor, control = actors[100], actors[200]
    resource = SimpleNamespace(actors=actors, bot=SimpleNamespace(user=SimpleNamespace(id=88)), tts_enabled=True)
    cog = build_music_cog(resource)
    member = SimpleNamespace(id=88, guild=SimpleNamespace(id=100))
    connected = SimpleNamespace(channel=SimpleNamespace(id=123))
    disconnected = SimpleNamespace(channel=None)
    try:
        for item in actors.values():
            await item.ask("connect", channel_id=123)
            await item.ask("enqueue", tracks=(song(), song(2)))
            await settle(lambda: item.projection().status == "playing")
        original, other = actor.projection(), control.projection()
        clock.value += 17
        await actor.ask("pause", session_id=original.session_id)
        assert not audio[100].audible and actor.projection().paused
        if interrupt_tts:
            await actor.ask("tts", text="synthetic announcement")
            await settle(lambda: actor.projection().status == "tts")
            assert actor.projection().paused and audio[100].audible
        # The actual Discord Cog forwards the two synthetic voice-state events.
        await cog.on_voice_state_update(member, connected, disconnected)
        after_disconnect = actor.projection().paused
        await cog.on_voice_state_update(member, disconnected, connected)
        await settle(lambda: actor.projection().status in {"playing", "paused"})
        result = actor.projection()
        assert result.session_id == original.session_id
        assert result.current == original.current and result.queue == original.queue
        assert result.elapsed == 17
        assert control.projection().session_id == other.session_id
        assert control.projection().status == "playing" and audio[200].audible
        observed = (after_disconnect, result.status, result.paused, audio[100].audible)
        assert observed == (True, "paused", True, False), observed
    finally:
        for item in actors.values():
            await item.close()
        await supervisor.shutdown(grace_seconds=0)
        assert not supervisor.snapshot().active
        assert all(not item.audible for item in audio.values())
