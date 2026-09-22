"""Real nested supervisors must not disappear behind successful stop coroutines."""
import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from discordbot.composition.config import Environment, PlatformConfig, RuntimePolicy, ServiceKind
from discordbot.composition.runtime import ProcessRuntime, RuntimeState, require_clean_shutdown
from discordbot.platform.clock import SystemClock
from discordbot.platform.errors import ShutdownError, StartupError
from discordbot.platform.tasks import TaskSpec, CancellationBehavior
from discordbot.watch.adapters.discord_runtime import DiscordWatchResource


class Resource:
    def __init__(self, name, events, required=True):
        self.name, self.events, self.required = name, events, required
    async def start(self):
        self.events.append('start:' + self.name)
        if not self.required:
            raise RuntimeError('synthetic optional failure')
    async def stop(self):
        self.events.append('stop:' + self.name)


def setup_watch(monkeypatch):
    config = PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, 'synthetic', runtime=RuntimePolicy(1, .2))
    shell = ProcessRuntime(config=config)
    bot = NS(add_cog=AsyncMock(), remove_cog=AsyncMock())
    watch = DiscordWatchResource(bot, 'https://watch.example.test', 'http://127.0.0.1:9001',
        'synthetic-control-key-for-offline-tests', 1, 1, SystemClock(), shell.telemetry, NS())
    watch.client.start, watch.client.stop = AsyncMock(), AsyncMock()
    watch.client.call = AsyncMock(return_value={'ready': True})
    original = watch.controller.supervisor.shutdown
    async def bounded(**kwargs):
        return await original(grace_seconds=.03)
    monkeypatch.setattr(watch.controller.supervisor, 'shutdown', bounded)
    return config, shell, bot, watch


async def hostile(watch, entered, release):
    async def work():
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
    task = watch.controller.supervisor.start(TaskSpec('nested', 'test', 'one', 'one', 5,
        cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), work)
    await entered.wait()
    return task


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['clean', 'eventual', 'incomplete', 'failure'])
async def test_degraded_start_nested_cleanup_propagates(monkeypatch, outcome):
    config, shell, bot, watch = setup_watch(monkeypatch)
    events, release, entered = [], asyncio.Event(), asyncio.Event()
    mandatory = Resource('mandatory', events)
    app = ProcessRuntime(config=config, resources=(mandatory, watch, Resource('optional', events, False)))
    task = None
    try:
        await app.start()
        assert app.health.snapshot().ready and events == ['start:mandatory', 'start:optional', 'stop:optional']
        if outcome in ('eventual', 'incomplete'):
            task = await hostile(watch, entered, release)
            if outcome == 'eventual':
                asyncio.get_running_loop().call_later(.01, release.set)
        if outcome == 'failure':
            watch.client.stop.side_effect = RuntimeError('synthetic cleanup failure')
        report = await asyncio.wait_for(app.shutdown(), .5)
        if outcome in ('clean', 'eventual'):
            require_clean_shutdown(report)
            assert app._started_resources == [] and events[-1] == 'stop:mandatory'
            assert not watch.controller.supervisor.snapshot().active
            assert watch.closed
        else:
            with pytest.raises(ShutdownError):
                require_clean_shutdown(report)
            assert app.state is RuntimeState.FAILED
            assert app._started_resources == [mandatory, watch]
            assert 'stop:mandatory' not in events and not watch.closed
            if outcome == 'incomplete':
                assert watch.controller.supervisor.snapshot().active
                watch.client.stop.assert_not_awaited()
        assert await app.shutdown() == report
        bot.remove_cog.assert_awaited_once()
        assert events.count('stop:optional') == 1
    finally:
        release.set()
        if task:
            await asyncio.wait_for(task, 1)
        await shell.executor.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('cleanup', ['clean', 'incomplete', 'failure', 'unmarked-failure'])
async def test_required_aggregate_retains_failed_partial_child(monkeypatch, cleanup):
    from discordbot.composition import production_discord as composition
    config, shell, bot, watch = setup_watch(monkeypatch)
    events, release, entered = [], asyncio.Event(), asyncio.Event()
    task = None
    async def add(_):
        nonlocal task
        if cleanup == 'incomplete':
            task = await hostile(watch, entered, release)
        raise RuntimeError('synthetic partial start')
    bot.add_cog = add
    if cleanup == 'failure':
        watch.client.stop.side_effect = RuntimeError('synthetic child cleanup failure')
    settings = NS(database=Path('unused'), master=1, main_channels=(), secrets=NS(gemini_key='synthetic',
        control_key='synthetic', discord_token='synthetic'), gemini_model='synthetic', public_origin='https://watch.example.test',
        control_port=9001, admin_channel=1, cache=Path('unused'), state=Path('unused'), music_channels=())
    replacements = dict(create_engagement_bot=lambda: bot, validate_candidate=AsyncMock(),
        EngagementResource=lambda *a: Resource('engagement', events), SummaryResource=lambda *a: Resource('summary', events),
        GeminiProvider=lambda *a: object(), DiscordWatchResource=lambda *a: watch,
        MusicResource=lambda *a, **k: Resource('music', events), SqliteMusicRepository=lambda *a: object(),
        DeferredMusic=lambda *a: Resource('deferred', events), Gateway=lambda *a: Resource('gateway', events))
    for name, value in replacements.items():
        monkeypatch.setattr(composition, name, value)
    if cleanup == 'unmarked-failure':
        class Unmarked(Resource):
            async def start(self):
                raise RuntimeError('synthetic partial member')
            async def stop(self):
                raise ShutdownError('synthetic member cleanup failure')
        watch = Unmarked('unmarked', events)
        monkeypatch.setattr(composition, 'DiscordWatchResource', lambda *a: watch)
    database = Resource('database', events)
    features = composition.DiscordFeatures(config, settings, database, SystemClock())
    app = ProcessRuntime(config=config, resources=(database, features))
    features.runtime = app
    try:
        with pytest.raises(StartupError):
            await asyncio.wait_for(app.start(), .5)
        assert not app.health.snapshot().ready
        report = await asyncio.wait_for(app.shutdown(), .5)
        if cleanup == 'clean':
            require_clean_shutdown(report)
            assert features.started == [] and app._partial_resources == []
            assert events[-3:] == ['stop:summary', 'stop:engagement', 'stop:database']
            assert watch.closed
        else:
            assert watch in features.started and app._partial_resources == [features]
            assert not any(event.startswith('stop:') for event in events)
            with pytest.raises(ShutdownError):
                require_clean_shutdown(report)
            if cleanup == 'incomplete':
                assert watch.controller.supervisor.snapshot().active
                watch.client.stop.assert_not_awaited()
            elif cleanup == 'failure':
                watch.client.stop.assert_awaited_once()
    finally:
        release.set()
        if task:
            await asyncio.wait_for(task, 1)
        await shell.executor.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['summary-service', 'summary-resource', 'watch-service', 'engagement', 'music'])
async def test_equivalent_nested_report_consumers_preserve_dependencies(kind):
    from unittest.mock import MagicMock
    from discordbot.platform.tasks import ShutdownReport
    from discordbot.summary.application.service import SummaryService
    from discordbot.summary.adapters.runtime import SummaryResource
    from discordbot.watch.application.service import WatchService
    from discordbot.engagement.adapters.discord_runtime import EngagementResource
    from discordbot.music.adapters.runtime import MusicResource
    supervisor = NS(shutdown=AsyncMock(return_value=ShutdownReport(0, 0, 1)))
    dependency = AsyncMock()
    owner = NS(supervisor=supervisor, background=supervisor, provider=NS(close=dependency),
        capture=MagicMock(), _results={}, _closed=False, _owns_bot=True, _stopped=False,
        _maintenance=None, health=MagicMock(), sessions={}, writer=NS(release=dependency),
        metadata=NS(close=dependency), epoch='synthetic', bot=MagicMock(), cog=None,
        controller=NS(close=MagicMock(), stop=AsyncMock()), service=NS(stop=dependency),
        startup_cleanup_complete=False, _service_started=True, scheduler=NS(stop=AsyncMock()),
        gateway=NS(receive=object()), ready=object(), message=object(), closed=False,
        _tick_task=None, _refresh_task=None, actors={}, dashboard_views={},
        processes=NS(close=dependency), ffmpeg=NS(close=dependency), cache=NS(close=dependency))
    owner.bot.remove_cog, owner.bot.close = AsyncMock(), dependency
    if kind == 'engagement':
        owner.cog = NS(qualified_name='synthetic')
    stop = {'summary-service': SummaryService.stop, 'summary-resource': SummaryResource.stop,
            'watch-service': WatchService.stop, 'engagement': EngagementResource.stop,
            'music': MusicResource.stop}[kind]
    with pytest.raises(ShutdownError):
        await asyncio.wait_for(stop(owner), .5)
    dependency.assert_not_awaited()
    supervisor.shutdown.assert_awaited_once()
    assert not owner.closed and not owner._closed


@pytest.mark.asyncio
async def test_aggregate_child_stop_error_retains_reverse_order_ownership():
    from discordbot.composition.production_discord import DiscordFeatures
    events = []
    class Broken(Resource):
        async def stop(self):
            self.events.append('stop:broken')
            raise ShutdownError('synthetic child failure')
    aggregate = object.__new__(DiscordFeatures)
    prerequisite, broken = Resource('prerequisite', events), Broken('broken', events)
    aggregate.started = [prerequisite, broken]
    with pytest.raises(ShutdownError):
        await asyncio.wait_for(aggregate.stop(), .5)
    assert aggregate.started == [prerequisite, broken]
    assert events == ['stop:broken'] and not aggregate.startup_cleanup_complete
