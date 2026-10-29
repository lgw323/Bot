"""Copyable diagnostics retain cause categories, never private payloads."""
import logging

import pytest

from discordbot.operations.adapters.discord_logging import notice
from .test_discord_logging import record, fixture


def test_busy_notice_keeps_stage_and_original_event_in_text_block():
    row = record(logging.INFO, 'discordbot.events', fields={
        'event': 'database.probe_contention', 'result': 'failed',
        'error_code': 'database_unavailable', 'stage': 'probe_configure',
        'configure_step': 'synchronous', 'exception_family': 'sqlite_operational',
        'sqlite_family': 'busy', 'sqlite_errorcode': 5, 'probe_disposition': 'bounded_busy',
        'incident_id': 'a' * 32, 'timestamp': '2026-10-27T01:02:03+00:00',
        'close_succeeded': True, 'cleanup_failed': False,
        'message': 'private chat', 'token': 'secret', 'sql': 'private SQL'})
    item = notice(row)
    assert item.description.startswith('```text\n') and item.description.endswith('\n```')
    for value in ('database.probe_contention', 'probe_configure', 'synchronous',
                  'sqlite_operational', 'busy', 'bounded_busy', 'a' * 32, '2026-10-27T01:02:03'):
        assert value in item.description
    assert 'private' not in item.description and 'secret' not in item.description
    assert len(item.description) < 1900


def test_recovery_is_visible_but_routine_info_and_forged_recovery_are_not():
    fields = {'event': 'database.probe_recovered', 'result': 'success', 'healthy_probes': 2}
    item = notice(record(logging.INFO, 'discordbot.events', fields=fields))
    assert item is not None and 'Recovery: recovered' in item.description
    assert item.color == 0x2ECC71
    assert notice(record(logging.INFO, fields={'event': 'music.work_succeeded'})) is None
    assert notice(record(logging.INFO, 'external', fields=fields)) is None


def test_dedup_ignores_new_time_and_work_identity_but_keeps_failure_and_recovery():
    owner, _, _ = fixture()
    for n in range(20):
        row = record(logging.WARNING, fields={'event': 'music.work_failed', 'stage': 'connect',
            'error_code': 'internal', 'exception_type': 'RuntimeError', 'work_id': f'{n:032x}'})
        row.created += n
        owner.enqueue(notice(row))
    assert len(owner.queue) == 1
    owner.enqueue(notice(record(logging.INFO, 'discordbot.events', fields={
        'event': 'database.probe_recovered', 'result': 'success'})))
    assert len(owner.queue) == 2


@pytest.mark.asyncio
async def test_code_block_is_message_content_for_copy_button():
    owner, _, channel = fixture()
    item = notice(record(logging.ERROR))
    owner.enqueue(item)
    await owner.deliver_one()
    assert channel.send.call_args.kwargs['content'] == item.description
    assert channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'] == []
    await owner.stop()


def test_injected_fields_cannot_break_fence_or_export_payload():
    fields = dict(event='music.work_failed', error_code='internal')
    for key in ('stage', 'exception_type', 'state_before', 'state_after', 'work_id',
                'incident_id', 'configure_step', 'timestamp', 'reason', 'probe_disposition'):
        fields[key] = '```\n@everyone private chat token=secret https://private.invalid'
    item = notice(record(logging.ERROR, fields=fields))
    assert item.description.count('```') == 2
    for value in ('private', '@everyone', 'secret', 'https:'):
        assert value not in item.description


def test_actual_telemetry_drain_delivers_failure_and_recovery(caplog):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from discordbot.operations.adapters.hosting import TelemetryDrain
    from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
    buffer = TelemetryBuffer(8)
    emitter = TelemetryEmitter(buffer=buffer, clock=SimpleNamespace(now=lambda: datetime.now(timezone.utc)),
        service='discord-bot', environment='test', release='synthetic')
    owner, _, _ = fixture()
    log = logging.getLogger('discordbot.events')
    caplog.set_level(logging.INFO, logger='discordbot.events')
    log.addHandler(owner.handler)
    try:
        emitter.emit('database.probe_failed', component='operations', result='failed',
            fields={'error_code': 'database_unavailable', 'probe_disposition': 'hard', 'incident_id': 'a' * 32})
        # The production ProbePolicy is responsible for recovery admission; this tests routing only.
        emitter.emit('database.probe_recovered', component='operations', result='success',
            fields={'healthy_probes': 2, 'incident_id': 'b' * 32})
        TelemetryDrain(SimpleNamespace(telemetry_buffer=buffer)).flush()
        assert len(owner.queue) == 2
        assert 'latched; operator review required' in owner.queue[0].description
        assert 'Recovery: recovered' in owner.queue[1].description
    finally:
        log.removeHandler(owner.handler)
        owner.handler.close()


@pytest.mark.parametrize('timestamp', ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00'])
def test_out_of_range_timezone_conversion_falls_back_to_record_time(timestamp):
    row = record(logging.ERROR, fields={'timestamp': timestamp})
    row.created = 0
    assert 'Time: 1970-01-01T00:00:00+00:00' in notice(row).description


@pytest.mark.parametrize('boundary', ['format', 'enqueue'])
def test_notification_failure_does_not_escape_or_print_private_record(monkeypatch, capsys, boundary):
    from discordbot.operations.adapters import discord_logging as module
    owner, _, _ = fixture()
    def broken(*args):
        raise ValueError('private exception token')
    if boundary == 'format':
        monkeypatch.setattr(module, 'notice', broken)
    else:
        monkeypatch.setattr(owner, 'enqueue', broken)
    log = logging.getLogger('discordbot.synthetic-notice-review')
    log.addHandler(owner.handler)
    try:
        log.warning('private chat %s', 'private token')
        assert owner.gauges()['discord_log_format_failures'] == 1
        assert owner.dropped == 1 and not owner.queue
        assert capsys.readouterr().err == ''
    finally:
        log.removeHandler(owner.handler)
        owner.handler.close()


def test_maximal_diagnostic_payload_stays_within_discord_limits():
    from discordbot.platform.diagnostics import EXCEPTION_TYPES
    from discordbot.storage.adapters.probe_diagnostics import STAGES, CONFIGURE_STEPS, FAMILIES
    fields = dict(event='database.probe_contention', error_code='database_unavailable',
        result='external_permanent', http_status=599,
        stage=max(STAGES, key=len), configure_step=max(CONFIGURE_STEPS, key=len),
        exception_family=max(FAMILIES, key=len), sqlite_family='constraint', errno_category='capacity',
        sqlite_errorcode=0xFFFFFF, connection_opened=False, close_succeeded=False, cleanup_failed=False,
        exception_type=max(EXCEPTION_TYPES, key=len), cause_type=max(EXCEPTION_TYPES, key=len),
        state_before='tts_starting', state_after='tts_starting', probe_disposition='recovery_expired',
        reason='executable_not_found', voice_connected=False, probe_recovery_safe=False,
        healthy_probes=100000, read_admitted=100000, write_admitted=100000, child_exit_code=-255,
        work_id='a'*32, incident_id='b'*32)
    item = notice(record(logging.ERROR, name='discordbot.'+'x'*89, fields=fields))
    assert len(item.description.encode('utf-16-le')) // 2 <= 2000
    assert len(item.title.encode('utf-16-le')) // 2 <= 256
    assert item.description.count('```') == 2


def test_recovery_incident_ids_and_timestamps_do_not_bypass_duplicate_window():
    owner, now, _ = fixture()
    for index in range(500):
        row = record(logging.INFO, 'discordbot.events', fields={
            'event': 'database.probe_recovered', 'result': 'success', 'healthy_probes': 2,
            'incident_id': f'{index:032x}'})
        row.created += index
        owner.enqueue(notice(row))
    assert len(owner.queue) == len(owner.recent) == 1
    now[0] = 60
    owner.enqueue(notice(row))
    assert len(owner.queue) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('event,result,fields,code', [
    *[('music.ui_failed' if stage == 'selection' else 'music.command_failed',
       'failed', {'stage': stage, 'error_code': 'internal'}, 'internal')
      for stage in ('request', 'message_request', 'selection')],
    *[('summary.request', result, {'reason': 'transport_error'}, result)
      for result in ('external_temporary', 'external_permanent', 'database_unavailable',
                     'deadline_exceeded', 'capacity')],
    ('summary.preload', 'failed', {}, 'unspecified'),
    ('summary.response', 'delivery_failed', {}, 'unspecified'),
    ('watch.invite', 'failed', {}, 'unspecified'),
    ('watch.maintenance', 'failed', {}, 'unspecified'),
    ('watch.shutdown', 'deadline', {}, 'deadline_exceeded'),
    ('watch.shutdown', 'uncertain_close', {}, 'unspecified'),
    ('watch.metadata', 'unavailable', {}, 'unspecified'),
])
async def test_feature_failure_identity_survives_actual_telemetry_send(
        caplog, tmp_path, event, result, fields, code):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from discordbot.operations.adapters.hosting import TelemetryDrain
    from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
    owner, _, channel = fixture()
    buffer = TelemetryBuffer(8)
    emitter = TelemetryEmitter(buffer=buffer,
        clock=SimpleNamespace(now=lambda: datetime(2026, 10, 27, tzinfo=timezone.utc)),
        service='discord-bot', environment='test', release='synthetic')
    log = logging.getLogger('discordbot.events')
    caplog.set_level(logging.INFO, logger=log.name)
    log.addHandler(owner.handler)
    try:
        emitter.emit(event, component=event.split('.')[0], result=result,
                     fields={**fields, 'content': 'PRIVATE_PAYLOAD', 'token': 'PRIVATE_SECRET'})
        TelemetryDrain(SimpleNamespace(telemetry_buffer=buffer)).flush()
        await owner.deliver_one()
        assert channel.send.await_count == 1
        actual = channel.send.call_args.kwargs
        content = actual['content']
        (tmp_path / 'fake-send.json').write_text(json.dumps({'content': content,
            'embed': actual['embed'].to_dict(), 'allowed_mentions': actual['allowed_mentions'].to_dict()},
            ensure_ascii=False), encoding='utf-8')
        assert f'Event: {event}' in content and f'Feature: {event.split(".")[0]}' in content
        assert f'Code: {code}' in content and f'result: {result}' in content
        for key, value in fields.items():
            if key != 'error_code':
                assert f'{key}: {value}' in content
        assert 'PRIVATE_' not in content and content.count('```') == 2
        assert len(content.encode('utf-16-le')) // 2 <= 2000
        assert actual['allowed_mentions'].to_dict()['parse'] == []
    finally:
        log.removeHandler(owner.handler)
        await owner.stop()


@pytest.mark.parametrize('event,result', [
    ('summary.request', 'success'), ('summary.request', 'cancellation'),
    ('summary.request', 'not_found'), ('summary.request', 'validation'),
    ('summary.request', 'authorization'), ('summary.request', 'conflict'),
    ('watch.cleanup', 'pending'), ('watch.invite_cleanup', 'pending'),
    ('watch.compensation', 'pending_expiry'), ('watch.metadata', 'success'),
    ('other.request', 'external_temporary'), ('summary.request', 'private result'),
])
def test_feature_result_admission_does_not_promote_routine_or_unknown_events(event, result):
    assert notice(record(logging.INFO, 'discordbot.events', fields={'event': event, 'result': result})) is None


def test_summary_failure_code_precedence_http_bounds_and_extended_fields_are_safe():
    fields = {'event': 'summary.request', 'result': 'external_temporary',
              'reason': 'http_server_error', 'http_status': 503}
    item = notice(record(logging.INFO, 'discordbot.events', fields=fields))
    assert item is not None and 'Code: external_temporary' in item.description
    assert 'http_status: 503' in item.description and 'reason: http_server_error' in item.description
    fields['error_code'] = 'database_unavailable'
    assert 'Code: database_unavailable' in notice(record(logging.INFO, fields=fields)).description
    for invalid in (True, 99, 600, '503', '```\n@everyone PRIVATE_SECRET'):
        fields.update(http_status=invalid, reason='```\nPRIVATE_SECRET')
        content = notice(record(logging.INFO, fields=fields)).description
        assert 'http_status:' not in content and 'reason:' not in content
        assert 'PRIVATE_' not in content and content.count('```') == 2
    assert notice(record(logging.INFO, 'external', fields=fields)) is None


def test_summary_typed_failure_dedup_ignores_identity_but_separates_error_codes():
    owner, now, _ = fixture()
    try:
        for number in range(20):
            owner.enqueue(notice(record(logging.INFO, fields={'event': 'summary.request',
                'result': 'external_temporary', 'reason': 'http_server_error', 'http_status': 503,
                'work_id': f'{number:032x}'})))
        assert len(owner.queue) == 1
        owner.enqueue(notice(record(logging.INFO, fields={'event': 'summary.request',
            'result': 'external_permanent'})))
        assert len(owner.queue) == 2
        now[0] = 60
        owner.enqueue(notice(record(logging.INFO, fields={'event': 'summary.request',
            'result': 'external_permanent'})))
        assert len(owner.queue) == 3
    finally:
        owner.handler.close()
