"""Fixed-panel refresh lifecycle on in-memory Discord messages; no network/deletes."""
import asyncio
from datetime import datetime, timedelta, timezone
from itertools import count
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
import pytest_asyncio

from discordbot.operations.adapters.discord_admin import OperationsPanel
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.tasks import TaskSupervisor
from .test_admin_panel import Status


def fake_channel(clock):
    messages={};identities=count(444);listeners={};views=[]
    guild=SimpleNamespace(id=71,me=SimpleNamespace(id=900))
    channel=SimpleNamespace(id=42,guild=guild)
    permissions=SimpleNamespace(view_channel=True,read_message_history=True,send_messages=True,embed_links=True)
    channel.permissions_for=lambda member: permissions
    async def send(**kwargs):
        identity=next(identities)
        message=SimpleNamespace(id=identity,author=SimpleNamespace(id=900,bot=True),channel=channel,guild=guild,
            embeds=[kwargs['embed']],components=[SimpleNamespace(children=list(kwargs['view'].children))],
            created_at=clock.now(),delete=AsyncMock())
        async def edit(**kw):
            if 'embed' in kw:message.embeds=[kw['embed']]
            if 'view' in kw:message.components=[] if kw['view'] is None else [SimpleNamespace(children=list(kw['view'].children))]
            return message
        message.edit=AsyncMock(side_effect=edit)
        messages[identity]=message
        return message
    channel.send=AsyncMock(side_effect=send)
    async def fetch(identity):
        if identity not in messages:
            raise discord.NotFound(SimpleNamespace(status=404,reason='missing'),{'message':'Unknown Message','code':10008})
        return messages[identity]
    channel.fetch_message=AsyncMock(side_effect=fetch)
    channel.get_partial_message=lambda identity:messages[identity]
    async def history(**kwargs):
        assert kwargs['limit'] in (100,101)
        rows=list(messages.values())
        if 'after' in kwargs:rows=[m for m in rows if m.created_at>=kwargs['after']]
        for message in rows[:kwargs['limit']]:yield message
    channel.history=history
    bot=SimpleNamespace(user=SimpleNamespace(id=900,bot=True),get_channel=lambda _:channel,
        fetch_channel=AsyncMock(return_value=channel),add_view=lambda view,**kw:views.append((view,kw)),
        add_listener=lambda fn,event:listeners.setdefault(event,fn),remove_listener=lambda fn,event:listeners.pop(event,None))
    return SimpleNamespace(bot=bot,channel=channel,messages=messages,permissions=permissions,views=views,listeners=listeners)


@pytest_asyncio.fixture
async def positioned(tmp_path,monkeypatch):
    ticks=[0.];epoch=datetime.now(timezone.utc)
    clock=SimpleNamespace(monotonic=lambda:ticks[0],now=lambda:epoch+timedelta(seconds=ticks[0]))
    # Persisted generations and fake Discord creation times share one clock.
    # Keep the real formatter so aware-UTC/explicit published_at validation stays.
    from discordbot.operations.adapters import panel_store
    real_now=panel_store._now
    monkeypatch.setattr(panel_store,'_now',lambda value=None:real_now(clock.now() if value is None else value))
    h=fake_channel(clock)
    h.clock=clock;h.ticks=ticks
    h.supervisor=TaskSupervisor(capacity=8,history_capacity=32,clock=clock)
    h.executor=BoundedExecutor(workers=1,queue_capacity=8,name='fixed-panel-test')
    h.inbox=SimpleNamespace(accept_current=AsyncMock(return_value='accepted'))
    h.status=Status();h.status.value['consumer_enabled']=False
    h.panel=OperationsPanel(h.bot,master=1,channel=42,state=tmp_path,inbox=h.inbox,
        status=h.status,clock=clock,supervisor=h.supervisor,executor=h.executor)
    await h.panel.start();await h.panel.ready()
    yield h
    await h.panel.stop();await h.supervisor.shutdown(grace_seconds=1);await h.executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_uncertain_generation_reconciles_after_real_second_with_frozen_fake_clock(positioned):
    h=positioned;frozen=h.clock.now();old=h.messages[444]
    loop=asyncio.get_running_loop();started=loop.time()
    await asyncio.sleep(1.1)
    assert loop.time()-started>=1
    assert h.clock.now()==frozen
    pending=h.panel.store.rotate(h.panel.store.read())
    existing=await h.channel.send(embed=h.panel._generation_embed(await h.status.snapshot(),pending),view=h.panel._view(),nonce=pending['nonce'])
    assert datetime.fromisoformat(pending['created_at'])<=existing.created_at
    await h.panel.ready()
    assert h.panel.message_id==existing.id and h.channel.send.await_count==2
    assert h.panel.store.read()['previous']==444
    old.edit.assert_not_called();old.delete.assert_not_called()


@pytest.mark.asyncio
async def test_fixture_clock_preserves_explicit_timestamp_validation(positioned):
    from discordbot.operations.adapters.panel_store import _now
    from discordbot.platform.errors import ValidationError
    explicit=datetime(2020,1,2,12,0,tzinfo=timezone(timedelta(hours=9)))
    assert _now(explicit)=='2020-01-02T03:00:00+00:00'
    with pytest.raises(ValidationError):_now(datetime(2020,1,2,12,0))


@pytest.mark.asyncio
async def test_notice_refresh_edits_same_id_and_keeps_every_other_message(positioned):
    h=positioned;old=h.messages[444];marker=h.panel.store.read()
    await h.panel._refresh_panel();await h.panel._refresh_panel()
    assert h.panel.message_id==444 and h.panel.store.read()==marker
    assert h.channel.send.await_count==1 and old.edit.await_count==2
    assert old.embeds[0].title=='🛠️ 시스템 운영 제어판'
    old.delete.assert_not_called();h.inbox.accept_current.assert_not_called()
    assert all(button.disabled for button in h.panel.view.children if button.custom_id!='ops:v1:refresh')


@pytest.mark.asyncio
async def test_restart_verifies_same_saved_id_before_binding(positioned):
    h=positioned;await h.panel.stop()
    new=OperationsPanel(h.bot,master=1,channel=42,state=h.panel.store.state,inbox=h.inbox,
        status=h.status,clock=h.clock,supervisor=h.supervisor,executor=h.executor)
    await new.start()
    assert new.message_id is None
    await new.ready()
    try:assert new.message_id==444 and h.channel.send.await_count==1
    finally:await new.stop()


@pytest.mark.asyncio
async def test_burst_has_one_refresh_task_and_shutdown_cleans_it(positioned):
    h=positioned
    for _ in range(100):h.panel.notice_delivered()
    assert len(h.panel.tasks)==1
    task=h.panel.bump_task
    await h.panel.stop()
    assert task.done() and h.channel.send.await_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('first,last,now,next_bump,expected',[(0,8,8,0,18),(0,59,59,0,60),(0,0,10,60,60)])
async def test_debounce_max_wait_and_spacing_refresh_same_id(positioned,monkeypatch,first,last,now,next_bump,expected):
    h=positioned;h.ticks[0]=now
    h.panel.notice_first=first;h.panel.notice_last=last;h.panel.next_bump=next_bump;h.panel.notice_revision=1
    async def sleep(seconds):h.ticks[0]+=seconds
    monkeypatch.setattr('discordbot.operations.adapters.discord_admin.asyncio.sleep',sleep)
    h.panel._refresh_panel=AsyncMock()
    await h.panel._follow_notices()
    assert h.ticks[0]==expected and h.panel.bumped_revision==1
    h.panel._refresh_panel.assert_awaited_once()
    assert h.channel.send.await_count==1


@pytest.mark.asyncio
async def test_real_sdk_dispatch_store_stays_bounded_for_repeated_refresh(positioned):
    h=positioned;client=discord.Client(intents=discord.Intents.none())
    h.bot.add_view=client.add_view;client.add_view(h.panel.view,message_id=444)
    try:
        for _ in range(5):await h.panel._refresh_panel()
        assert set(client._connection._view_store._views)=={444}
        await h.panel.stop()
        assert not client._connection._view_store._views
    finally:await client.close()
