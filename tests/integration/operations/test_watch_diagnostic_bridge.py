"""Real signed ASGI status transport and fake Discord send; no network or data."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from characterization.watch_support import AsgiSession, SECRET, harness, interaction
from discordbot.operations.adapters.hosting import TelemetryDrain
from discordbot.operations.adapters.watch_diagnostics import WatchDiagnostics, receive_watch_diagnostics
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.watch.adapters.control_server import build_control_app
from discordbot.watch.adapters.discord_io import DiscordInteraction
from discordbot.watch.adapters.control_schema import response_data
from .test_discord_logging import fixture
from .test_runtime import config_files


def test_production_watch_wires_observer_to_authenticated_status(config_files):
    from discordbot.composition.config import PlatformConfig, Environment, ServiceKind
    from discordbot.composition.production_watch import assemble
    from discordbot.operations.adapters.configuration import load_settings
    path, credentials = config_files
    settings = load_settings(path, credentials, 'watch-web')
    runtime, feature, _, drain, _ = assemble(PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'synthetic'), settings)
    runtime.telemetry.emit('watch.metadata', component='watch', result='unavailable',
        fields={'error_code':'external_temporary'})
    drain.flush()
    rows = feature.control_app.state.diagnostics()
    assert len(rows) == 1 and rows[0]['event'] == 'watch.metadata'
    assert rows[0]['error_code'] == 'external_temporary'


@pytest.mark.asyncio
async def test_signed_status_relays_failure_and_recovery_without_discord_in_web(tmp_path, caplog):
    async with harness(tmp_path) as h:
        relay = WatchDiagnostics(h.clock)
        app = build_control_app(h.service, SECRET)
        app.state.diagnostics = relay.drain
        transport = AsgiSession(app)
        old_transport, h.client.session = h.client.session, transport
        owner, now, channel = fixture()
        h.controller.diagnostics = receive_watch_diagnostics
        runtime = SimpleNamespace(telemetry_buffer=h.buffer)
        drain = TelemetryDrain(runtime, relay.capture)
        log = logging.getLogger('discordbot.watch.web')
        log.addHandler(owner.handler)
        caplog.set_level(logging.INFO, logger=log.name)
        try:
            # Actual maintenance failure emitter, not a manually rendered notice.
            heartbeat = h.writer.heartbeat
            h.writer.heartbeat = AsyncMock(side_effect=DatabaseUnavailableError('PRIVATE_SECRET'))
            await h.service.sweep()
            drain.flush()
            assert relay.pending
            await h.controller.refresh()  # signed request/response and schema validation
            await owner.deliver_one()
            content = channel.send.call_args.kwargs['content']
            assert 'Event: watch.maintenance' in content and 'Code: database_unavailable' in content
            assert 'Module: discordbot.watch.web' in content and 'PRIVATE_SECRET' not in content
            assert not relay.pending
            await h.controller.refresh()
            assert not owner.queue
            h.writer.heartbeat = heartbeat
            h.service.telemetry.emit('database.probe_recovered', component='database', result='success',
                fields={'healthy_probes': 2})
            drain.flush()
            now[0] = 5
            await h.controller.refresh()
            await owner.deliver_one()
            assert 'Recovery: recovered' in channel.send.call_args.kwargs['content']
            (tmp_path/'actual-payloads.json').write_text(json.dumps([
                {'content': c.kwargs['content'], 'allowed_mentions': c.kwargs['allowed_mentions'].to_dict()}
                for c in channel.send.call_args_list], ensure_ascii=False), encoding='utf-8')
        finally:
            h.writer.heartbeat = heartbeat
            log.removeHandler(owner.handler)
            await owner.stop()
            h.client.session = old_transport
            await transport.close()


@pytest.mark.asyncio
async def test_invite_failure_carries_typed_code_through_notifier(tmp_path, caplog):
    async with harness(tmp_path) as h:
        h.writer.create = AsyncMock(side_effect=DatabaseUnavailableError('PRIVATE_SECRET'))
        await h.controller.request(DiscordInteraction(interaction(h.clock), 'https://watch.example.test'))
        owner, _, channel = fixture()
        log = logging.getLogger('discordbot.events')
        log.addHandler(owner.handler)
        caplog.set_level(logging.INFO, logger=log.name)
        try:
            TelemetryDrain(SimpleNamespace(telemetry_buffer=h.buffer)).flush()
            await owner.deliver_one()
            text = channel.send.call_args.kwargs['content']
            assert 'Event: watch.invite' in text and 'Code: database_unavailable' in text
            assert 'exception_type: DatabaseUnavailableError' in text and 'PRIVATE_SECRET' not in text
        finally:
            log.removeHandler(owner.handler)
            await owner.stop()


def test_relay_capacity_expiry_dedup_and_untrusted_fields():
    now = [0.]
    relay = WatchDiagnostics(SimpleNamespace(monotonic=lambda: now[0]))
    def event(number):
        return SimpleNamespace(as_dict=lambda: {'event':'database.probe_failed', 'result':'failed',
            'sqlite_errorcode':number, 'message':'``` PRIVATE_SECRET', 'token':'PRIVATE_SECRET'})
    for _ in range(100): relay.capture(event(1))
    assert len(relay.pending) == 1
    for i in range(2, 40): relay.capture(event(i))
    assert len(relay.pending) == 32 and relay.dropped == 7
    rows = relay.drain()
    assert len(rows) == 8 and 'PRIVATE_SECRET' not in json.dumps(rows)
    now[0] = 301
    assert relay.drain() == [] and not relay.pending
    assert relay.dropped == 31


@pytest.mark.asyncio
async def test_bad_optional_diagnostics_do_not_break_health_or_send(tmp_path, caplog):
    async with harness(tmp_path) as h:
        def fail(_): raise RuntimeError('PRIVATE_SECRET')
        h.controller.diagnostics = fail
        await h.controller.refresh()
        assert h.controller.health.snapshot().ready and h.controller.diagnostic_failures == 1
        assert response_data('status', {'ready':True, 'diagnostics':'PRIVATE_SECRET'}) == {'ready':True,'diagnostics':[]}
        owner, _, channel = fixture()
        log = logging.getLogger('discordbot.watch.web')
        caplog.set_level(logging.INFO, logger=log.name)
        log.addHandler(owner.handler)
        try:
            receive_watch_diagnostics([{'event':'watch.maintenance','result':'failed',
                'timestamp':'PRIVATE_SECRET'}, {'event':'unknown','result':'failed'}])
            assert not owner.queue
            receive_watch_diagnostics([{'event':'watch.maintenance','result':'failed',
                'error_code':'database_unavailable', 'stage':'``` PRIVATE_SECRET', 'url':'PRIVATE_SECRET'}])
            await owner.deliver_one()
            assert channel.send.await_count == 1 and 'PRIVATE_SECRET' not in channel.send.call_args.kwargs['content']
        finally:
            log.removeHandler(owner.handler)
            await owner.stop()


def test_telemetry_observer_failure_does_not_stop_drain(caplog):
    from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
    from datetime import datetime, timezone
    buffer = TelemetryBuffer(4)
    emitter = TelemetryEmitter(buffer=buffer, clock=SimpleNamespace(now=lambda: datetime.now(timezone.utc)),
        service='watch-web', environment='test', release='test')
    def fail(_): raise RuntimeError('PRIVATE_SECRET')
    drain = TelemetryDrain(SimpleNamespace(telemetry_buffer=buffer), fail)
    emitter.emit('watch.maintenance', component='watch', result='failed')
    drain.flush()
    assert len(buffer) == 0 and drain.observer_failures == 1
