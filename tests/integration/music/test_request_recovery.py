import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from discord.ui.view import ViewStore

from discordbot.music.adapters.discord_ui import build_song_view
from discordbot.music.domain.model import Bounds
from discordbot.music.domain.pages import SongPages
from discordbot.platform.errors import CapacityError, ConflictError, ExternalPermanentError
from .conftest import settle, song
from .test_discord import controller, interaction

pytestmark = pytest.mark.asyncio


def message():
    user=interaction().user
    user.bot=False
    return SimpleNamespace(id=77,author=user,guild=SimpleNamespace(id=100),
        content='https://youtube.com/watch?v=synthetic',
        channel=SimpleNamespace(id=55,send=AsyncMock()),delete=AsyncMock())


@pytest.mark.parametrize('error',[RuntimeError,TimeoutError])
async def test_public_connect_failure_replies_once_and_next_request_recovers(rig,error):
    control,actor=controller(rig)
    request=message()
    rig[3].connect.side_effect=error('private synthetic')
    try:
        await control.message(request)
        request.channel.send.assert_awaited_once_with('노래 정보를 가져오는 중 오류가 발생했습니다.',delete_after=8)
        assert actor.projection().current is None
        rig[3].connect.side_effect=None
        request.id=78
        await control.message(request)
        await settle(lambda:actor.projection().status=='playing')
        assert request.channel.send.await_count==2
    finally: await control.stop()


@pytest.mark.parametrize('stage',['connect','send'])
async def test_public_cancellation_is_preserved_without_fallback(rig,stage):
    control,_=controller(rig)
    request=message()
    entered,release=asyncio.Event(),asyncio.Event()
    async def connect(_): entered.set(); await release.wait()
    if stage=='connect': rig[3].connect.side_effect=connect
    else: request.channel.send.side_effect=asyncio.CancelledError()
    task=asyncio.create_task(control.message(request))
    try:
        if stage=='connect':
            await entered.wait()
            task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert request.channel.send.await_count==(stage=='send')
    finally: release.set(); await control.stop()


@pytest.mark.parametrize('error',[RuntimeError,TimeoutError,ExternalPermanentError])
async def test_public_ambiguous_send_never_gets_second_response(rig,error):
    control,_=controller(rig)
    request=message()
    request.channel.send.side_effect=error('private synthetic')
    try:
        with pytest.raises(error): await control.message(request)
        assert request.channel.send.await_count==1
    finally: await control.stop()


@pytest.mark.parametrize('failure',['voice','connect'])
async def test_selection_pre_enqueue_failure_can_retry_same_view(rig,failure):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    if failure=='connect': rig[3].connect.side_effect=TimeoutError('private')
    try:
        await view.perform(interaction(voice=None if failure=='voice' else 123),'add')
        assert not view.consumed and actor.projection().current is None
        rig[3].connect.side_effect=None
        retry=interaction()
        retry.id=1000
        await view.perform(retry,'add')
        await settle(lambda:actor.projection().status=='playing')
        assert view.consumed and not actor.projection().queue
        assert rig[6].record_start.await_count==1
    finally: view.stop(); await control.stop()


async def test_selection_concurrent_clicks_only_admit_one(rig):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    entered,release=asyncio.Event(),asyncio.Event()
    async def connect(_): entered.set(); await release.wait()
    rig[3].connect.side_effect=connect
    first=asyncio.create_task(view.perform(interaction(),'add'))
    try:
        await entered.wait()
        second=interaction(); second.id=1000
        await view.perform(second,'add')
        assert rig[3].connect.await_count==1
        release.set(); await first
        await settle(lambda:actor.projection().status=='playing')
        assert not actor.projection().queue and rig[6].record_start.await_count==1
    finally: release.set(); await first; view.stop(); await control.stop()


@pytest.mark.parametrize('failure',['cancel','timeout','response'])
async def test_selection_accepted_or_uncertain_enqueue_stays_consumed(rig, failure):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    original=actor.ask
    async def ask(operation,**kwargs):
        value=await original(operation,**kwargs)
        if operation=='enqueue' and failure!='response':
            raise asyncio.CancelledError() if failure=='cancel' else TimeoutError('uncertain')
        return value
    actor.ask=ask
    request=interaction()
    if failure=='response': request.followup.send.side_effect=TimeoutError('uncertain response')
    try:
        if failure=='cancel':
            with pytest.raises(asyncio.CancelledError):
                await view.perform(request,'add')
        else: await view.perform(request,'add')
        assert view.consumed
        await view.perform(interaction(),'add')
        await settle(lambda:actor.projection().status=='playing')
        assert not actor.projection().queue and rig[6].record_start.await_count==1
        if failure=='response': assert request.followup.send.await_count==1
    finally: view.stop(); await control.stop()


@pytest.mark.parametrize('error',[CapacityError,ConflictError])
async def test_definite_enqueue_rejection_allows_retry(rig,error):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    original=actor.ask
    async def reject(operation,**kwargs):
        if operation=='enqueue': raise error('synthetic rejection before enqueue')
        return await original(operation,**kwargs)
    actor.ask=reject
    try:
        await view.perform(interaction(),'add')
        assert not view.consumed and not view.adding and actor.projection().current is None
        actor.ask=original
        await view.perform(interaction(),'add')
        await settle(lambda:actor.projection().status=='playing')
    finally: view.stop(); await control.stop()


async def test_partial_favorite_delete_failure_stays_consumed(rig):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),song(2))),'favorites')
    view.selected={'1','2'}; view.deleting=True
    rig[6].remove_favorite.side_effect=[True,TimeoutError('ambiguous delete')]
    try:
        await view.perform(interaction(),'add')
        assert view.consumed and not view.adding
        await view.perform(interaction(),'add')
        assert rig[6].remove_favorite.await_count==2
    finally: view.stop(); await control.stop()


async def test_selection_cancel_before_enqueue_can_retry(rig):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    entered,release=asyncio.Event(),asyncio.Event()
    async def connect(_): entered.set(); await release.wait()
    rig[3].connect.side_effect=connect
    task=asyncio.create_task(view.perform(interaction(),'add'))
    try:
        await entered.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert not view.consumed and not view.adding
        release.set()
        rig[3].connect.side_effect=None
        await view.perform(interaction(),'add')
        await settle(lambda:actor.projection().status=='playing')
        assert not actor.projection().queue
    finally: release.set(); view.stop(); await control.stop()


async def test_sdk_selection_same_view_recovers_after_connect_failure(rig):
    control,actor=controller(rig)
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    store=ViewStore(SimpleNamespace())
    store.add_view(view,500)
    async def dispatch(identity):
        request=interaction(); request.id=identity
        request.message=SimpleNamespace(id=500)
        request.data={'component_type':3,'custom_id':'music:search:select','values':['1']}
        store.dispatch_view(3,'music:search:select',request)
        tasks=tuple(store._ViewStore__tasks)
        assert tasks
        await asyncio.wait_for(asyncio.gather(*tasks),2)
        return request
    rig[3].connect.side_effect=TimeoutError('synthetic')
    try:
        first=await dispatch(1)
        assert first.followup.send.await_count==1 and not view.consumed
        rig[3].connect.side_effect=None
        second=await dispatch(2)
        await settle(lambda:actor.projection().status=='playing')
        assert second.followup.send.await_count==1 and view.is_finished()
        assert rig[6].record_start.await_count==1
    finally: view.stop(); await control.stop()


async def test_real_full_queue_rejection_then_same_selection_retry(rig):
    control,actor=controller(rig)
    actor.bounds=Bounds(queue=1)
    await actor.ask('enqueue',tracks=(song(2),))
    await actor.ask('enqueue',tracks=(song(3),))
    view=build_song_view(control,SongPages(100,10,280,(song(),)),'search')
    view.selected={'1'}
    try:
        await view.perform(interaction(),'add')
        assert not view.consumed
        assert [track.item_id for track in actor.projection().queue]==['3']
        await actor.ask('edit',action='clear',revision=actor.projection().revision)
        await view.perform(interaction(),'add')
        assert view.consumed
        assert [track.title for track in actor.projection().queue]==['Track 1']
    finally: view.stop(); await control.stop()
