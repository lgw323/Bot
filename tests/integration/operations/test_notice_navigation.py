"""Optional verified navigation; alerts still deliver without a panel."""
import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.operations.adapters.discord_logging import Notice
from discordbot.operations.adapters.notice_cards import CardMetadata, notice_embed
from discordbot.operations.adapters.panel_links import panel_link
from .test_discord_logging import fixture


URL = 'https://discord.com/channels/100/42/444'


@pytest.mark.parametrize('value', [None, {}, True, 'https://discord.com.evil/channels/100/42/444',
    'http://discord.com/channels/100/42/444', 'https://discord.com/channels/0/42/444',
    'https://discord.com/channels/@me/42/444', URL+'?token=PRIVATE', URL+'#PRIVATE',
    'https://discord.com/channels/100/43/444', 'https://discord.com/channels/100/42/0',
    'https://discord.com/channels/100/42/9223372036854775808', URL+'\nPRIVATE'])
def test_untrusted_or_wrong_channel_shape_never_becomes_navigation(value):
    assert panel_link(value, channel=42) is None


def test_only_canonical_positive_identity_shape_is_allowed():
    assert panel_link(URL, channel=42) == URL
    class Injected(str):
        def __str__(self): return 'PRIVATE'
    assert panel_link(Injected(URL), channel=42) is None
    assert panel_link(URL, channel=True) is None


@pytest.mark.asyncio
async def test_confirmed_destination_is_one_embed_link_without_extra_view_or_message():
    owner, _, channel = fixture()
    owner.panel_link_provider = AsyncMock(return_value=URL)
    owner.enqueue(Notice('safe', 'safe evidence', 0))
    await owner.deliver_one()
    sent=channel.send.call_args.kwargs
    assert channel.send.await_count == 1 and 'content' not in sent and 'view' not in sent
    navigation=sent['embed'].fields[-1]
    assert navigation.name == '운영 제어판' and navigation.value == f'[제어판으로 이동]({URL})'
    assert sent['allowed_mentions'].to_dict()['parse'] == []
    await owner.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [None, 'https://PRIVATE.invalid/?token=PRIVATE',
                                  'https://discord.com/channels/100/43/444'])
async def test_unavailable_or_bad_destination_keeps_alert_and_exports_no_raw_url(result):
    owner, _, channel = fixture()
    owner.panel_link_provider = AsyncMock(return_value=result)
    owner.enqueue(Notice('safe', 'safe evidence', 0))
    await owner.deliver_one()
    body=channel.send.call_args.kwargs['embed'].to_dict()
    assert body['description']=='safe evidence' and 'fields' not in body
    assert 'PRIVATE' not in json.dumps(body) and '제어판으로 이동' not in json.dumps(body,ensure_ascii=False)
    assert owner.failures==0 and owner.delivered==1
    await owner.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',[PermissionError('PRIVATE token'),TimeoutError('PRIVATE')])
async def test_link_lookup_failure_does_not_become_alert_transport_failure(failure):
    owner, _, channel=fixture()
    owner.panel_link_provider=AsyncMock(side_effect=failure)
    owner.enqueue(Notice('safe','safe evidence',0))
    await owner.deliver_one()
    assert channel.send.await_count==1 and owner.panel_link_failures==1
    assert owner.failures==owner.uncertain==0
    assert 'PRIVATE' not in json.dumps(channel.send.call_args.kwargs['embed'].to_dict())
    await owner.stop()


@pytest.mark.asyncio
async def test_lookup_is_bounded_and_alert_is_sent_without_link():
    owner, _, channel=fixture()
    async def wait(): await asyncio.Event().wait()
    owner.panel_link_provider=wait
    owner.enqueue(Notice('safe','safe evidence',0))
    await asyncio.wait_for(owner.deliver_one(),4)
    assert channel.send.await_count==1 and owner.panel_link_failures==1
    assert 'fields' not in channel.send.call_args.kwargs['embed'].to_dict()
    await owner.stop()


@pytest.mark.asyncio
async def test_cancel_during_lookup_never_sends_or_marks_uncertain():
    owner, _, channel=fixture();entered=asyncio.Event()
    async def wait(): entered.set();await asyncio.Event().wait()
    owner.panel_link_provider=wait
    owner.enqueue(Notice('safe','safe evidence',0))
    task=asyncio.create_task(owner.deliver_one());await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert channel.send.await_count==0 and owner.uncertain==0 and owner.dropped==1
    await owner.stop()


@pytest.mark.asyncio
async def test_explicit_rate_limit_rechecks_destination_but_preserves_notice_identity():
    owner, clock, channel=fixture()
    owner.panel_link_provider=AsyncMock(side_effect=[URL,None])
    owner.enqueue(Notice('safe','safe evidence',0))
    channel.send.side_effect=discord.RateLimited(10)
    await owner.deliver_one()
    first=channel.send.call_args.kwargs
    clock[0]=10;channel.send.side_effect=None
    await owner.deliver_one()
    second=channel.send.call_args.kwargs
    assert owner.panel_link_provider.await_count==2 and first['nonce']==second['nonce']
    assert first['embed'].description==second['embed'].description
    assert first['embed'].footer.text==second['embed'].footer.text
    assert first['embed'].fields and not second['embed'].fields
    await owner.stop()


def test_optional_link_never_displaces_evidence_at_field_or_total_limit():
    now=datetime(2026,10,31,tzinfo=timezone.utc)
    fields=tuple(('n','v') for _ in range(25))
    body=notice_embed('safe','evidence',0,CardMetadata(fields,'release',now),panel_link=URL).to_dict()
    assert len(body['fields'])==25 and all(f['name']=='n' for f in body['fields'])
    base=notice_embed('t','d'*2000,0,CardMetadata(release='release',occurred_at=now)).to_dict()
    footer_size=len(base['footer']['text'].encode('utf-16-le'))//2
    rest=6000-1-2000-footer_size-3*1025-1
    fields=(('n','v'*1024),)*3+(('n','v'*rest),)
    metadata=CardMetadata(fields,'release',now)
    expected=notice_embed('t','d'*2000,0,metadata).to_dict()
    actual=notice_embed('t','d'*2000,0,metadata,panel_link=URL).to_dict()
    assert actual==expected
