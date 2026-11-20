"""Observed connection timing, using fake clocks and fake Discord only."""
import json
from unittest.mock import Mock

import discord
import pytest

from discordbot.operations.adapters.discord_logging import connection_interval
from .test_discord_logging import fixture


@pytest.mark.parametrize('start,end,expected', [
    (0., 0., '1초 미만'), (10., 10.0001, '1초 미만'), (0., .9999, '1초 미만'),
    (0., 1., '약 1초'), (10., 21., '약 11초'), (0., 11.26, '약 11.3초'),
    (0., 1.99, '약 2초'), (-20., -9., '약 11초'),
    (0., 7*86400, '약 604800초'), (0., 7*86400+.1, '7일 초과 (표시 상한)'),
    (0., 1e308, '7일 초과 (표시 상한)'),
])
def test_finite_observed_intervals_are_honest_and_bounded(start,end,expected):
    assert connection_interval(start,end)==expected


@pytest.mark.parametrize('start,end', [
    (None,1.), (0.,None), (1.,0.), (0.,-0.0001),
    (float('nan'),1.), (0.,float('nan')), (float('inf'),1.),
    (0.,float('inf')), (float('-inf'),0.), (-1e308,1e308),
    (True,1.), (0.,False), ('PRIVATE',1.), (0.,'PRIVATE'),
    (10**1000,10**1000+1), (0.,10**1000),
])
def test_missing_nonfinite_reversed_and_unusable_readings_are_unknown(start,end):
    assert connection_interval(start,end)=='미확인'


@pytest.mark.asyncio
async def test_short_interval_recovery_card_has_no_zero_or_duplicate_time_and_cause():
    owner,clock,channel=fixture()
    owner.announced=True
    clock[0]=10.;await owner.disconnected()
    clock[0]=10.2;await owner.resumed();await owner.ready()
    assert len(owner.queue)==1 and owner.reconnects==1
    item=owner.queue[0]
    assert '전체 서비스 준비 상태는 별도 확인' in item.description
    assert '초' not in item.description and '원인' not in item.description
    fields=dict(item.card.fields)
    assert fields['관측된 연결 이벤트 간격']=='1초 미만'
    assert fields['중단 원인']=='확인되지 않음'
    assert '실제 통신 장애 전체 시간이 아닙니다' in fields['측정 범위']
    await owner.deliver_one()
    sent=channel.send.call_args.kwargs
    assert 'content' not in sent
    text=json.dumps(sent['embed'].to_dict(),ensure_ascii=False)
    assert '0초' not in text and 'SLA' not in text
    assert sent['allowed_mentions'].to_dict()['parse']==[]
    await owner.stop()


@pytest.mark.asyncio
async def test_repeated_disconnect_uses_first_event_and_recovery_emits_once():
    owner,clock,_=fixture();owner.announced=True
    clock[0]=10.;await owner.disconnected()
    clock[0]=11.;await owner.disconnected()
    clock[0]=12.;await owner.resumed();await owner.ready()
    assert len(owner.queue)==1 and owner.reconnects==1
    assert dict(owner.queue[0].card.fields)['관측된 연결 이벤트 간격']=='약 2초'
    assert owner.disconnected_at is None and owner.disconnect_observed is False
    await owner.stop()


@pytest.mark.asyncio
async def test_missing_start_reading_still_reports_one_unknown_recovery():
    owner,clock,_=fixture();owner.announced=True
    owner.clock.monotonic=Mock(side_effect=[RuntimeError('PRIVATE clock'), 99., 99.])
    await owner.disconnected()
    assert owner.disconnected_at is None and owner.disconnect_observed is True
    await owner.disconnected()  # Does not replace an unknown first observation.
    await owner.resumed()
    assert len(owner.queue)==1 and owner.reconnects==1
    item=owner.queue[0]
    assert dict(item.card.fields)['관측된 연결 이벤트 간격']=='미확인'
    assert 'PRIVATE' not in item.description+str(item.card.fields)
    await owner.stop()


@pytest.mark.asyncio
async def test_failed_end_reading_and_backward_clock_do_not_become_zero():
    for end in [RuntimeError('PRIVATE'), 9., float('nan'), float('inf')]:
        owner,_,_=fixture();owner.announced=True
        owner.clock.monotonic=Mock(side_effect=[10.,end,20.])
        await owner.disconnected();await owner.ready()
        assert dict(owner.queue[0].card.fields)['관측된 연결 이벤트 간격']=='미확인'
        assert owner.reconnects==1
        await owner.stop()


@pytest.mark.asyncio
async def test_integer_clock_origin_does_not_lose_interval_by_float_coercion():
    owner,_,_=fixture();owner.announced=True
    origin=2**70
    owner.clock.monotonic=Mock(side_effect=[origin,origin+1,origin+2])
    await owner.disconnected();await owner.ready()
    assert dict(owner.queue[0].card.fields)['관측된 연결 이벤트 간격']=='약 1초'
    await owner.stop()


@pytest.mark.asyncio
async def test_recovery_metadata_and_nonce_are_stable_across_rate_limit_retry():
    owner,clock,channel=fixture();owner.announced=True
    clock[0]=20.;await owner.disconnected()
    clock[0]=20.4;await owner.ready()
    channel.send.side_effect=discord.RateLimited(10)
    await owner.deliver_one()
    first=channel.send.call_args.kwargs
    clock[0]=40.;channel.send.side_effect=None
    await owner.deliver_one()
    second=channel.send.call_args.kwargs
    assert first['nonce']==second['nonce']
    assert first['embed'].to_dict()==second['embed'].to_dict()
    assert owner.retries==1 and owner.reconnects==1 and owner.delivered==1
    await owner.stop()


@pytest.mark.asyncio
async def test_disconnect_before_initial_connection_is_not_an_observed_recovery():
    owner,clock,_=fixture()
    await owner.disconnected();clock[0]=1.;await owner.ready()
    assert owner.reconnects==0 and len(owner.queue)==1
    assert '연결 확인' in owner.queue[0].title
    await owner.stop()
