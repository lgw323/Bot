"""Production assembly contract; no sockets, credentials, DB or service operations."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def assembled(monkeypatch, tmp_path):
    from discordbot.composition import production_discord as module

    events, calls = [], {}
    bot = SimpleNamespace(is_ready=lambda: True)

    class Resource:
        startup_cleanup_complete = True

        def __init__(self, name):
            self.name = name
            self.started, self.failed, self.failed_restore = False, False, False
            self.controller = SimpleNamespace()
            self.actors = {}
            self.cache = SimpleNamespace(bytes=0)
            self.processes = SimpleNamespace(children={})
            self.service = SimpleNamespace(waiting=0)

        async def start(self):
            self.started = True
            events.append(('start', self.name))

        async def stop(self):
            events.append(('stop', self.name))

        def gauges(self):
            return {self.name + '_worker_enabled': 0.0}

    def factory(name):
        def make(*args, **kwargs):
            calls[name] = (args, kwargs)
            return Resource(name)
        return make

    def value(name):
        def make(*args, **kwargs):
            result = SimpleNamespace(kind=name)
            calls[name] = (args, kwargs, result)
            return result
        return make

    monkeypatch.setattr(module, 'create_engagement_bot', lambda: bot)
    monkeypatch.setattr(module, 'validate_candidate', AsyncMock())
    for symbol, name in [('EngagementResource', 'engagement'), ('SummaryResource', 'summary'),
                         ('DiscordWatchResource', 'watch'), ('MusicResource', 'music'),
                         ('DeferredMusic', 'deferred'), ('Gateway', 'gateway'),
                         ('DiscordLogging', 'logs'), ('OperationsPanel', 'panel')]:
        monkeypatch.setattr(module, symbol, factory(name))
    for symbol, name in [('GeminiProvider', 'provider'), ('SqliteMusicRepository', 'repository'),
                         ('Audit', 'audit'), ('RequestInbox', 'inbox'),
                         ('SystemdManualConsumer', 'availability'), ('OperationalStatus', 'status')]:
        monkeypatch.setattr(module, symbol, value(name))
    settings = SimpleNamespace(database=tmp_path/'db', state=tmp_path/'state', cache=tmp_path/'cache',
        audit=tmp_path/'audit', backups=tmp_path/'backups', operation_lock=tmp_path/'operation.lock', master=1, admin_channel=83,
        main_channels=(), music_channels=(), public_origin='https://watch.example.invalid', control_port=9001,
        secrets=SimpleNamespace(gemini_key='synthetic', control_key='synthetic', discord_token='synthetic'),
        gemini_model='synthetic-not-called', log_channel=76, discord_health_port=9010)
    config = SimpleNamespace(release='synthetic-release', service=SimpleNamespace(value='discord-bot'))
    feature = module.DiscordFeatures(config, settings, None, SimpleNamespace())
    feature.runtime = SimpleNamespace(supervisor=SimpleNamespace(), executor=SimpleNamespace(), telemetry=SimpleNamespace())
    return module, feature, settings, calls, events


@pytest.mark.asyncio
async def test_production_wires_persistent_controls_and_safe_results_to_existing_state(assembled):
    module, feature, settings, calls, events = assembled
    await feature.start()
    try:
        args, kwargs = calls['logs']
        assert args[1] == settings.log_channel != settings.admin_channel
        assert kwargs == dict(state=settings.state, executor=feature.runtime.executor, release=feature.config.release)
        args, kwargs, inbox = calls['inbox']
        assert args[:3] == (settings.state, settings.operation_lock, feature.runtime.executor)
        assert args[-1] == feature.config.release
        _, kwargs, status = calls['status']
        assert kwargs['result_reader'] is module.read_operation_result
        assert kwargs['readiness'].__self__ is feature
        assert kwargs['readiness']() is False  # No aggregate binding: fail closed.
        args, kwargs = calls['panel']
        assert args == (feature.bot,)
        assert kwargs['inbox'] is inbox and kwargs['status'] is status
        assert kwargs['master'] == settings.master and kwargs['channel'] == settings.log_channel
        assert kwargs['state'] == settings.state
        assert kwargs['executor'] is feature.runtime.executor
        assert kwargs['supervisor'] is feature.runtime.supervisor
        assert events[-2:] == [('start', 'logs'), ('start', 'panel')]
        assert feature.ready() is True
        assert feature.gauges()['panel_worker_enabled'] == 0.0
    finally:
        await feature.stop()
    assert events[-7:-5] == [('stop', 'panel'), ('stop', 'logs')]


@pytest.mark.asyncio
async def test_optional_notification_absence_creates_no_panel_or_execution_reader(assembled):
    _, feature, settings, calls, events = assembled
    settings.log_channel = None
    await feature.start()
    try:
        for name in ('logs', 'panel', 'inbox', 'availability', 'status', 'audit'):
            assert name not in calls
        assert feature.logs is None and feature.operations is None
        assert feature.ready() is True
        assert not settings.state.exists()
    finally:
        await feature.stop()
    assert all(name not in ('logs', 'panel') for _, name in events)


@pytest.mark.asyncio
async def test_panel_readiness_matches_http_when_feature_is_ready_but_other_gates_fail(assembled, monkeypatch):
    import httpx
    module, feature, settings, calls, _ = assembled
    await feature.start()
    flags = dict(platform=True, probe=True, listener=True)
    app_holder = {}
    runtime = SimpleNamespace(config=feature.config, executor=feature.runtime.executor,
        supervisor=feature.runtime.supervisor,
        health=SimpleNamespace(snapshot=lambda: SimpleNamespace(ready=flags['platform'])))
    monkeypatch.setattr(module, 'ProcessRuntime', lambda **kwargs: runtime)
    monkeypatch.setattr(module, 'SqliteDatabase', lambda *_: object())
    monkeypatch.setattr(module, 'DiscordFeatures', lambda *_: feature)
    monkeypatch.setattr(module, 'Probe', lambda *_: SimpleNamespace(ready=lambda: flags['probe']))
    monkeypatch.setattr(module, 'Servers', lambda *_: SimpleNamespace(ready=lambda: flags['listener']))

    def server(app, _port):
        app_holder['app'] = app
        return object()
    monkeypatch.setattr(module, 'server', server)
    module.assemble(feature.config, settings)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_holder['app']), base_url='http://test') as client:
            assert feature.ready() is True
            for failed_gate in ('platform', 'probe', 'listener', None):
                for name in flags:
                    flags[name] = name != failed_gate
                response = await client.get('/health/ready')
                available = failed_gate is None
                assert response.status_code == (200 if available else 503)
                assert feature.operational_ready() is available
                assert calls['status'][1]['readiness']() is available
    finally:
        await feature.stop()


@pytest.mark.asyncio
async def test_real_result_schema_and_panel_distinguish_pending_failure_and_cleanup(tmp_path):
    import json
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.discord_admin import OperationalStatus, status_embed
    from discordbot.operations.adapters.manual import RequestInbox
    from discordbot.operations.adapters.operation_results import OperationResults, read_operation_result
    from discordbot.platform.executors import BoundedExecutor

    executor = BoundedExecutor(workers=1, queue_capacity=4, name='integrated-operation-status')
    audit = tmp_path/'audit'
    audit.mkdir()
    inbox = RequestInbox(tmp_path, tmp_path/'lock', executor, Audit(audit), 'release1')
    status = OperationalStatus(inbox, SimpleNamespace(enabled=AsyncMock(return_value=True)),
                               'release1', lambda: True, read_operation_result)
    writer = OperationResults(tmp_path)
    try:
        writer.write('restart', 'manual', 'in_progress', 'accepted', 'release1',
                     identity='a'*32, receipt='b'*64)
        pending = await status.snapshot()
        assert pending['pending'] is True
        assert pending['outcome']['result'] == 'in_progress'
        writer.write('restart', 'manual', 'failed', 'readiness', 'release1',
                     identity='a'*32, receipt='b'*64)
        failed = await status.snapshot()
        assert failed['pending'] is False
        assert failed['revision'] != pending['revision']
        assert failed['outcome']['result'] == 'failed'
        assert '실패' in json.dumps(status_embed(failed).to_dict(), ensure_ascii=False)
        writer.write('update', 'unknown', 'ok_cleanup_failed', 'retention', 'release2',
                     identity='c'*32)
        cleanup = await status.snapshot()
        assert cleanup['pending'] is False
        assert cleanup['outcome']['result'] == 'ok_cleanup_failed'
        displayed = json.dumps(status_embed(cleanup).to_dict(), ensure_ascii=False)
        assert 'b'*64 not in displayed
        assert 'operation-result.json' not in displayed
    finally:
        await executor.close(grace_seconds=5)
