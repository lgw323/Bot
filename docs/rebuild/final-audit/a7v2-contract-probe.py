"""Independent Phase 7 probes; temporary SQLite/files, fake transport and media only."""
import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from discordbot.music.adapters.runtime import MusicResource
from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.music.adapters.discord_ui import build_clear_confirmation
from discordbot.music.domain.pages import SongPages
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from tests.integration.music.conftest import rig, settle, song  # noqa: F401
from tests.integration.music.test_actor import playing
from tests.integration.music.test_discord import controller, interaction
from tests.integration.music.test_lifecycle import fake_bot


async def wait_for_io(predicate):
    """SQLite executor needs real scheduling time, unlike the all-fake rig."""
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.001)


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
async def test_resource_restart_retains_session_settings_and_sqlite_count(rig, tmp_path, paused):
    database = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
    await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
    await database.start()
    repository = SqliteMusicRepository(database)
    executor = BoundedExecutor(workers=1, queue_capacity=8, name="a7v2-restart")
    runtimes = []

    def resource():
        bot, _ = fake_bot()
        runtime = MusicResource(bot, repository, rig[1], executor,
            cache_path=tmp_path / "cache", snapshot_path=tmp_path / "snapshot.json",
            channels={100: 55, 200: 66}, master=99, provider=rig[5], library=rig[4],
            audio_factory=lambda _: AsyncMock())
        runtimes.append(runtime)
        return runtime

    try:
        first = resource()
        await first.start()
        actor = await first.actor(100)
        await actor.ask("connect", channel_id=123)
        await actor.ask("enqueue", tracks=(song(), song(2)))
        await wait_for_io(lambda: actor.projection().status == "playing")
        original = actor.projection()
        await wait_for_io(lambda: "start" not in actor._jobs)
        await actor.ask("loop")
        await actor.ask("loop")
        await actor.ask("autoplay", enabled=True)
        await actor.ask("volume", value=.35)
        rig[1].value += 17
        if paused:
            await actor.ask("pause", session_id=original.session_id)
        saved = actor.projection()
        await first.stop()
        assert not first.supervisor.snapshot().active

        second = resource()
        await second.start()
        restored = await second.actor(100)
        await wait_for_io(lambda: restored.projection().status in {"playing", "paused"})
        await wait_for_io(lambda: "start" not in restored._jobs)
        state = restored.projection()
        assert state.legacy() == saved.legacy()
        assert state.session_id == saved.session_id and state.paused is paused
        assert state.status == ("paused" if paused else "playing")
        counts = await repository.list_play_counts(100, DatabaseRequest.within(5))
        assert [(row.url, row.count) for row in counts] == [(song().url, 1)]
        assert not await repository.list_play_counts(200, DatabaseRequest.within(5))
        # A new song starts a new receipt; a restored same-session start did not.
        await restored.ask("skip", session_id=state.session_id)
        await wait_for_io(lambda: restored.projection().status == "playing")
        await wait_for_io(lambda: "start" not in restored._jobs)
        after = restored.projection()
        assert after.session_id != state.session_id and not after.paused
        assert after.current.url == song(2).url and after.elapsed == 0
        counts = await repository.list_play_counts(100, DatabaseRequest.within(5))
        assert {row.url: row.count for row in counts} == {song().url: 1, song(2).url: 1}
    finally:
        for runtime in reversed(runtimes):
            await runtime.stop()
            assert not runtime.supervisor.snapshot().active
            assert not runtime.processes.children and not runtime.ffmpeg.children
        await executor.close(grace_seconds=2)
        await database.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["confirm", "cancel", "stale", "expired"])
async def test_clear_confirmation_preserves_current_and_revision_boundary(rig, change):
    control, actor = controller(rig)
    state = await playing(actor, (song(), song(2), song(3)))
    pages = SongPages(100, 10, rig[1].value + 180, state.queue, state.revision)
    view = build_clear_confirmation(control, pages)
    try:
        if change == "stale":
            await actor.ask("enqueue", tracks=(song(4),))
        if change == "expired":
            rig[1].value += 30
        before = actor.projection()
        request = interaction()
        await view.children[1 if change == "cancel" else 0].callback(request)
        result = actor.projection()
        assert result.session_id == before.session_id and result.current == before.current
        if change == "confirm":
            assert not result.queue
            request.response.edit_message.assert_awaited_once()
        else:
            assert result.queue == before.queue
            if change != "cancel":
                request.response.send_message.assert_awaited_once()
                request.response.edit_message.assert_not_awaited()
    finally:
        view.stop()
        await control.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("roll,expected", [(0.29, "Guest"), (0.30, "Artist")])
async def test_autoplay_featured_probability_duration_and_identity_filters(rig, monkeypatch, roll, expected):
    import discordbot.music.application.actor as module
    monkeypatch.setattr(module.random, "random", lambda: roll)
    monkeypatch.setattr(module.random, "choice", lambda values: values[0])
    actor = rig[0]()
    first = await playing(actor, (song(title="Original feat. Guest"),))
    rig[5].lookup.return_value = (
        replace(song(2, "Boundary short"), duration=90),
        replace(song(3, "Boundary long"), duration=600),
        replace(song(4, "Different title"), url=first.current.url),
        song(5, "Original feat. Guest (Official)"),
        song(6, "Entirely new melody"),
    )
    await actor.ask("autoplay", enabled=True)
    await actor.ask("ended", attempt=first.attempt, failed=False)
    await settle(lambda: actor.projection().status == "playing")
    assert rig[5].lookup.call_args.args[0] == "ytsearch10:" + expected
    assert actor.projection().current.item_id == "6"
    assert actor.projection().session_id != first.session_id
    assert not actor.projection().paused and actor.projection().elapsed == 0
