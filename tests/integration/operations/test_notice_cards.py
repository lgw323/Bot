"""Single-card presentation on fake Discord transports; no real messages."""
from datetime import datetime, timedelta, timezone
import json
import logging

import discord
import pytest

from discordbot.operations.adapters.discord_logging import Notice, notice
from discordbot.operations.adapters.notice_cards import CardMetadata, notice_embed
from discordbot.operations.adapters.operation_notifications import result_content, startup_content
from .test_discord_logging import fixture, record
from .test_operation_notifications import outcome, NOW


def payload(channel):
    sent = channel.send.call_args.kwargs
    assert 'content' not in sent
    assert sent['allowed_mentions'].to_dict()['parse'] == []
    return sent['embed'].to_dict()


@pytest.mark.asyncio
async def test_startup_fields_and_utc_footer_are_inside_one_card(tmp_path):
    owner, _, channel = fixture()
    owner.release = 'running-release'
    owner.clock.now = lambda: NOW
    text, card = startup_content(owner.release, outcome(tmp_path, 'in_progress', stage='checkpoint'), NOW)
    owner.enqueue(Notice('연결 확인', text, 0x3498DB, card=card))
    await owner.deliver_one()
    body = payload(channel)
    assert channel.send.await_count == 1 and body['title'] == '연결 확인'
    assert '전체 서비스의 준비 완료를 뜻하지는 않습니다' in body['description']
    assert '직접 원인을 확정하지 않습니다' in body['description']
    fields = {row['name']: row['value'] for row in body['fields']}
    assert fields['시작 원인'] == '확인되지 않음'
    assert '최종 완료 검증 대기' in fields['확인된 최근 운영 기록']
    assert body['footer']['text'] == '실행 버전: running-release · 시각(UTC): 2026-10-30T00:00:00+00:00'
    await owner.stop()


@pytest.mark.asyncio
async def test_recovery_is_connection_only_and_resumed_ready_do_not_duplicate():
    owner, clock, channel = fixture()
    owner.clock.now = lambda: NOW
    await owner.ready(); await owner.deliver_one()
    await owner.disconnected(); clock[0] = 11
    await owner.resumed(); await owner.ready(); await owner.deliver_one()
    body = payload(channel)
    assert channel.send.await_count == 2
    assert '전체 서비스 준비 상태는 별도 확인' in body['description']
    assert {f['name']:f['value'] for f in body['fields']}['중단 원인'] == '확인되지 않음'
    assert body['fields'][0]['value'] == '약 11초'
    assert '시각(UTC)' in body['footer']['text']
    await owner.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('result,stage,operation', [
    ('ok', 'complete', 'restart'), ('failed', 'readiness', 'update'),
    ('ok_cleanup_failed', 'retention', 'update'), ('ok', 'unchanged', 'update')])
async def test_operation_record_version_is_not_claimed_as_current_version(tmp_path, result, stage, operation):
    owner, _, channel = fixture()
    owner.release = 'actually-running'
    title, text, color, card = result_content(outcome(tmp_path, result, operation=operation, stage=stage))
    owner.enqueue(Notice(title, text, color, card=card))
    await owner.deliver_one()
    body = payload(channel)
    assert '작업 기록 버전: release' in body['footer']['text']
    assert '실행 버전:' not in body['footer']['text'] and 'actually-running' not in json.dumps(body)
    fields = {field['name']:field['value'] for field in body['fields']}
    assert set(fields) == {'단계', '작업 추적(축약)'}
    assert fields['작업 추적(축약)'] == 'aaaaaaaa…'
    assert fields['단계'] == {'complete':'완료 확인','readiness':'준비 확인',
        'retention':'보존본 정리','unchanged':'변경 없음'}[stage]
    if stage == 'unchanged':
        assert '실행하지 않았습니다' in body['description']
        assert '건강 상태를 검증했다는 뜻은 아닙니다' in body['description']
    await owner.stop()


@pytest.mark.asyncio
async def test_all_embed_slots_keep_private_record_content_out_and_original_event_time():
    owner, _, channel = fixture()
    owner.release = '/home/PRIVATE/release?token=PRIVATE'
    owner.clock.now = lambda: NOW + timedelta(hours=1)
    item = notice(record(logging.ERROR, message='PRIVATE %s', fields={
        'event': 'music.work_failed', 'error_code': 'internal',
        'timestamp': NOW.isoformat(), 'token': 'PRIVATE', 'user_id': 'PRIVATE',
        'sql': 'PRIVATE', 'url': 'https://PRIVATE/?token=PRIVATE',
        'stage': '``` PRIVATE', 'correlation_id': 'PRIVATE'}))
    owner.enqueue(item)
    await owner.deliver_one()
    body = payload(channel)
    assert 'PRIVATE' not in json.dumps(body, ensure_ascii=False)
    assert body['description'].count('```') == 2
    assert '실행 버전: 미확인' in body['footer']['text']
    assert NOW.isoformat(timespec='seconds') in body['footer']['text']
    assert (NOW + timedelta(hours=1)).isoformat() not in body['footer']['text']
    assert {field['name'] for field in body['fields']} == {'중요도', '구성 요소', '복구 상태'}
    await owner.stop()


@pytest.mark.asyncio
async def test_429_retry_preserves_whole_card_nonce_and_occurrence_time():
    owner, clock, channel = fixture()
    owner.clock.now = lambda: NOW
    owner.enqueue(Notice('알림', '안전한 설명', 0))
    channel.send.side_effect = discord.RateLimited(10)
    await owner.deliver_one()
    first = channel.send.call_args.kwargs
    owner.clock.now = lambda: NOW + timedelta(hours=1)
    clock[0] = 10; channel.send.side_effect = None
    await owner.deliver_one()
    second = channel.send.call_args.kwargs
    assert first['nonce'] == second['nonce']
    assert first['embed'].to_dict() == second['embed'].to_dict()
    assert owner.retries == 1 and owner.delivered == 1
    await owner.stop()


@pytest.mark.parametrize('title,description,card', [
    ('🧪'*129, 'safe', CardMetadata()), ('safe', '🧪'*1001, CardMetadata()),
    ('safe', 'safe', CardMetadata((('n'*257, 'safe'),))),
    ('safe', 'safe', CardMetadata((('safe', '🧪'*513),))),
    ('safe', 'safe', CardMetadata(tuple(('n', 'v') for _ in range(26)))),
    ('safe', 'safe', CardMetadata(tuple(('n', 'v'*1024) for _ in range(6)))),
    ('safe', '\ud800', CardMetadata()),
    ('safe', 'safe', CardMetadata(occurred_at=NOW.replace(tzinfo=None))),
])
def test_malformed_or_over_budget_cards_fail_closed(title, description, card):
    with pytest.raises((ValueError, UnicodeError)):
        notice_embed(title, description, 0, card.with_context('release', NOW))


def test_utf16_boundaries_and_utc_conversion():
    card = CardMetadata((('n'*256, '🧪'*512),), 'release',
        NOW.astimezone(timezone(timedelta(hours=9))))
    body = notice_embed('🧪'*128, '🧪'*1000, 0, card).to_dict()
    assert '2026-10-30T00:00:00+00:00' in body['footer']['text']
    assert len(body['description'].encode('utf-16-le')) // 2 == 2000


def test_exact_aggregate_limit_accepts_6000_and_rejects_one_more():
    card = CardMetadata(release='release', occurred_at=NOW)
    base = notice_embed('t', 'd'*2000, 0, card).to_dict()
    footer_size = len(base['footer']['text'].encode('utf-16-le')) // 2
    remaining = 6000 - 1 - 2000 - footer_size - 3*1025 - 1
    fields = (('n', 'v'*1024),)*3 + (('n', 'v'*remaining),)
    card = CardMetadata(fields, 'release', NOW)
    body = notice_embed('t', 'd'*2000, 0, card).to_dict()
    assert sum(len(text.encode('utf-16-le')) // 2 for text in
        [body['title'], body['description'], body['footer']['text'],
         *[text for field in body['fields'] for text in (field['name'], field['value'])]]) == 6000
    with pytest.raises(ValueError, match='total limit'):
        notice_embed('t', 'd'*2000, 0, CardMetadata(fields[:-1]+(('n', 'v'*(remaining+1)),), 'release', NOW))


@pytest.mark.asyncio
async def test_renderer_failure_drops_without_plain_text_network_or_raw_error(monkeypatch, capsys):
    from discordbot.operations.adapters import discord_logging as module
    owner, _, channel = fixture()
    owner.enqueue(Notice('safe', 'safe', 0))
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE raw token')
    monkeypatch.setattr(module, 'notice_embed', fail)
    await owner.deliver_one()
    assert channel.send.await_count == 0
    assert owner.format_failures == owner.dropped == 1 and owner.uncertain == 0
    assert capsys.readouterr().err == ''
    await owner.stop()


@pytest.mark.asyncio
async def test_bad_operation_presentation_never_claims_or_retries_forever(tmp_path, monkeypatch):
    from discordbot.operations.adapters import discord_logging as module
    from .test_operation_notifications import fixture as operation_fixture
    owner, clock, channel, _ = operation_fixture(tmp_path)
    row = outcome(tmp_path)
    await owner.poll_operations()
    def fail(*args, **kwargs):
        raise ValueError('PRIVATE formatter detail')
    monkeypatch.setattr(module, 'notice_embed', fail)
    await owner.deliver_one()
    assert not (tmp_path / 'operation-notice.json').exists()
    assert channel.send.await_count == 0 and owner.uncertain == 0
    assert owner.format_failures == owner.dropped == 1
    clock[0] = 60
    await owner.poll_operations()
    assert not owner.queue  # No endless re-admission of the malformed alert.
    assert owner.operations.current == row  # Durable outcome remains for the panel.
    await owner.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('event',['task.failed','task.deadline_exceeded'])
async def test_panel_task_failure_alert_does_not_trigger_another_panel_move(event):
    from unittest.mock import Mock
    owner,_,channel=fixture()
    owner.on_delivered=Mock()
    owner.enqueue(notice(record(logging.ERROR,fields={'event':event,'result':'failed',
        'task_name':'panel-follow-notices','owner_type':'operations'})))
    await owner.deliver_one()
    assert channel.send.await_count==1
    owner.on_delivered.assert_not_called()
    await owner.stop()
