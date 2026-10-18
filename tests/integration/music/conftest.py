import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest_asyncio

from discordbot.music.application.actor import MusicActor
from discordbot.music.domain.model import Track
from discordbot.music.ports.playback import Media
from discordbot.platform.tasks import TaskSupervisor


class FakeClock:
    value = 100.
    def monotonic(self): return self.value
    def now(self): return datetime.fromtimestamp(self.value, timezone.utc)


class Sleep:
    def __init__(self): self.pending = []
    async def sleep(self, seconds):
        event = asyncio.Event()
        self.pending.append((seconds, event))
        await event.wait()
    def wake(self, seconds):
        for duration, event in self.pending:
            if duration == seconds: event.set()


def song(index=1, title=None):
    return Track(str(index), f"https://example.invalid/{index}", title or f"Track {index}", 200, 10, "Artist")


async def settle(predicate, turns=300):
    for _ in range(turns):
        if predicate(): return
        await asyncio.sleep(0)
    raise AssertionError("deterministic work did not settle")


@pytest_asyncio.fixture
async def rig():
    clock, sleep = FakeClock(), Sleep()
    supervisor = TaskSupervisor(capacity=128, history_capacity=512, clock=clock)
    audio, library, provider, repository = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    library.acquire.side_effect = lambda track: Media("synthetic", track.item_id)
    library.speech.return_value = Media("synthetic-tts", "tts")
    provider.lookup.return_value = (song(),)
    actors = []
    def make(guild=100, **kwargs):
        actor = MusicActor(guild, supervisor=supervisor, clock=clock, sleeper=sleep, provider=provider,
                           library=library, audio=audio, repository=repository, **kwargs)
        actors.append(actor)
        return actor
    yield make, clock, sleep, audio, library, provider, repository, supervisor
    for actor in actors: await actor.close()
    await supervisor.shutdown(grace_seconds=0)
    assert not supervisor.snapshot().active
