import asyncio

import pytest

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
