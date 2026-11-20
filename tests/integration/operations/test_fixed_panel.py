"""Verified links/current-ID selection; all Discord operations are in-memory fakes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.operations.adapters.discord_admin import OperationsPanel
from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.platform.errors import ValidationError
from .test_admin_panel import interaction
from .test_panel_position import positioned


def clone(h):
    return OperationsPanel(h.bot,master=1,channel=42,state=h.panel.store.state,inbox=h.inbox,
        status=h.status,clock=h.clock,supervisor=h.supervisor,executor=h.executor)


@pytest.mark.asyncio
async def test_verified_link_uses_real_fetch_and_canonical_ids_only(positioned):
    h=positioned;message=h.messages[444]
    message.jump_url='https://PRIVATE.invalid/forged'
    assert await h.panel.verified_link()=='https://discord.com/channels/71/42/444'
    assert h.channel.fetch_message.await_count==1
    assert h.channel.send.await_count==1
    message.edit.assert_not_called();message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_link_cache30s_has_one_fetch_for_concurrent_callers(positioned):
    h=positioned
    links=await asyncio.gather(*(h.panel.verified_link() for _ in range(20)))
    assert set(links)=={'https://discord.com/channels/71/42/444'}
    assert h.channel.fetch_message.await_count==1
    h.ticks[0]=31
    assert await h.panel.verified_link()
    assert h.channel.fetch_message.await_count==2


@pytest.mark.asyncio
async def test_cached_link_does_not_survive_current_marker_change(positioned):
    h=positioned;assert await h.panel.verified_link()
    row=h.panel.store.read();atomic_json(h.panel.store.path,{**row,'nonce':'a'*24})
    assert await h.panel.verified_link() is None
    assert h.panel.message_id is None
    assert h.channel.send.await_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['author','message_id','channel','guild','message_guild','title','components','generation','permission'])
async def test_unverified_identity_never_becomes_a_link_or_edit(positioned,kind):
    h=positioned;message=h.messages[444]
    if kind=='author':message.author.id=901
    elif kind=='message_id':message.id=445
    elif kind=='channel':message.channel=SimpleNamespace(id=99,guild=h.channel.guild)
    elif kind=='guild':message.channel=SimpleNamespace(id=42,guild=SimpleNamespace(id=72));message.guild=message.channel.guild
    elif kind=='message_guild':message.guild=SimpleNamespace(id=72)
    elif kind=='title':message.embeds=[discord.Embed(title='ordinary log')]
    elif kind=='components':message.components=[]
    elif kind=='generation':message.embeds[0].set_footer(text='wrong generation')
    else:h.permissions.read_message_history=False
    assert await h.panel.verified_link() is None
    assert h.channel.send.await_count==1
    message.edit.assert_not_called();message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_link_getter_never_creates_or_adopts_missing_state(positioned):
    h=positioned;h.panel.store.path.unlink()
    assert await h.panel.verified_link() is None
    assert not h.panel.store.path.exists() and h.channel.send.await_count==1


@pytest.mark.asyncio
async def test_missing_state_adopts_one_existing_verified_panel_without_send(positioned):
    h=positioned;await h.panel.stop();h.panel.store.path.unlink()
    new=clone(h);await new.start()
    try:
        assert new.message_id is None
        await new.ready()
        assert new.message_id==444 and h.channel.send.await_count==1
        assert new.store.read()['message']==444
        assert await new.verified_link()=='https://discord.com/channels/71/42/444'
    finally:await new.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['multiple','legacy','truncated','permission'])
async def test_missing_state_unknown_or_ambiguous_history_never_reposts(positioned,kind):
    h=positioned;await h.panel.stop();h.panel.store.path.unlink()
    message=h.messages[444]
    if kind=='multiple':
        await h.channel.send(embed=message.embeds[0],view=h.panel._view(),nonce='b'*24)
    elif kind=='legacy':message.embeds[0].set_footer(text='legacy without generation')
    elif kind=='permission':h.permissions.read_message_history=False
    else:
        async def history(**kwargs):
            for _ in range(101):yield SimpleNamespace(author=SimpleNamespace(id=99))
        h.channel.history=history
    count=h.channel.send.await_count
    new=clone(h);await new.start();await new.ready()
    try:
        assert new.message_id is None and not new.store.path.exists()
        assert h.channel.send.await_count==count
        message.delete.assert_not_called()
    finally:await new.stop()


@pytest.mark.asyncio
async def test_uncertain_v2_reconciles_existing_exact_generation_without_old_edits(positioned):
    h=positioned;old=h.messages[444]
    pending=h.panel.store.rotate(h.panel.store.read())  # Legacy prior-version state fixture only.
    existing=await h.channel.send(embed=h.panel._generation_embed(await h.status.snapshot(),pending),view=h.panel._view(),nonce=pending['nonce'])
    await h.panel.ready()
    assert h.panel.message_id==existing.id and h.channel.send.await_count==2
    assert h.panel.store.read()['previous']==444  # Old marker retained as inert audit evidence.
    old.edit.assert_not_called();old.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['no_match','multiple','truncated','legacy'])
async def test_uncertain_state_is_not_a_reason_to_send_another_panel(positioned,kind):
    h=positioned
    row=h.panel.store.rotate(h.panel.store.read())
    if kind=='legacy':atomic_json(h.panel.store.path,dict(version=1,channel=42,message=None,nonce='a'*24,state='publishing'))
    if kind=='multiple':
        for _ in range(2):await h.channel.send(embed=h.panel._generation_embed(await h.status.snapshot(),row),view=h.panel._view(),nonce=row['nonce'])
    if kind=='truncated':
        async def history(**kwargs):
            for _ in range(101):yield SimpleNamespace(author=SimpleNamespace(id=99))
        h.channel.history=history
    before=h.panel.store.read();count=h.channel.send.await_count
    await h.panel.ready();await h.panel.ready()
    assert h.panel.store.read()==before and h.channel.send.await_count==count


@pytest.mark.asyncio
async def test_legacy_published_panel_is_verified_and_upgraded_on_same_id(positioned):
    h=positioned;await h.panel.stop()
    atomic_json(h.panel.store.path,dict(version=1,channel=42,message=444,nonce='a'*24,state='published'))
    h.messages[444].embeds[0].set_footer(text='legacy')
    new=clone(h);await new.start()
    try:
        assert await new.verified_link() is None
        await new.ready()
        assert new.message_id==444 and h.channel.send.await_count==1
        assert await new.verified_link()=='https://discord.com/channels/71/42/444'
    finally:await new.stop()


@pytest.mark.asyncio
async def test_verified_link_429_is_bounded_without_retry_task_or_new_send(positioned):
    h=positioned;fetch=h.channel.fetch_message.side_effect
    h.channel.fetch_message.side_effect=discord.RateLimited(20)
    assert await h.panel.verified_link() is None
    h.ticks[0]=10;assert await h.panel.verified_link() is None
    assert h.channel.fetch_message.await_count==1 and not h.panel.tasks
    h.ticks[0]=21;h.channel.fetch_message.side_effect=fetch
    assert await h.panel.verified_link()
    assert h.channel.send.await_count==1


@pytest.mark.asyncio
async def test_cancelled_or_stopped_link_lookup_never_binds_late_result(positioned):
    h=positioned;entered=asyncio.Event()
    async def blocked(identity):entered.set();await asyncio.Event().wait()
    h.channel.fetch_message.side_effect=blocked
    task=asyncio.create_task(h.panel.verified_link());await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert h.panel._link_cache is None
    await h.panel.stop()
    assert await h.panel.verified_link() is None


@pytest.mark.asyncio
async def test_external_marker_change_invalidates_old_buttons_and_confirmation(positioned):
    h=positioned;h.status.value['consumer_enabled']=True
    await h.panel.interact(interaction(),'restart')
    nonce=next(iter(h.panel.confirmations))
    row=h.panel.store.read();atomic_json(h.panel.store.path,{**row,'nonce':'a'*24})
    await h.panel.interact(interaction(message=777),'confirm',nonce)
    h.inbox.accept_current.assert_not_called()
    assert h.panel.message_id is None and not h.panel.confirmations


@pytest.mark.asyncio
async def test_adoption_compare_and_swap_never_overwrites_concurrent_marker(positioned):
    h=positioned;h.panel.store.path.unlink()
    row, _=h.panel.store.claim()
    with pytest.raises(ValidationError):h.panel.store.adopt_existing('a'*24,444)
    assert h.panel.store.read()==row
