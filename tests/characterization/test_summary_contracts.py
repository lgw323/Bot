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


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 does not verify requester access to the source channel",
)
@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_denies_requester_without_source_acl() -> None:
    """Feature F008; FR-030; CORRECT."""
    cog, channel = _summary_cog()
    channel.permissions_for.return_value = SimpleNamespace(
        view_channel=False,
        read_message_history=False,
    )
    interaction = _interaction()
    summarize = AsyncMock(return_value=("raw", 1))
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=summarize,
    ), patch(
        "cogs.summary.summary_listeners.parse_summary_to_structured_data",
        return_value={"overall_summary": "x", "topics": [{"title": "x"}]},
    ):
        await cog.execute_summary(interaction, 1.0)

    summarize.assert_not_awaited()
    assert interaction.followup.send.call_args.kwargs["ephemeral"] is True


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 has no bounded Gemini total timeout",
)
@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_total_timeout_is_bounded() -> None:
    """Feature F008; FR-030; CORRECT; accepted total timeout is 60 seconds."""
    cog, _channel = _summary_cog()
    interaction = _interaction()
    never = asyncio.Event()

    async def stalled_summary(*_args: object, **_kwargs: object) -> tuple[str, int]:
        await never.wait()
        return "unreachable", 0

    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=stalled_summary,
    ):
        await asyncio.wait_for(cog.execute_summary(interaction, 1.0), timeout=0.05)

    assert interaction.followup.send.call_args.kwargs["ephemeral"] is True


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 allows concurrent Gemini calls instead of active=1, queue=4",
)
@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_concurrency_is_one() -> None:
    """Feature F008; FR-030; CORRECT; accepted concurrency=1 and queue capacity=4."""
    cog, _channel = _summary_cog()
    active = 0
    maximum_active = 0
    release = asyncio.Event()

    async def measured_summary(*_args: object, **_kwargs: object) -> tuple[str, int]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await release.wait()
            return "raw", 1
        finally:
            active -= 1

    interactions = [_interaction(), _interaction()]
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=measured_summary,
    ), patch(
        "cogs.summary.summary_listeners.parse_summary_to_structured_data",
        return_value={"overall_summary": "x", "topics": [{"title": "x"}]},
    ):
        tasks = [
            asyncio.create_task(cog.execute_summary(interaction, 1.0))
            for interaction in interactions
        ]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)

    assert maximum_active == 1


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: parse failures must not publish raw provider output",
)
@pytest.mark.asyncio
async def test_f008_fr010_fr030_correct_summary_parse_error_is_private_and_redacted() -> None:
    """Feature F008; FR-010/FR-030; CORRECT."""
    cog, _channel = _summary_cog()
    interaction = _interaction()
    sensitive_text = "private source material"
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=AsyncMock(return_value=(sensitive_text, 1)),
    ), patch(
        "cogs.summary.summary_listeners.parse_summary_to_structured_data",
        return_value={},
    ):
        await cog.execute_summary(interaction, 1.0)

    args, kwargs = interaction.followup.send.call_args
    assert sensitive_text not in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 has no four-request Summary waiting queue",
)
@pytest.mark.asyncio
async def test_f008_fr030_correct_summary_waiting_queue_capacity_is_four() -> None:
    """Feature F008; FR-030; CORRECT; one active plus four waiting requests."""
    cog, _channel = _summary_cog()
    release = asyncio.Event()
    provider_calls = 0

    async def queued_summary(*_args: object, **_kwargs: object) -> tuple[str, int]:
        nonlocal provider_calls
        provider_calls += 1
        await release.wait()
        return "raw", 1

    interactions = [_interaction() for _ in range(6)]
    with patch.object(summary_listeners, "SUMMARY_CHANNEL_ID", 999), patch(
        "cogs.summary.summary_listeners.gemini_summarize",
        new=queued_summary,
    ), patch(
        "cogs.summary.summary_listeners.parse_summary_to_structured_data",
        return_value={"overall_summary": "x", "topics": [{"title": "x"}]},
    ):
        tasks = [
            asyncio.create_task(cog.execute_summary(interaction, 1.0))
            for interaction in interactions
        ]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)

    assert provider_calls == 5
    overloads = [
        interaction
        for interaction in interactions
        if interaction.followup.send.call_args.kwargs.get("ephemeral") is True
    ]
    assert len(overloads) == 1
