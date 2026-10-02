"""A5-M1: synthetic combined cancellation/delivery faults at the real controller."""

import asyncio

import pytest

from characterization.summary_support import interaction, settled
from discordbot.platform.errors import (
    CancellationError, DeadlineExceededError, ExternalTemporaryError,
)
from discordbot.summary.adapters.discord_ui import SummaryController
from discordbot.summary.domain.models import Query


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["cancel", "deadline", "provider_error"])
@pytest.mark.parametrize("delivery", ["success", "failure", "timeout"])
async def test_request_outcome_survives_notification_delivery(summary, trigger, delivery):
    controller = SummaryController(summary.service)
    request = interaction()
    entered, provider_done, delivery_done = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def provider(*args, **kwargs):
        entered.set()
        try:
            if trigger == "provider_error":
                raise ExternalTemporaryError("SYNTHETIC_PROVIDER_PRIVATE")
            await asyncio.Event().wait()
        finally:
            provider_done.set()

    async def stalled_delivery(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            delivery_done.set()

    summary.provider.generate.side_effect = provider
    if delivery == "failure":
        request.followup.send.side_effect = RuntimeError("SYNTHETIC_DELIVERY_PRIVATE")
    elif delivery == "timeout":
        request.followup.send.side_effect = stalled_delivery
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if trigger == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert task.cancelled()
        else:
            if trigger == "deadline":
                summary.timers.expire(0)
            await asyncio.wait_for(task, 3)
            assert not task.cancelled()
        await settled()
        assert provider_done.is_set()
        assert not summary.supervisor.snapshot().active
        assert summary.service.active == summary.service.waiting == 0
        assert not summary.service._results and not controller._views and not controller._modals
        request.response.defer.assert_awaited_once_with(thinking=True, ephemeral=False)
        request.response.send_message.assert_not_awaited()
        request.followup.send.assert_awaited_once()
        error = {"cancel": CancellationError, "deadline": DeadlineExceededError,
                 "provider_error": ExternalTemporaryError}[trigger]
        assert request.followup.send.call_args.kwargs == {
            "wait": True, "content": error.default_safe_message, "ephemeral": True,
        }
        events = summary.buffer.drain()
        responses = [event for event in events if event.event == "summary.response"]
        assert [event.result for event in responses] == ([] if delivery == "success" else ["delivery_failed"])
        assert "PRIVATE" not in repr(events)
        if delivery == "timeout":
            assert delivery_done.is_set()  # actual two-second Discord bound cancelled the send
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        controller.close()


@pytest.mark.asyncio
async def test_second_cancel_during_notification_keeps_cancellation_and_single_send(summary):
    controller = SummaryController(summary.service)
    request = interaction()
    entered, sending, send_done = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def provider(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    async def notification(**kwargs):
        sending.set()
        try:
            await asyncio.Event().wait()
        finally:
            send_done.set()

    summary.provider.generate.side_effect = provider
    request.followup.send.side_effect = notification
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(sending.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await settled()
        assert task.cancelled() and send_done.is_set()
        assert not summary.supervisor.snapshot().active
        assert summary.service.active == summary.service.waiting == 0
        assert not summary.service._results and not controller._views
        request.followup.send.assert_awaited_once()
        request.response.send_message.assert_not_awaited()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        controller.close()


@pytest.mark.asyncio
async def test_handoff_cancel_with_failed_notification_reclaims_completed_result(summary):
    controller = SummaryController(summary.service)
    request = interaction()
    request.followup.send.side_effect = RuntimeError("SYNTHETIC_DELIVERY_PRIVATE")
    original_submit = summary.service.submit

    def submit(*args, **kwargs):
        child = original_submit(*args, **kwargs)
        child.add_done_callback(lambda _: task.cancel())
        return child

    summary.service.submit = submit
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await settled()
        assert task.cancelled()
        assert not summary.service._results and not controller._views
        assert not summary.supervisor.snapshot().active
        assert summary.service.active == summary.service.waiting == 0
        request.followup.send.assert_awaited_once()
        assert request.followup.send.call_args.kwargs["ephemeral"] is True
        assert "PRIVATE" not in repr(summary.buffer.drain())
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        controller.close()
