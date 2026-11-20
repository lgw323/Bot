"""In-memory panel positioning, refresh and recovery without a Discord connection."""
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
    assert h.panel.store.read()['previous'] is None
    assert not old.components
    old.delete.assert_not_called()


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
    for message_id in range(500, 600):h.panel.notice_delivered(message_id)
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
    h.panel._refresh_panel.assert_awaited_once_with(after_notice=0)
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


async def alert(h):
    return await h.channel.send(embed=discord.Embed(title="fixture notice"), view=discord.ui.View())


@pytest.mark.asyncio
async def test_coalesced_alerts_move_one_panel_and_preserve_all_notices(positioned):
    h = positioned
    first, second = await alert(h), await alert(h)
    await h.panel._refresh_panel(after_notice=second.id)
    current = h.panel.message_id
    assert current > second.id and h.panel.moves == 1
    assert h.messages[444].components == []
    assert f"/{current})" in h.messages[444].embeds[0].description
    assert await h.panel.verified_link() == f"https://discord.com/channels/71/42/{current}"
    for notice in (first, second):
        notice.edit.assert_not_called()
        notice.delete.assert_not_called()
    await h.panel._refresh_panel(after_notice=first.id)
    assert h.panel.message_id == current and h.channel.send.await_count == 4
    assert h.panel.store.read()['previous'] is None


@pytest.mark.asyncio
async def test_definite_rejection_preserves_old_and_permits_one_later_move(positioned):
    h = positioned
    notice = await alert(h)
    original = h.panel.store.read()
    send = h.channel.send.side_effect
    h.channel.send.side_effect = discord.RateLimited(3)
    with pytest.raises(discord.RateLimited):
        await h.panel._refresh_panel(after_notice=notice.id)
    assert h.panel.store.read() == original and h.panel.message_id == 444
    h.messages[444].edit.assert_not_called()
    h.channel.send.side_effect = send
    await h.panel._refresh_panel(after_notice=notice.id)
    assert h.panel.message_id > notice.id and len(h.messages) == 3


@pytest.mark.asyncio
async def test_ambiguous_send_reconciles_same_panel_before_retiring(positioned):
    h = positioned
    notice = await alert(h)
    send = h.channel.send.side_effect
    async def uncertain(**kwargs):
        await send(**kwargs)
        raise TimeoutError
    h.channel.send.side_effect = uncertain
    with pytest.raises(TimeoutError):
        await h.panel._refresh_panel(after_notice=notice.id)
    assert h.panel.store.read()['state'] == 'publishing'
    h.messages[444].edit.assert_not_called()
    h.channel.send.side_effect = send
    await h.panel.ready()
    assert h.panel.message_id == max(h.messages) and h.channel.send.await_count == 3
    assert not h.messages[444].components and h.panel.store.read()['previous'] is None


@pytest.mark.asyncio
async def test_quiet_channel_periodic_refresh_stops_with_panel(positioned):
    h = positioned
    handle = h.panel.refresh_timer
    handle.cancel()
    h.panel._periodic_due()
    await asyncio.gather(*h.panel.tasks)
    assert h.messages[444].edit.await_count == 1 and h.channel.send.await_count == 1
    next_handle = h.panel.refresh_timer
    assert next_handle is not None and next_handle is not handle
    await h.panel.stop()
    assert next_handle.cancelled() and h.panel.refresh_timer is None


@pytest.mark.asyncio
async def test_new_alert_during_publication_remains_pending(positioned, monkeypatch):
    h = positioned
    monkeypatch.setattr(h.panel, '_schedule_follow', lambda: None)
    first = await alert(h)
    h.panel.notice_delivered(first.id)
    h.ticks[0] = 10
    send = h.channel.send.side_effect

    async def arriving(**kwargs):
        panel = await send(**kwargs)
        newer = await send(embed=discord.Embed(title="later alert"), view=discord.ui.View())
        h.panel.notice_delivered(newer.id)
        return panel

    h.channel.send.side_effect = arriving
    await h.panel._follow_notices()
    assert h.panel.notice_revision == 2 and h.panel.bumped_revision == 1
    newest_alert = h.panel.latest_notice_id
    assert h.panel.message_id < newest_alert
    h.channel.send.side_effect = send
    h.ticks[0] = 70
    await h.panel._follow_notices()
    assert h.panel.bumped_revision == 2 and h.panel.message_id > newest_alert
    assert h.panel.moves == 2
    assert sum(bool(message.components and message.components[0].children) for message in h.messages.values()) == 1


@pytest.mark.asyncio
async def test_failed_follow_has_one_spaced_retry_and_preserves_notices(positioned, monkeypatch):
    h = positioned
    monkeypatch.setattr(h.panel, '_schedule_follow', lambda: None)
    h.panel._refresh_panel = AsyncMock(side_effect=discord.RateLimited(5))
    h.panel.notice_delivered(500)
    h.ticks[0] = 10
    await h.panel._follow_notices()
    assert h.panel.bumped_revision == 0 and h.panel.notice_first == 10
    h.ticks[0] = 70
    await h.panel._follow_notices()
    assert h.panel.bumped_revision == 1 and h.panel.notice_first is None
    assert h.panel._refresh_panel.await_count == 2
    assert h.channel.send.await_count == 1


@pytest.mark.asyncio
async def test_retirement_receipt_retry_accepts_only_exact_existing_redirect(positioned, monkeypatch):
    h = positioned
    notice = await alert(h)
    receipt = h.panel.store.retired
    def unavailable(previous):
        raise OSError("fixture store unavailable")
    monkeypatch.setattr(h.panel.store, 'retired', unavailable)
    with pytest.raises(OSError):
        await h.panel._refresh_panel(after_notice=notice.id)
    assert h.panel.store.read()['previous'] == 444 and not h.messages[444].components
    monkeypatch.setattr(h.panel.store, 'retired', receipt)
    await h.panel.ready()
    assert h.panel.store.read()['previous'] is None and h.channel.send.await_count == 3
    h.messages[444].edit.assert_awaited_once()
