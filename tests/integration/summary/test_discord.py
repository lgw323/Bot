import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from characterization.summary_support import harness, interaction, settled
from discordbot.platform.errors import AuthorizationError, ExternalPermanentError, ExternalTemporaryError
from discordbot.summary.adapters.discord_io import DiscordAuthorization, message_value
from discordbot.summary.adapters.discord_ui import SummaryCog, SummaryController, SummaryView, summary_embed
from discordbot.summary.domain.models import MalformedSummary, Query, Scope, Summary, Topic


@pytest.mark.asyncio
async def test_command_signature_public_shell_and_binding(summary):
    controller = SummaryController(summary.service)
    cog = SummaryCog(controller)
    command = cog.get_app_commands()[0]
    assert (command.name, command.description) == ("요약", "최근 대화를 요약합니다.")
    assert [(p.name, p.type, p.default) for p in command.parameters] == [("hours", discord.AppCommandOptionType.number, 6.0)]
    request = interaction()
    try:
        await command.callback(cog, request)
        request.response.defer.assert_awaited_once_with(thinking=True, ephemeral=False)
        request.followup.send.assert_awaited_once()
        kwargs = request.followup.send.call_args.kwargs
        assert kwargs["ephemeral"] is False
        assert kwargs["embed"].title == "최근 6.0시간 대화 요약"
        assert [item.label for item in kwargs["view"].children[:2]] == ["새로고침", "고급 요약"]
        result = next(iter(summary.service._results.values()))
        assert result.message_id == 500
    finally:
        controller.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["invalid", "dm", "no_data", "denied", "transient", "permanent", "malformed"])
async def test_failure_one_private_responder(summary, kind):
    controller = SummaryController(summary.service)
    request = interaction(guild=0 if kind == "dm" else 100)
    if kind == "no_data":
        summary.capture.clear()
    if kind == "denied":
        summary.authorization.require.side_effect = AuthorizationError("SECRET")
    errors = {"transient": ExternalTemporaryError, "permanent": ExternalPermanentError, "malformed": MalformedSummary}
    if kind in errors:
        summary.provider.generate.side_effect = errors[kind]("SECRET raw prompt", safe_message="SECRET override")
    try:
        await controller.execute(request, Query(0 if kind == "invalid" else 6))
        pre = kind in {"invalid", "dm"}
        assert request.response.defer.await_count == (0 if pre else 1)
        send = request.response.send_message if pre else request.followup.send
        send.assert_awaited_once()
        assert send.call_args.kwargs["ephemeral"] is True
        assert "SECRET" not in str(send.call_args)
        if kind == "no_data":
            assert "요약할 메시지가 없습니다" in send.call_args.kwargs["content"]
    finally:
        controller.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["defer", "followup", "error_followup"])
async def test_uncertain_discord_failure_never_retries(summary, stage):
    controller = SummaryController(summary.service)
    request = interaction()
    if stage == "defer":
        request.response.defer.side_effect = RuntimeError("token=SECRET")
    else:
        request.followup.send.side_effect = RuntimeError("token=SECRET")
    if stage == "error_followup":
        summary.provider.generate.side_effect = ExternalTemporaryError("SECRET")
    try:
        await controller.execute(request, Query())
        assert request.response.defer.await_count == 1
        assert request.followup.send.await_count == (0 if stage == "defer" else 1)
        request.response.send_message.assert_not_awaited()
        assert "SECRET" not in repr(summary.buffer.drain())
        assert not summary.service._results
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_end_to_end_timeout_and_cancel_single_followup(summary):
    entered = asyncio.Event()
    async def stall(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    summary.provider.generate.side_effect = stall
    controller = SummaryController(summary.service)
    request = interaction()
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        await entered.wait()
        summary.timers.expire(0)  # outer request timer owns queue, provider and presentation
        await task
        request.followup.send.assert_awaited_once()
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
        await settled()
        assert not summary.supervisor.snapshot().active
        assert not summary.service._results
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_refresh_modal_topic_and_stale_context(summary):
    controller = SummaryController(summary.service)
    first = interaction()
    try:
        await controller.execute(first, Query(2, "합성", "합성 사용자", "차분한 표현"))
        original = next(iter(summary.service._results.values()))
        refresh = interaction(message=500)
        refresh.followup.send.return_value.id = 501
        await controller.refresh(refresh, original.id)
        result = list(summary.service._results.values())[-1]
        assert result.query == original.query
        assert result.id != original.id and result.message_id == 501
        detail = interaction(message=500)
        await controller.detail(detail, original.id, original.page(0)[0][0])
        assert detail.response.send_message.call_args.kwargs["ephemeral"] is True
        assert detail.response.send_message.call_args.kwargs["embed"].title.startswith("주제 1:")
        advanced = interaction(message=500)
        await controller.advanced(advanced, original.id)
        modal = advanced.response.send_modal.call_args.args[0]
        assert modal.timeout == 300
        assert [i._underlying.label for i in modal.children] == ["포함할 키워드 (쉼표로 구분)", "특정 사용자 이름 (쉼표로 구분)", "추가 요청사항"]
        modal.keywords._value = "합성"
        submitted = interaction(message=502)
        await modal.on_submit(submitted)
        assert submitted.followup.send.call_args.kwargs["ephemeral"] is False
        for bad in (interaction(guild=101, channel=201), interaction(channel=999), interaction(message=999)):
            await controller.detail(bad, original.id, original.page(0)[0][0])
            assert "embed" not in bad.response.send_message.call_args.kwargs
        invalid = interaction()
        await controller.detail(invalid, original.id, f"{result.id}:0")
        assert "embed" not in invalid.response.send_message.call_args.kwargs
        summary.clock.tick += 3601
        stale = interaction()
        await controller.refresh(stale, original.id)
        assert stale.response.send_message.call_args.kwargs["ephemeral"] is True
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_26_topics_pagination_and_absolute_selection_ids():
    fixture = harness(topics=26)
    controller = SummaryController(fixture.service)
    try:
        first = interaction()
        await controller.execute(first, Query())
        result = next(iter(fixture.service._results.values()))
        view = first.followup.send.call_args.kwargs["view"]
        assert len(view.children[2].options) == 25
        navigation = interaction()
        await next(item for item in view.children if getattr(item, "label", "") == "다음").callback(navigation)
        next_view = navigation.response.edit_message.call_args.kwargs["view"]
        assert [option.value for option in next_view.children[2].options] == [f"{result.id}:25"]
        selected = interaction()
        selected.data["values"] = [f"{result.id}:25"]
        await next_view.children[2].callback(selected)
        assert selected.response.send_message.call_args.kwargs["embed"].title == "주제 26: 주제 25"
        assert len(result.summary.topics) == 26
        assert view.is_finished()
    finally:
        controller.close()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_acl_adapter_checks_source_guild_and_both_permissions():
    member = object()
    channel = SimpleNamespace(guild=SimpleNamespace(id=100), permissions_for=MagicMock())
    bot = SimpleNamespace(get_channel=lambda _: channel,
                          get_guild=lambda _: SimpleNamespace(get_member=lambda _: member))
    authorization = DiscordAuthorization(bot)
    for view, history in ((False, False), (True, False), (False, True)):
        channel.permissions_for.return_value = SimpleNamespace(view_channel=view, read_message_history=history)
        with pytest.raises(AuthorizationError):
            await authorization.require(Scope(100, 200), 300)
    channel.permissions_for.return_value = SimpleNamespace(view_channel=True, read_message_history=True)
    await authorization.require(Scope(100, 200), 300)
    with pytest.raises(AuthorizationError):
        await authorization.require(Scope(101, 200), 300)


def test_dm_and_nonbot_system_policy_translation():
    assert message_value(SimpleNamespace(guild=None)) is None
    # V1 capture examines bot/guild/content, not Message.type. Preserve that.
    message = SimpleNamespace(guild=SimpleNamespace(id=100), channel=SimpleNamespace(id=200), id=1,
        author=SimpleNamespace(bot=False, display_name="synthetic"), content="system content",
        created_at=None, type=discord.MessageType.pins_add)
    assert message_value(message).content == "system content"


@pytest.mark.asyncio
async def test_cancellation_at_result_handoff_reclaims_unbound_result(summary):
    controller = SummaryController(summary.service)
    original_submit = summary.service.submit
    parent = None
    def submit(*args, **kwargs):
        task = original_submit(*args, **kwargs)
        # Registered before Controller awaits the task: deterministic handoff race.
        task.add_done_callback(lambda _: parent.cancel())
        return task
    summary.service.submit = submit
    request = interaction()
    try:
        parent = asyncio.create_task(controller.execute(request, Query()))
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert not summary.service._results and not controller._views
        request.followup.send.assert_awaited_once()
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
        await settled()
        assert not summary.supervisor.snapshot().active
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_stalled_provider_does_not_block_capture_or_unrelated_async_probe(summary):
    from discordbot.summary.domain.models import Message

    entered, release, probe = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def stall(*args, **kwargs):
        entered.set()
        await release.wait()
        return Summary("ok", (Topic("ok"),))
    summary.provider.generate.side_effect = stall
    task = summary.service.submit(100, 300, 200, Query())
    await entered.wait()
    async def independent():
        await asyncio.sleep(0)
        probe.set()
    await independent()
    summary.capture.add(Message(Scope(101, 201), 2, summary.clock.now(), "synthetic", "while waiting"))
    assert probe.is_set() and len(summary.capture.read(Scope(101, 201))) == 2
    assert not task.done()
    release.set()
    await task
