import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from characterization.summary_support import harness, interaction, settled
from discordbot.platform.errors import ConflictError
from discordbot.summary.adapters.runtime import SummaryResource
from discordbot.summary.adapters.discord_ui import SummaryController, summary_embed
from discordbot.summary.domain.models import Message, Query, Scope, Summary, SummaryConfig, Topic


def fake_bot():
    return SimpleNamespace(add_cog=AsyncMock(), remove_cog=AsyncMock(), add_listener=MagicMock(),
                           remove_listener=MagicMock(), close=AsyncMock())


@pytest.mark.asyncio
async def test_repeated_ready_during_preload_coalesces_then_reconciles():
    fixture = harness(config=SummaryConfig((Scope(100, 200),)))
    bot = fake_bot()
    resource = SummaryResource(bot, fixture.config, fixture.provider, fixture.clock, fixture.service.telemetry)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def page(scope, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            return (Message(scope, 1, fixture.clock.now(), "name", "old"),)
        return (Message(scope, 2, fixture.clock.now(), "name", "reconnected"),)
    resource.history = SimpleNamespace(page=page)
    try:
        await resource.start()
        await resource.start()
        await resource.ready()
        await entered.wait()
        for _ in range(20):
            await resource.ready()
        assert calls == 1
        assert len(resource.background.snapshot().active) == 2
        release.set()
        await resource._preload
        await settled()
        await resource._preload
        assert calls == 2
        assert [m.id for m in resource.service.capture.read(Scope(100, 200))] == [1, 2]
        bot.add_cog.assert_awaited_once()
        assert bot.add_listener.call_count == 3
        assert "on_resumed" in [call.args[1] for call in bot.add_listener.call_args_list]
        assert not any("edit" in call.args[1] or "delete" in call.args[1] for call in bot.add_listener.call_args_list)
    finally:
        await resource.stop()
        await fixture.service.stop()
    assert not resource.background.snapshot().active
    await resource.ready()
    assert calls == 2
    with pytest.raises(ConflictError):
        await resource.start()


@pytest.mark.asyncio
async def test_disabled_resource_no_client_history_cleanup_and_owns_bot_close():
    fixture = harness(config=SummaryConfig((Scope(100, 200),), enabled=False))
    fixture.provider.start = AsyncMock()
    resource = SummaryResource(fake_bot(), fixture.config, fixture.provider, fixture.clock,
                               fixture.service.telemetry, owns_bot=True)
    await resource.start()
    await resource.ready()
    assert not resource.background.snapshot().active
    fixture.provider.start.assert_not_awaited()
    resource.bot.add_listener.assert_not_called()
    await resource.stop()
    resource.bot.close.assert_awaited_once()
    await fixture.service.stop()


@pytest.mark.asyncio
async def test_result_view_modal_bounds_and_expiry():
    fixture = harness(config=SummaryConfig((Scope(100, 200),), result_capacity=2))
    controller = SummaryController(fixture.service)
    try:
        views = []
        for id in range(500, 503):
            request = interaction(message=id)
            await controller.execute(request, Query())
            views.append(request.followup.send.call_args.kwargs["view"])
        assert len(fixture.service._results) == len(controller._views) == 2
        assert views[0].is_finished()
        result = list(fixture.service._results.values())[-1]
        modals = []
        for _ in range(3):
            request = interaction(message=502)
            await controller.advanced(request, result.id)
            modals.append(request.response.send_modal.call_args.args[0])
        assert len(controller._modals) == 2 and modals[0].is_finished()
        fixture.clock.tick += 3601
        controller.prune()
        assert not fixture.service._results and not controller._views and not controller._modals
    finally:
        controller.close()
        await fixture.service.stop()


@pytest.mark.asyncio
async def test_maximal_embed_is_discord_valid_without_losing_overall(summary):
    maximum = Summary("x"*3000, tuple(Topic("x"*200, *(["x"*800]*6)) for _ in range(100)))
    maximum.validate()
    summary.provider.generate.return_value = maximum
    result = await summary.service.submit(100, 300, 200, Query())
    for page in range(4):
        embed = summary_embed(result, "x"*100, page)
        assert len(embed) <= 6000
        assert len(embed.fields) == 25
        assert maximum.overall in embed.description
