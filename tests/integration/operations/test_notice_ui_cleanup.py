"""Presentation-only cleanup; full identities, authority and readiness stay intact."""
from datetime import datetime, timezone
import json

import pytest

from discordbot.operations.adapters.discord_admin import STAGE_LABELS, status_embed
from discordbot.operations.adapters.notice_cards import display_release, display_trace, notice_embed, stage_label
from discordbot.operations.adapters.operation_notifications import operation_key, result_content


NOW = datetime(2026, 10, 31, 9, 41, 52, tzinfo=timezone.utc)
RELEASE = 'r-b4a27730888dc62a-bd1ffa96253a4d84'


def snapshot(**updates):
    value = dict(release=RELEASE, ready=True, consumer_enabled=False,
        request_operation=None, request_result=None, outcome=None, pending=False)
    return {**value, **updates}


def outcome(**updates):
    value = dict(version=1, id='b'*32, operation='update', source='operator',
        result='ok', stage='complete', release=RELEASE, timestamp=NOW.isoformat(), receipt=None)
    return {**value, **updates}


def test_full_release_identity_is_compact_but_keeps_code_and_dependency_parts():
    assert display_release(RELEASE) == 'b4a27730… / bd1ffa96…'
    assert display_release(RELEASE.replace('bd1ffa96', '00000000')) != display_release(RELEASE)
    assert display_release('b'*40) == 'bbbbbbbb…'
    assert display_release('running-release') == 'running-release'
    assert display_release('safe-'+'x'*60) == 'safe-'+'x'*15+'…'


@pytest.mark.parametrize('value', [None, {}, True, '/home/PRIVATE/token', 'token=PRIVATE',
    '``` @everyone', 'https://PRIVATE/?token=PRIVATE', 'x'*97])
def test_bad_public_release_identity_never_falls_back_to_raw_text(value):
    assert display_release(value) == '미확인'


def test_trace_display_is_explicitly_abbreviated_and_not_an_authority_key():
    first = outcome(id='a'*8+'b'*24)
    second = outcome(id='a'*8+'c'*24)
    assert display_trace(first['id']) == display_trace(second['id']) == 'aaaaaaaa…'
    assert operation_key(first) != operation_key(second)
    for raw in [None, 1, 'PRIVATE', 'A'*32, 'a'*31, '/private/path', '``` @everyone']:
        assert display_trace(raw) == '미확인'


@pytest.mark.parametrize('code,label', list(STAGE_LABELS.items()))
def test_notice_stage_labels_match_the_existing_validated_stage_contract(code, label):
    assert stage_label(code) == label


@pytest.mark.parametrize('value', [None, {}, True, 'PRIVATE', '``` @everyone', 'private/path'])
def test_unknown_stage_has_fixed_korean_label_without_raw_fallback(value):
    assert stage_label(value) == '미확인'


def test_result_card_uses_korean_stage_short_trace_and_distinct_record_version():
    row = outcome()
    title, description, color, card = result_content(row)
    body = notice_embed(title, description, color, card).to_dict()
    fields = {f['name']: f['value'] for f in body['fields']}
    assert fields == {'단계': '완료 확인', '작업 추적(축약)': 'bbbbbbbb…'}
    assert 'complete' not in json.dumps(body, ensure_ascii=False)
    assert row['id'] not in json.dumps(body) and row['release'] not in json.dumps(body)
    assert row['id'] == 'b'*32 and row['release'] == RELEASE
    assert card.release == RELEASE and card.occurred_at == NOW
    assert body['footer']['text'].startswith('작업 기록 버전: b4a27730… / bd1ffa96…')
    assert '실행 버전:' not in body['footer']['text']


@pytest.mark.parametrize('result,stage', [('failed', 'readiness'), ('ok_cleanup_failed', 'retention'), ('ok', 'unchanged')])
def test_ui_cleanup_keeps_failure_cleanup_and_unchanged_meanings(result, stage):
    _, description, _, card = result_content(outcome(result=result, stage=stage))
    assert dict(card.fields)['단계'] == STAGE_LABELS[stage]
    if stage == 'unchanged':
        assert '실행하지 않았습니다' in description and '건강 상태를 검증했다는 뜻은 아닙니다' in description
    elif result == 'failed':
        assert '실패했습니다' in description and '복구 여부' in description
    else:
        assert '정리가 실패했습니다' in description


def test_empty_panel_omits_no_request_unknown_time_and_unknown_stage_rows():
    body = status_embed(snapshot()).to_dict()
    description = body['description']
    assert '기본 준비 검사: 통과' in description and '봇: 정상' not in description
    assert '수동 실행 타이머: 꺼짐 · 요청 불가' in description
    assert '운영 기록 없음' in description
    for placeholder in ['시각 미상', '요청 기록:', '최근 작업 기록:', '결과 기록 시각', '결과 기록 단계']:
        assert placeholder not in description
    fields = {f['name']: f['value'] for f in body['fields']}
    assert fields['실행 버전'] == display_release(RELEASE)
    assert 'DB probe' in fields['검사 범위'] and 'Discord 연결' in fields['검사 범위']
    assert '음악 초기화/복원' in fields['검사 범위']
    assert '외부 API·음성 재생·웹 기능 전체의 성공 확인은 별도' in fields['검사 범위']


def test_timer_on_is_not_claimed_to_prove_service_control_authority():
    description = status_embed(snapshot(ready=False, consumer_enabled=True)).description
    assert '기본 준비 검사: 미통과' in description
    assert '켜짐 · 제어 권한 별도 확인' in description and '사용 가능' not in description


def test_request_without_timestamp_remains_unconfirmed_without_fake_empty_outcome_rows():
    description = status_embed(snapshot(request_operation='restart', request_result='in_progress', pending=True)).description
    assert '요청 기록: 재시작 · 시작 기록·완료 미확인' in description
    assert '현재 실행 여부나 완료를 확정하지 않습니다' in description
    assert '진행 중' not in description
    for absent in ['결과 기록 시각', '결과 기록 단계', '시각 미상', '운영 기록 없음']:
        assert absent not in description


def test_historical_outcome_keeps_actual_time_and_stage_without_current_running_claim():
    row = {'id':'a'*32, 'operation':'update', 'result':'in_progress',
           'stage':'readiness', 'timestamp':'2020-01-01T01:00:00Z'}
    description = status_embed(snapshot(outcome=row, pending=True)).description
    assert '2020-01-01T01:00:00Z' in description and '준비 확인' in description
    assert '시작 기록·완료 미확인' in description and '진행 중' not in description
