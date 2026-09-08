import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.summary import summary_listeners
from cogs.summary.summary_listeners import SummaryListenersCog


def _interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild.id = 123
    interaction.user.id = 456
    interaction.user.display_name = "요청자"
    interaction.followup.send = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    return interaction


def _summary_cog() -> tuple[SummaryListenersCog, MagicMock]:
    bot = MagicMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "대화"
    bot.get_channel.return_value = channel
    with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}), patch.object(
        summary_listeners,
        "SUMMARY_CHANNEL_ID",
        999,
    ):
        cog = SummaryListenersCog(bot)
    cog.message_log.append(
        (datetime.now(timezone.utc), 123, 456, "요청자", "테스트 메시지")
    )
    return cog, channel


@pytest.mark.asyncio
async def test_f008_fr027_fr030_preserve_summary_success_is_public() -> None:
    """Feature F008; FR-027/FR-030; PRESERVE public result shell."""
    cog, _channel = _summary_cog()
    interaction = _interaction()
    structured = {
        "overall_summary": "전체 요약",
        "topics": [
            {
                "title": "주제",
                "participants": "요청자",
                "keywords": "테스트",
            }
        ],
    }
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=AsyncMock(return_value=("raw", 12)),
    ) as summarize, patch(
        "cogs.summary.summary_listeners.parse_summary_to_structured_data",
        return_value=structured,
    ):
        await cog.execute_summary(interaction, 6.0)

    summarize.assert_awaited_once()
    request = interaction.followup.send.call_args
    assert "embed" in request.kwargs
    assert "view" in request.kwargs
    assert request.kwargs.get("ephemeral", False) is False
    assert request.kwargs["embed"].title == "최근 6.0시간 대화 요약"


@pytest.mark.asyncio
async def test_f008_fr010_fr027_preserve_summary_empty_and_failure_are_private() -> None:
    """Feature F008; FR-010/FR-027; PRESERVE."""
    cog, _channel = _summary_cog()
    cog.message_log.clear()
    interaction = _interaction()
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999):
        await cog.execute_summary(interaction, 1.0)

    args, kwargs = interaction.followup.send.call_args
    assert "요약할 메시지가 없습니다" in args[0]
    assert kwargs["ephemeral"] is True

    cog, _channel = _summary_cog()
    interaction = _interaction()
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=AsyncMock(side_effect=RuntimeError("provider failure")),
    ):
        await cog.execute_summary(interaction, 1.0)
    interaction.followup.send.assert_awaited_once_with(
        "요약 생성 중 치명적인 오류가 발생했습니다. 로그를 확인해주세요.",
        ephemeral=True,
    )


# PHASE 5 CORRECT contracts now execute the V2 application/Discord boundary.
from characterization.summary_support import harness, interaction as v2_interaction, settled
from discordbot.platform.errors import AuthorizationError, CapacityError, DeadlineExceededError
from discordbot.summary.adapters.discord_ui import SummaryController
from discordbot.summary.domain.models import MalformedSummary, Query, Summary, Topic


@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_denies_requester_without_source_acl() -> None:
    """Feature F008; FR-030; CORRECT; V2 ACL precedes extraction and Gemini."""
    fixture = harness()
    fixture.authorization.require.side_effect = AuthorizationError("synthetic denied")
    controller = SummaryController(fixture.service)
    request = v2_interaction()
    try:
        await controller.execute(request, Query())
        fixture.provider.generate.assert_not_awaited()
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
    finally:
        controller.close()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_total_timeout_is_bounded() -> None:
    """Feature F008; FR-030; CORRECT; accepted total deadline is exactly 60 seconds."""
    fixture = harness()
    entered = asyncio.Event()
    async def stall(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    fixture.provider.generate.side_effect = stall
    controller = SummaryController(fixture.service)
    request = v2_interaction()
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        await entered.wait()
        assert fixture.service.deadline_seconds == 60
        assert all(value == 60 for value in fixture.timers.durations)
        fixture.timers.expire(0)
        await task
        request.followup.send.assert_awaited_once()
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
        await settled()
        assert not fixture.supervisor.snapshot().active
    finally:
        controller.close()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_concurrency_is_one() -> None:
    """Feature F008; FR-030; CORRECT; V2 admission serializes actual provider calls."""
    fixture = harness()
    entered, release = asyncio.Event(), asyncio.Event()
    active = peak = 0
    async def provider(*args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        entered.set()
        try:
            await release.wait()
            return Summary("overall", (Topic("topic"),))
        finally:
            active -= 1
    fixture.provider.generate.side_effect = provider
    tasks = [fixture.service.submit(100, 300, 200, Query()) for _ in range(2)]
    try:
        await entered.wait()
        assert fixture.service.waiting == 1
        release.set()
        await asyncio.gather(*tasks)
        assert peak == 1 and active == 0
    finally:
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_f008_fr010_fr030_correct_summary_parse_error_is_private_and_redacted() -> None:
    """Feature F008; FR-010/FR-030; CORRECT; V2 never sends/logs raw malformed output."""
    fixture = harness()
    fixture.provider.generate.side_effect = MalformedSummary("private source material SECRET")
    controller = SummaryController(fixture.service)
    request = v2_interaction()
    try:
        await controller.execute(request, Query())
        kwargs = request.followup.send.call_args.kwargs
        assert kwargs["ephemeral"] is True
        assert "private source material" not in kwargs["content"]
        assert "SECRET" not in repr(fixture.buffer.drain())
    finally:
        controller.close()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_waiting_queue_capacity_is_four() -> None:
    """Feature F008; FR-030; CORRECT; V2 active one plus four waiting, sixth rejected."""
    fixture = harness()
    entered, release = asyncio.Event(), asyncio.Event()
    async def provider(*args, **kwargs):
        entered.set()
        await release.wait()
        return Summary("overall", (Topic("topic"),))
    fixture.provider.generate.side_effect = provider
    tasks = [fixture.service.submit(100, 300, 200, Query()) for _ in range(5)]
    try:
        await entered.wait()
        with pytest.raises(CapacityError):
            fixture.service.submit(100, 300, 200, Query())
        assert fixture.service.active == 1 and fixture.service.waiting == 4
        release.set()
        await asyncio.gather(*tasks)
        assert fixture.provider.generate.await_count == 5
        await settled()
        assert fixture.service.active == fixture.service.waiting == 0
    finally:
        await fixture.service.stop()
