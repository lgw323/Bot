import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discordbot.music.adapters.discord_ui import MusicController, Responder, build_dashboard, build_search_modal, build_song_view
from discordbot.music.adapters.runtime import build_music_cog
from discordbot.music.domain.pages import SongPages
from discordbot.platform.errors import AuthorizationError, ConflictError
from .conftest import song

pytestmark = pytest.mark.asyncio


def interaction(guild=100, user=10, channel=55, voice=123):
    member = SimpleNamespace(id=user, voice=SimpleNamespace(channel=SimpleNamespace(id=voice, guild=SimpleNamespace(id=guild))) if voice else None)
    return SimpleNamespace(id=999, guild_id=guild, channel_id=channel, user=member,
        response=SimpleNamespace(is_done=lambda: False, defer=AsyncMock(), send_message=AsyncMock(), edit_message=AsyncMock(), send_modal=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()))


def controller(rig):
    actor = rig[0]()
    return MusicController(AsyncMock(return_value=actor), rig[6], rig[1], {100:55}, 99), actor


async def test_command_required_string_private_defer_and_search(rig):
    control, actor = controller(rig)
    cog = build_music_cog(SimpleNamespace(controller=control))
    command = cog.get_app_commands()[0]
    assert command.name == "재생"
    assert command.description == "유튜브 링크나 검색어로 노래를 재생하고, 봇을 음성 채널로 자동 초대합니다."
    assert [(p.name, p.required, p.type) for p in command.parameters] == [("검색어", True, discord.AppCommandOptionType.string)]
    request = interaction()
    try:
        await command.callback(cog, request, "찾을 노래")
        request.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        assert request.followup.send.call_args.kwargs["content"] == "**🔎 검색 결과:**"
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
        view = request.followup.send.call_args.kwargs["view"]
        assert view.children[0].placeholder == "재생할 노래를 선택하세요..."
        assert not actor.projection().current
    finally: control.close()


@pytest.mark.parametrize("voice,master,expected", [(123,False,True), (None,False,False), (None,True,False)])
async def test_request_voice_policy(rig, voice, master, expected):
    control, actor = controller(rig)
    request = interaction(user=99 if master else 10, voice=voice)
    if expected:
        assert await control.voice(actor, request.user)
    else:
        with pytest.raises(AuthorizationError): await control.voice(actor, request.user)
    if master:
        await actor.ask("connect", channel_id=555)
        assert not await control.voice(actor, request.user)
    control.close()


async def test_cross_guild_move_denied_and_own_voice_move_allowed(rig):
    control, actor = controller(rig)
    await actor.ask("connect", channel_id=222)
    assert await control.voice(actor, interaction(voice=123).user)
    with pytest.raises(AuthorizationError): await control.voice(actor, interaction(guild=200).user)
    control.close()


@pytest.mark.parametrize("stage", ["channel", "provider", "defer", "followup"])
async def test_cf19_single_responder_failures(rig, stage):
    control, actor = controller(rig)
    request = interaction(channel=22 if stage == "channel" else 55)
    if stage == "provider": rig[5].lookup.side_effect = TimeoutError("SECRET")
    if stage == "defer": request.response.defer.side_effect = RuntimeError("SECRET")
    if stage == "followup": request.followup.send.side_effect = RuntimeError("SECRET")
    try:
        await control.request(request, "https://youtube.com/watch?v=synthetic")
        assert request.response.defer.await_count == 1
        assert request.followup.send.await_count == (0 if stage == "defer" else 1)
        assert not request.response.send_message.await_count
        assert "SECRET" not in str(request.followup.send.call_args)
    finally: control.close()


@pytest.mark.parametrize("kind", ["search", "queue", "favorites"])
async def test_pagination_26_stable_ids_duplicate_titles_owner_expiry(rig, kind):
    control, actor = controller(rig)
    pages = SongPages(100,10,120,tuple(song(i, "same") for i in range(26)))
    view = build_song_view(control, pages, kind)
    try:
        assert len(view.songs) == 26 and len(view.children[0].options) == 25
        request = interaction()
        button = next(item for item in view.children if getattr(item, "label", None) == "다음")
        await button.callback(request)
        assert view.children[0].options[0].value == "25"
        assert pages.select(("25",), 100, 10, 110)[0].item_id == "25"
        with pytest.raises(AuthorizationError): pages.select(("25",), 200, 10, 110)
        with pytest.raises(AuthorizationError): pages.select(("25",), 100, 11, 110)
        with pytest.raises(ConflictError): pages.select(("25",), 100, 10, 120)
        with pytest.raises(ConflictError): pages.select(("not-present",), 100, 10, 110)
    finally: view.stop(); control.close()


async def test_dashboard_inventory_and_stale_skip(rig):
    control, actor = controller(rig)
    await actor.ask("enqueue", tracks=(song(), song(2)))
    state = actor.projection()
    top = tuple(SimpleNamespace(url="u", title="Top", count=i) for i in range(3))
    view = build_dashboard(control, state, top)
    modal = build_search_modal(control)
    try:
        assert len(view.children) == 12
        assert [str(item.emoji) for item in view.children[:5]] == ["⏸️", "⏭️", "⏹️", "⭐", "📜"]
        assert [item.label for item in view.children[5:9]] == ["반복 없음", "추천재생: OFF", "보관함", "노래 검색"]
        assert modal.title == "🎵 노래 검색 및 재생" and modal.timeout == 180
        await control.action(interaction(), "skip", state)
        await control.action(interaction(), "skip", state)
        assert actor.projection().current.item_id == "2"
    finally: view.stop(); modal.stop(); control.close()


async def test_message_delete_before_provider_and_public_failure_tolerance(rig):
    control, actor = controller(rig)
    order = []
    async def delete(): order.append("delete"); raise PermissionError("synthetic")
    async def lookup(*args, **kwargs): order.append("lookup"); return (song(),)
    rig[5].lookup.side_effect = lookup
    request = interaction()
    request.user.bot = False
    message = SimpleNamespace(id=77, author=request.user, guild=SimpleNamespace(id=100),
        content="https://youtube.com/watch?v=synthetic", channel=SimpleNamespace(id=55, send=AsyncMock()), delete=delete)
    try:
        await control.message(message)
        assert order == ["delete", "lookup"]
        assert "ephemeral" not in message.channel.send.call_args.kwargs
        assert message.channel.send.call_args.kwargs["delete_after"] == 5
    finally: control.close()


async def test_responder_concurrent_sends_only_once():
    request = interaction()
    responder = Responder(request)
    await asyncio.gather(responder.send("one", ephemeral=True), responder.send("two", ephemeral=True))
    assert request.response.send_message.await_count == 1


async def test_favorite_batch_keeps_partial_success_in_original_order(rig):
    control, actor = controller(rig)
    async def lookup(query, user, **kwargs):
        if query.endswith("/2"): raise TimeoutError("synthetic missing favorite")
        return (song(1 if query.endswith("/1") else 3),)
    rig[5].lookup.side_effect = lookup
    try:
        assert await control.add_favorites(actor, (song(), song(2), song(3)), 10, "batch") == 2
        assert actor.projection().current.item_id == "1"
        assert [song.item_id for song in actor.projection().queue] == ["3"]
    finally: control.close()
