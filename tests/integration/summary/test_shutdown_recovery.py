"""Independent cleanup and retry after a Summary dependency fails to close."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from characterization.summary_support import harness, interaction
from discordbot.platform.errors import ShutdownError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec
from discordbot.summary.adapters.runtime import SummaryResource
from discordbot.summary.domain.models import Query, Scope


def resource_fixture():
    fixture = harness()
    bot = SimpleNamespace(add_cog=AsyncMock(), remove_cog=AsyncMock(), add_listener=MagicMock(),
                          remove_listener=MagicMock(), close=AsyncMock())
    resource = SummaryResource(bot, fixture.config, fixture.provider, fixture.clock,
                               fixture.service.telemetry, owns_bot=True)
    resource.service.require_preload = False
    resource.service.capture = fixture.capture
    resource.service.authorization = fixture.authorization
    return resource, fixture, bot


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['provider', 'bot', 'both'])
async def test_close_failure_cleans_independent_owners_and_retries_only_pending(failure):
    resource, fixture, bot = resource_fixture()
    original = RuntimeError('synthetic first close failure')
    secondary = RuntimeError('synthetic second close failure')
    try:
        await resource.start()
        request = interaction()
        await resource.controller.execute(request, Query())
        view = request.followup.send.call_args.kwargs['view']
        result = next(iter(resource.service._results.values()))
        modal_request = interaction()
        await resource.controller.advanced(modal_request, result.id)
        modal = modal_request.response.send_modal.call_args.args[0]
        if failure in ('provider', 'both'):
            fixture.provider.close.side_effect = original
        if failure in ('bot', 'both'):
            bot.close.side_effect = original if failure == 'bot' else secondary
        with pytest.raises(RuntimeError) as captured:
            await resource.stop()
        assert captured.value is original
        assert view.is_finished() and modal.is_finished()
        assert not resource.controller._views and not resource.controller._modals
        assert not resource.background.snapshot().active and not resource.service.supervisor.snapshot().active
        assert not resource.service._results and not fixture.capture.read(Scope(100, 200))
        bot.close.assert_awaited_once()
        fixture.provider.close.assert_awaited_once()
        assert not resource.startup_cleanup_complete
        fixture.provider.close.side_effect = bot.close.side_effect = None
        await resource.stop()
        await resource.stop()
        assert resource.startup_cleanup_complete and resource._closed
        assert fixture.provider.close.await_count == (1 if failure == 'bot' else 2)
        assert bot.close.await_count == (1 if failure == 'provider' else 2)
        bot.remove_cog.assert_awaited_once()
    finally:
        fixture.provider.close.side_effect = bot.close.side_effect = None
        resource.controller.close()
        await resource.service.stop()
        await fixture.service.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_partial_start_preserves_original_error_when_cleanup_also_fails(cancelled):
    resource, fixture, bot = resource_fixture()
    original = asyncio.CancelledError() if cancelled else RuntimeError('synthetic start error')
    fixture.provider.start = AsyncMock(side_effect=original)
    fixture.provider.close.side_effect = RuntimeError('synthetic cleanup error')
    try:
        with pytest.raises(type(original)) as captured:
            await resource.start()
        assert captured.value is original
        bot.close.assert_awaited_once()
        assert not resource.startup_cleanup_complete
        fixture.provider.close.side_effect = None
        await resource.stop()
        assert resource.startup_cleanup_complete
        bot.close.assert_awaited_once()
    finally:
        fixture.provider.close.side_effect = None
        await resource.service.stop()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_cancel_during_provider_close_cleans_view_and_bot_then_can_retry():
    resource, fixture, bot = resource_fixture()
    entered = asyncio.Event()
    async def stall() -> None:
        entered.set()
        await asyncio.Event().wait()
    task = None
    try:
        await resource.start()
        request = interaction()
        await resource.controller.execute(request, Query())
        view = request.followup.send.call_args.kwargs['view']
        fixture.provider.close.side_effect = stall
        task = asyncio.create_task(resource.stop())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert view.is_finished()
        bot.close.assert_awaited_once()
        fixture.provider.close.side_effect = None
        await resource.stop()
        assert resource.startup_cleanup_complete
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        fixture.provider.close.side_effect = None
        resource.controller.close()
        await resource.service.stop()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_unfinished_background_preserves_dependencies_then_retry(monkeypatch):
    resource, fixture, bot = resource_fixture()
    entered, release = asyncio.Event(), asyncio.Event()
    async def hostile() -> None:
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
    original_shutdown = resource.background.shutdown
    async def bounded(**kwargs):
        return await original_shutdown(grace_seconds=.01)
    monkeypatch.setattr(resource.background, 'shutdown', bounded)
    task = None
    try:
        await resource.start()
        task = resource.background.start(TaskSpec('hostile', 'test', 'one', 'one', 5,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), hostile)
        await entered.wait()
        with pytest.raises(ShutdownError):
            await resource.stop()
        fixture.provider.close.assert_not_awaited()
        bot.close.assert_not_awaited()
        release.set()
        await task
        await resource.stop()
        assert resource.startup_cleanup_complete
    finally:
        release.set()
        if task is not None:
            await task
        await resource.service.stop()
        await fixture.service.stop()
