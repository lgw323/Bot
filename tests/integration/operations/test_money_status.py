"""Synthetic projection/UI boundary; no financial DB, keys, HTTP or Discord."""
from datetime import timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

from discordbot.operations.adapters.discord_admin import OperationsPanel
from discordbot.operations.adapters.money_status import MAXIMUM_BYTES, MoneyProjectionError, parse_projection
from discordbot.operations.adapters.service_status import LEGACY_PRIMARY_SERVICE_KEYS, SERVICES, UNITS
from .test_admin_panel import interaction
from .test_unified_panel import NOW, unified


def value(**changes):
    return dict(version=1,service='mymoney',observed_at=NOW.isoformat(),process='running',health='pass',
        schema='compatible',artifact_sha256='a'*64,backup='pass',
        backup_verified_at=(NOW-timedelta(hours=1)).isoformat()) | changes


def payload(**changes):
    return json.dumps(value(**changes),separators=(',',':')).encode()


async def select_money(h):
    i=interaction();i.data={'values':['mymoney']}
    await h.panel.view.children[0].callback(i)
    return h.messages[444].embeds[0]


def fields(embed):
    return {field.name:field.value for field in embed.fields}


def test_minimal_projection_is_bounded_and_only_public_metadata_survives():
    parsed=parse_projection(payload(),NOW)
    assert parsed.process=='running' and parsed.artifact_sha256=='a'*64
    assert parsed.backup_verified_at==NOW-timedelta(hours=1)
    assert len(payload())<MAXIMUM_BYTES
    assert not any('mymoney' in unit for unit in UNITS)  # Collector has no new service permission.
    assert len(SERVICES)==6


@pytest.mark.parametrize('field',['balance','amount','transactions','accounts','session','api_key','db_path','tables'])
def test_financial_auth_or_other_unknown_fields_reject_without_echo(field):
    with pytest.raises(MoneyProjectionError,match='^invalid_or_noncurrent_money_status_projection$') as error:
        parse_projection(payload(**{field:'PRIVATE synthetic'}),NOW)
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('raw',[b'',b'[]',b'\xff',b' '*2049,
    payload().replace(b'"version":1',b'"version":1,"version":1'),
    payload().replace(b'"version":1',b'"version":NaN'),
    payload().replace(b'"health":"pass"',b'"health":{}')])
def test_bad_type_duplicate_nan_invalid_utf8_and_size_are_rejected(raw):
    with pytest.raises(MoneyProjectionError):parse_projection(raw,NOW)


@pytest.mark.parametrize('change',[{'version':True},{'service':'other'},{'process':'PRIVATE'},
    {'artifact_sha256':'a'*40},{'artifact_sha256':'../PRIVATE'},
    {'observed_at':NOW.replace(tzinfo=None).isoformat()},
    {'observed_at':NOW.astimezone(timezone(timedelta(hours=9))).isoformat()},
    {'observed_at':(NOW+timedelta(seconds=1)).isoformat()},
    {'observed_at':(NOW-timedelta(seconds=181)).isoformat()}])
def test_schema_identity_timestamp_and_noncurrent_proofs_fail_closed(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


def test_exact_freshness_boundary_and_uninstalled_cross_validation():
    assert parse_projection(payload(observed_at=(NOW-timedelta(seconds=180)).isoformat(),
        backup='unknown',backup_verified_at=None),NOW)
    absent=dict(process='not_installed',health='unknown',schema='unknown',artifact_sha256=None,
                backup='unknown',backup_verified_at=None)
    assert parse_projection(payload(**absent),NOW).process=='not_installed'
    for change in ({'health':'pass'},{'schema':'compatible'},{'artifact_sha256':'a'*64},
                   {'backup':'pass','backup_verified_at':NOW.isoformat()}):
        with pytest.raises(MoneyProjectionError):parse_projection(payload(**(absent|change)),NOW)


@pytest.mark.parametrize('change',[
    {'process':'stopped','health':'unknown','schema':'compatible','artifact_sha256':None},
    {'process':'stopped','health':'unknown','schema':'unknown','artifact_sha256':'a'*64},
    {'process':'failed','health':'fail','schema':'unknown','artifact_sha256':None},
    {'process':'unknown','health':'unknown','schema':'unknown','artifact_sha256':None},
    {'health':'fail','schema':'compatible'}, {'health':'unknown','schema':'compatible'},
])
def test_contradictory_projection_is_rejected_like_the_producer_contract(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


@pytest.mark.parametrize('change',[{'backup_verified_at':None},{'backup':'unknown'},
    {'backup_verified_at':(NOW+timedelta(seconds=1)).isoformat()},
    {'backup_verified_at':'PRIVATE'}])
def test_backup_claim_needs_its_own_valid_prior_verification_time(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


def test_backup_older_than_six_hours_is_unknown_without_erasing_other_observations():
    value=parse_projection(payload(backup_verified_at=(NOW-timedelta(hours=6,seconds=1)).isoformat()),NOW)
    assert value.process=='running' and value.health=='pass'
    assert value.backup=='unknown' and value.backup_verified_at is None
    delayed=parse_projection(payload(observed_at=(NOW-timedelta(seconds=120)).isoformat(),
        backup_verified_at=(NOW-timedelta(hours=6,seconds=1)).isoformat()),NOW)
    assert delayed.backup=='unknown'


def test_parser_never_opens_files_reads_clock_or_calls_network():
    with patch('builtins.open',side_effect=AssertionError('no file read')), \
         patch('time.time',side_effect=AssertionError('no clock read')), \
         patch('socket.create_connection',side_effect=AssertionError('no network')):
        assert parse_projection(payload(),NOW)


@pytest.mark.asyncio
async def test_default_fourth_choice_is_unconfigured_and_never_claims_money_installed(unified):
    h=unified;marker=h.panel.store.read()
    assert [option.value for option in h.panel.view.children[0].options]==['bot','supper','forme','mymoney']
    embed=await select_money(h)
    assert '미구성' in embed.description and '설치 여부와 현재 상태 미확인' in embed.description
    assert embed.color.value==0x95A5A6
    assert fields(embed)['관측 시각(UTC)']=='미제공'
    assert h.panel.store.read()==marker and h.channel.send.await_count==1
    assert await h.panel.verified_link()=='https://discord.com/channels/71/42/444'
    assert all(item.disabled for item in h.panel.view.children[1:] if item.custom_id!='ops:v2:refresh')
    h.status.snapshot.assert_not_called();h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_future_projection_adapter_is_injected_only_not_read_in_default_production(unified):
    h=unified;provider=SimpleNamespace(snapshot=AsyncMock(return_value=payload()))
    h.panel.money_status=provider
    await h.panel._refresh_panel()
    provider.snapshot.assert_not_called()  # Bot selected; no Money metadata requested.
    embed=await select_money(h)
    provider.snapshot.assert_awaited_once()
    assert '실행 중 보고' in embed.description and '검사 투영: 통과 보고' in embed.description
    assert '직접 검증 아님' in fields(embed)['표시 시점의 관측 최신성']
    assert 'a'*64 in fields(embed)['패키지 식별 · 근거']
    assert '2026-10-31 11:00:00 UTC' in fields(embed)['백업 상태 투영 · 마지막 검증(UTC)']
    assert 'Git 커밋·실행 버전 직접 검증 아님' in fields(embed)['패키지 식별 · 근거']
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['permission','timeout','missing','expired','future','financial'])
async def test_denied_missing_or_stale_projection_omits_all_previous_positive_evidence(unified,failure):
    h=unified;provider=SimpleNamespace(snapshot=AsyncMock(return_value=payload()))
    h.panel.money_status=provider
    await select_money(h)
    if failure=='permission':provider.snapshot.side_effect=PermissionError('PRIVATE filesystem path')
    elif failure=='timeout':provider.snapshot.side_effect=TimeoutError('PRIVATE transport detail')
    elif failure=='missing':provider.snapshot.return_value=None
    elif failure=='expired':provider.snapshot.return_value=payload(observed_at=(NOW-timedelta(seconds=181)).isoformat())
    elif failure=='future':provider.snapshot.return_value=payload(observed_at=(NOW+timedelta(seconds=1)).isoformat())
    else:provider.snapshot.return_value=payload(balance='PRIVATE financial value')
    await h.panel._refresh_panel()
    embed=h.messages[444].embeds[0]
    assert ('상태 자료 미구성·미확인' if failure=='missing' else '상태 자료 미확인') in embed.description and embed.color.value==0x95A5A6
    assert 'PRIVATE' not in str(embed.to_dict()) and 'a'*64 not in str(embed.to_dict())
    assert fields(embed)['스키마 상태 투영']=='미확인'
    assert fields(embed)['관측 시각(UTC)']=='미제공'


@pytest.mark.asyncio
async def test_backup_failure_report_is_visible_without_claiming_money_runtime_failed(unified):
    h=unified;h.panel.money_status=SimpleNamespace(snapshot=AsyncMock(return_value=payload(backup='fail')))
    embed=await select_money(h)
    assert '실행 중 보고' in embed.description and '검사 투영: 통과 보고' in embed.description
    assert '검증 실패 보고' in fields(embed)['백업 상태 투영 · 마지막 검증(UTC)']
    assert embed.color.value==0xFF0000


@pytest.mark.asyncio
async def test_projection_becomes_unknown_if_it_expires_after_sampling_before_render(unified):
    h=unified;h.panel.money_status=SimpleNamespace(snapshot=AsyncMock(return_value=payload()))
    await select_money(h)
    snapshot=await h.panel._snapshot()
    h.ticks[0]=181
    embed=h.panel._service_embed(snapshot)
    assert embed.color.value==0x95A5A6 and '상태 자료 미확인' in embed.description
    assert 'a'*64 not in str(embed.to_dict())


@pytest.mark.asyncio
async def test_backup_expiry_during_render_does_not_erase_independent_process_projection(unified):
    h=unified;h.panel.money_status=SimpleNamespace(snapshot=AsyncMock(return_value=payload(
        backup_verified_at=(NOW-timedelta(hours=6)+timedelta(seconds=1)).isoformat())))
    await select_money(h)
    snapshot=await h.panel._snapshot();h.ticks[0]=2
    embed=h.panel._service_embed(snapshot)
    assert '실행 중 보고' in embed.description
    assert '검증 통과 보고' not in fields(embed)['백업 상태 투영 · 마지막 검증(UTC)']
    assert '미확인' in fields(embed)['백업 상태 투영 · 마지막 검증(UTC)']


@pytest.mark.asyncio
@pytest.mark.parametrize('old_keys',[LEGACY_PRIMARY_SERVICE_KEYS,tuple(spec.key for spec in SERVICES)])
async def test_three_and_six_option_own_panels_upgrade_same_id_without_reposting(unified,old_keys):
    h=unified;marker=h.panel.store.read();old=h.messages[444]
    h.panel.view.children[0].options=[discord.SelectOption(label=key,value=key) for key in old_keys]
    await h.panel.stop()
    h.panel=OperationsPanel(h.bot,master=1,channel=42,state=h.panel.store.state,inbox=h.inbox,status=h.status,
        clock=h.clock,supervisor=h.supervisor,executor=h.executor,services=h.services)
    await h.panel.start();await h.panel.ready()
    assert len(h.panel.view.children[0].options)==4
    assert h.panel.store.read()==marker and h.panel.message_id==444 and h.channel.send.await_count==1
    old.delete.assert_not_called()


@pytest.mark.asyncio
async def test_money_actions_stay_disabled_even_with_forged_operational_callbacks(unified):
    h=unified;await select_money(h)
    for action in ('restart','update','backup','confirm','ops:v1:update'):
        await h.panel.interact(interaction(),action,'forged')
    assert not h.panel.confirmations
    h.inbox.accept_current.assert_not_called();h.status.snapshot.assert_not_called()
    forbidden=interaction(user=2);forbidden.data={'values':['mymoney']}
    before=h.messages[444].edit.await_count
    await h.panel.view.children[0].callback(forbidden)
    assert h.messages[444].edit.await_count==before


@pytest.mark.asyncio
async def test_money_embed_limits_and_no_unverified_navigation(unified):
    h=unified;h.panel.money_status=SimpleNamespace(snapshot=AsyncMock(return_value=payload()))
    embed=await select_money(h)
    utf16=lambda s:len(s.encode('utf-16-le'))//2
    assert len(embed)<=6000 and len(embed.fields)<=25
    assert all(utf16(f.name)<=256 and utf16(f.value)<=1024 for f in embed.fields)
    assert utf16(embed.footer.text)<=2048 and 'Bot 중단 시 갱신 불가' in embed.footer.text
    h.panel._invalidate_link();h.messages[444].author=SimpleNamespace(id=901)
    assert await h.panel.verified_link() is None
