"""Exercise the real reply-deletion owner through Music and its parent lifecycle."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.composition.config import Environment, PlatformConfig, RuntimePolicy, ServiceKind
from discordbot.composition.runtime import ProcessRuntime, RuntimeState, require_clean_shutdown
from discordbot.music.adapters.runtime import MusicResource
from discordbot.platform.errors import ShutdownError


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['clean', 'cancelled', 'eventual', 'incomplete', 'failure'])
async def test_real_music_deletion_cleanup_after_optional_degradation(tmp_path, monkeypatch, outcome):
    events = []
    class Resource:
        def __init__(self, name, required=True):
            self.name, self.required = name, required
        async def start(self):
            events.append('start:' + self.name)
            if not self.required:
                raise RuntimeError('synthetic optional failure')
        async def stop(self):
            events.append('stop:' + self.name)

    config = PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, 'synthetic',
                            runtime=RuntimePolicy(1, .2))
    app = ProcessRuntime(config=config)
    bot = SimpleNamespace(add_cog=AsyncMock(), remove_cog=AsyncMock())
    music = MusicResource(bot, SimpleNamespace(), app.clock, app.executor,
                          cache_path=tmp_path / 'cache', snapshot_path=tmp_path / 'state',
                          channels={}, master=1)
    monkeypatch.setattr(music.cache, 'start', AsyncMock())
    monkeypatch.setattr(music.cache, 'close', AsyncMock())
    monkeypatch.setattr(music.snapshots, 'records', AsyncMock(return_value=((), ())))
    mandatory, optional = Resource('mandatory'), Resource('optional', False)
    parent = ProcessRuntime(config=config, resources=(mandatory, music, optional))
    entered, release = asyncio.Event(), asyncio.Event()
    task = None

    async def delete():
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                if outcome == 'cancelled':
                    raise
                if outcome == 'eventual':
                    return

    try:
        await parent.start()
        assert parent.health.snapshot().ready
        assert events == ['start:mandatory', 'start:optional', 'stop:optional']
        music.controller._delete_later(SimpleNamespace(delete=delete), 0)
        task = next(iter(music.controller._delete_tasks))
        await asyncio.wait_for(entered.wait(), .5)
        if outcome == 'clean':
            release.set()
            await asyncio.wait_for(task, .5)
        if outcome == 'failure':
            async def failed_shutdown(**kwargs):
                raise ShutdownError('synthetic supervisor cleanup failure')
            monkeypatch.setattr(music.controller._deletions, 'shutdown', failed_shutdown)
        report = await asyncio.wait_for(parent.shutdown(), .7)
        if outcome in ('clean', 'cancelled', 'eventual'):
            require_clean_shutdown(report)
            assert music.closed and music.startup_cleanup_complete
            assert not music.controller._deletions.snapshot().active
            assert not music.controller._delete_tasks
            assert parent._started_resources == []
            assert events[-1] == 'stop:mandatory'
            music.cache.close.assert_awaited_once()
            bot.remove_cog.assert_awaited_once()
        else:
            with pytest.raises(ShutdownError):
                require_clean_shutdown(report)
            assert parent.state is RuntimeState.FAILED
            assert report.resource_errors
            assert parent._started_resources == [mandatory, music]
            assert not music.closed and not music.startup_cleanup_complete
            assert task in music.controller._delete_tasks and not task.done()
            assert len(music.controller._deletions.snapshot().active) == 1
            assert 'stop:mandatory' not in events
            music.cache.close.assert_not_awaited()
            bot.remove_cog.assert_not_awaited()
        assert await parent.shutdown() == report
        assert events.count('stop:optional') == 1
    finally:
        release.set()
        if task is not None:
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
        if music._tick_task is not None:
            music._stopping = True
            music._tick_task.cancel()
            await asyncio.gather(music._tick_task, return_exceptions=True)
        await music.supervisor.shutdown(grace_seconds=.1)
        await app.executor.close()
        await parent.executor.close()
        assert not music.controller._deletions.snapshot().active
