"""Selectable read-only service UI; no real collectors, Discord or operations."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
import pytest_asyncio

from discordbot.operations.adapters.discord_admin import OperationsPanel
from discordbot.operations.adapters.service_status import SERVICES, PRIMARY_SERVICE_KEYS, unknown_observations
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.tasks import TaskSupervisor
from .test_admin_panel import Status, interaction
from .test_panel_position import fake_channel, positioned

NOW=datetime(2026,10,31,12,tzinfo=timezone.utc)
RELEASE='r-'+'a'*16+'-'+'b'*16


def observations():
    rows=[]
    for row in unknown_observations():
        values=dict(state='실행 중',health='미확인',observed_at=NOW)
        if row.key in {'bot','watch'}:
            values.update(health='통과',version=RELEASE,version_provenance='실행 health 응답')
        if row.key in {'backup', 'update', 'manual'}:
            values.update(state='예약 대기',recent_job='최근 작업 정상 종료 · 2026-10-31T08:00:34+00:00',
                enabled=True,last_trigger=NOW-timedelta(hours=1),next_run=NOW+timedelta(hours=4),version_provenance='예약 작업 · 별도 실행 버전 없음')
        rows.append(replace(row,**values))
    return tuple(rows)


@pytest_asyncio.fixture
async def unified(tmp_path):
    ticks=[0.]
    clock=SimpleNamespace(monotonic=lambda:ticks[0],now=lambda:NOW+timedelta(seconds=ticks[0]))
    h=fake_channel(clock);h.clock=clock;h.ticks=ticks
    h.executor=BoundedExecutor(workers=1,queue_capacity=8,name='unified-panel-test')
    h.supervisor=TaskSupervisor(capacity=8,history_capacity=32,clock=clock)
    h.inbox=SimpleNamespace(accept_current=AsyncMock(return_value='accepted'))
    h.status=Status();h.status.snapshot=AsyncMock(side_effect=AssertionError('legacy authority must not be queried'))
    h.services=SimpleNamespace(snapshot=AsyncMock(return_value=observations()))
    h.panel=OperationsPanel(h.bot,master=1,channel=42,state=tmp_path,inbox=h.inbox,status=h.status,
        clock=clock,supervisor=h.supervisor,executor=h.executor,services=h.services)
    await h.panel.start();await h.panel.ready()
    yield h
    await h.panel.stop();await h.supervisor.shutdown(grace_seconds=1);await h.executor.close(grace_seconds=2)


def fields(h):return {field.name:field.value for field in h.messages[444].embeds[0].fields}


@pytest.mark.asyncio
async def test_service_select_and_unsupported_actions_are_disabled_in_memory_and_payload(unified):
    h=unified;assert h.panel.message_id==444
    assert h.messages[444].embeds[0].title=='🛠️ 서비스 상태 제어판'
    select=h.panel.view.children[0]
    assert tuple(option.value for option in select.options)==PRIMARY_SERVICE_KEYS
    expected={'ops:v2:refresh':False,'ops:v2:restart':True,'ops:v2:update':True,'ops:v2:backup':True}
    assert {item.custom_id:item.disabled for item in h.panel.view.children[1:]}==expected
    actual={item.custom_id:item.disabled for group in h.messages[444].components for item in group.children if item.type==discord.ComponentType.button}
    assert actual==expected
    footer=h.messages[444].embeds[0].footer.text
    assert '표시 시점의 관측' in footer and 'Bot 중단 시 갱신 불가' in footer
    assert '선택은 공유 표시만 변경' in footer and '실행 비활성화' in footer
    h.status.snapshot.assert_not_called();h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key',PRIMARY_SERVICE_KEYS)
async def test_service_selection_only_updates_same_message_with_truthful_scope(unified,key):
    h=unified;click=interaction();click.data={'values':[key]}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service==key and h.panel.message_id==444
    assert h.channel.send.await_count==1
    spec=next(spec for spec in SERVICES if spec.key==key)
    assert spec.label in h.messages[444].embeds[0].description
    assert fields(h)['검사 범위']==spec.health_scope
    assert fields(h)['관측 시각(UTC)']=='2026-10-31 12:00:00 UTC'
    assert '최근 관측' in fields(h)['표시 시점의 관측 최신성']
    h.inbox.accept_current.assert_not_called();h.status.snapshot.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['update','restart','backup','confirm','cancel','ops:v1:update','ops:v2:restart'])
async def test_forged_legacy_or_unified_actions_never_enqueue(unified,action):
    h=unified;click=interaction()
    await h.panel.interact(click,action,'forged-nonce')
    h.inbox.accept_current.assert_not_called();h.status.snapshot.assert_not_called()
    assert not h.panel.confirmations
    assert '읽기 전용' in click.response.send_message.call_args.args[0]
    click.response.defer.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_service_selection_never_echoes_private_payload(unified):
    h=unified;click=interaction();click.data={'values':['PRIVATE token=PRIVATE']}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service=='bot' and h.messages[444].edit.await_count==0
    assert 'PRIVATE' not in str(click.followup.send.call_args)


@pytest.mark.asyncio
async def test_stale_or_future_observation_is_not_presented_as_current_health(unified):
    h=unified;h.ticks[0]=61
    await h.panel._refresh_panel()
    assert '현재 미확인' in h.messages[444].embeds[0].description
    assert '오래된 관측' in fields(h)['표시 시점의 관측 최신성']
    h.ticks[0]=-1
    await h.panel._refresh_panel()
    assert '미래 관측 시각' in fields(h)['표시 시점의 관측 최신성']
    assert '현재 미확인' in h.messages[444].embeds[0].description


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['exception','malformed'])
async def test_provider_failure_uses_unknown_not_previous_healthy_snapshot(unified,failure):
    h=unified
    if failure=='exception':h.services.snapshot.side_effect=RuntimeError('PRIVATE token')
    else:h.services.snapshot.return_value=(replace(observations()[0],health_scope='PRIVATE'),*observations()[1:])
    await h.panel._refresh_panel()
    embed=h.messages[444].embeds[0]
    assert '상태 수집 실패' in embed.description and '통과' not in embed.description
    assert 'PRIVATE' not in str(embed.to_dict())
    assert fields(h)['관측 시각(UTC)']=='미제공'
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_primary_version_provenance_and_missing_job_are_not_overclaimed(unified):
    h=unified
    assert '실행 health 응답' in fields(h)['실행 버전 · 출처']
    click=interaction();click.data={'values':['salary']}
    await h.panel.view.children[0].callback(click)
    assert fields(h)['실행 버전 · 출처']=='미제공\n실행 버전 미제공'
    assert fields(h)['최근 작업 기록']=='최근 작업 미확인 · 검증된 기록 미제공'
    assert 'systemd 프로세스 상태' in fields(h)['검사 범위']
    assert '다음 예약' not in fields(h)
    h.ticks[0]=61
    await h.panel._refresh_panel()
    assert fields(h)['이전 관측 버전 · 출처']=='미제공\n실행 버전 미제공'
    assert '현재 상태 미확인' in fields(h)['표시 시점의 관측 최신성']


@pytest.mark.asyncio
@pytest.mark.parametrize('error',[OSError('synthetic clock unavailable'),RuntimeError('synthetic clock unavailable')])
async def test_clock_read_failure_updates_card_as_unknown_instead_of_leaving_old_health(unified,error):
    h=unified;before=h.messages[444].edit.await_count
    def failed_clock():raise error
    h.clock.now=failed_clock
    await h.panel._refresh_panel()
    assert h.messages[444].edit.await_count==before+1
    assert '현재 미확인' in h.messages[444].embeds[0].description
    assert '관측 시각 미확인' in fields(h)['표시 시점의 관측 최신성']
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_unified_current_panel_proof_and_verified_link(unified):
    h=unified
    assert await h.panel.verified_link()=='https://discord.com/channels/71/42/444'
    h.panel._invalidate_link()
    next(item for group in h.messages[444].components for item in group.children if item.custom_id=='ops:v2:backup').disabled=False
    assert await h.panel.verified_link() is None  # Enabled unsupported button is not a verified read-only panel.


@pytest.mark.asyncio
async def test_legacy_own_panel_migrates_in_place_without_repost(positioned):
    h=positioned;await h.panel.stop();old=h.messages[444]
    services=SimpleNamespace(snapshot=AsyncMock(return_value=observations()))
    new=OperationsPanel(h.bot,master=1,channel=42,state=h.panel.store.state,inbox=h.inbox,status=h.status,
        clock=h.clock,supervisor=h.supervisor,executor=h.executor,services=services)
    await new.start()
    assert await new.verified_link() is None  # Lookup never edits a legacy operational card.
    old.edit.assert_not_called()
    await new.ready()
    try:
        assert new.message_id==444 and h.channel.send.await_count==1
        assert old.embeds[0].title=='🛠️ 서비스 상태 제어판'
        assert await new.verified_link()=='https://discord.com/channels/71/42/444'
        assert {item.custom_id for item in new.view.children}=={'ops:v2:service','ops:v2:refresh','ops:v2:restart','ops:v2:update','ops:v2:backup'}
        old.delete.assert_not_called()
    finally:await new.stop()


@pytest.mark.asyncio
async def test_legacy_disabled_flags_survive_handler_rebinding(positioned):
    h=positioned
    assert all(item.disabled for item in h.panel.view.children if item.custom_id!='ops:v1:refresh')
    assert all(item.disabled for group in h.messages[444].components for item in group.children if item.custom_id!='ops:v1:refresh')


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ('backup', 'update', 'manual'))
async def test_timer_selection_shows_schedule_and_worker_evidence(unified, key):
    h = unified
    h.panel.selected_service = key
    await h.panel._refresh_panel()
    evidence = fields(h)
    assert evidence['부팅 시 자동 시작'] == '활성'
    for label, when in [('마지막 예약 실행', NOW-timedelta(hours=1)), ('다음 예약', NOW+timedelta(hours=4))]:
        assert f'<t:{int(when.timestamp())}:F>' in evidence[label]
        assert f'<t:{int(when.timestamp())}:R>' in evidence[label]
    assert '정상 종료' in evidence['최근 작업 기록']
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_elapsed_deadline_cannot_be_presented_as_next_timer_run(unified):
    h = unified
    h.panel.selected_service = 'manual'
    h.services.snapshot.return_value = tuple(
        replace(row, next_run=NOW+timedelta(seconds=1)) if row.key == 'manual' else row
        for row in observations())
    h.ticks[0] = 2
    await h.panel._refresh_panel()
    assert '<t:' not in fields(h)['다음 예약']
