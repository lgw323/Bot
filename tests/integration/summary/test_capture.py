import asyncio
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from characterization.summary_support import Clock
from discordbot.summary.application.capture import Capture
from discordbot.summary.domain.models import Message, Scope, SummaryConfig
from discordbot.platform.errors import ValidationError


def msg(clock, id, *, scope=Scope(100, 200), **kwargs):
    return Message(scope, id, clock.now(), "synthetic", "body", **kwargs)


@pytest.mark.asyncio
async def test_preload_live_interleave_reconnect_cursor_no_gap_or_duplicate():
    clock = Clock()
    capture = Capture(SummaryConfig((Scope(100, 200),), page_size=2), clock)
    calls, entered, release = [], asyncio.Event(), asyncio.Event()

    async def page(scope, *, before, after, limit):
        calls.append(before)
        if before is None:
            entered.set()
            await release.wait()
            return (msg(clock, 4), msg(clock, 3))
        if before == 3:
            return (msg(clock, 2), msg(clock, 1))
        return ()

    history = SimpleNamespace(page=page)
    task = asyncio.create_task(capture.preload(Scope(100, 200), history))
    await entered.wait()
    capture.add(msg(clock, 5))
    capture.add(msg(clock, 4))
    await capture.preload(Scope(100, 200), history)  # in-flight ready is idempotent
    release.set()
    await task
    assert calls == [None, 3, 1]
    assert [m.id for m in capture.read(Scope(100, 200))] == [1, 2, 3, 4, 5]
    await capture.preload(Scope(100, 200), history)
    assert [m.id for m in capture.read(Scope(100, 200))] == [1, 2, 3, 4, 5]


def test_count_age_order_scope_and_first_observation_policy():
    clock = Clock()
    a, b = Scope(100, 200), Scope(101, 201)
    capture = Capture(SummaryConfig((a, b), max_messages=3), clock)
    for id in [5, 1, 4, 2, 3]:
        capture.add(msg(clock, id))
    capture.add(msg(clock, 1, scope=b))
    capture.add(replace(msg(clock, 5), content="edited event is not subscribed"))
    assert [(m.id, m.content) for m in capture.read(a)] == [(3, "body"), (4, "body"), (5, "body")]
    capture.add(replace(msg(clock, 100), created_at=clock.now()-timedelta(hours=25)))
    assert len(capture.read(a)) == 3  # age prune before count prune
    clock.tick += 86400
    assert len(capture.read(a)) == 3  # inclusive boundary
    clock.tick += 1
    assert capture.read(a) == capture.read(b) == ()


@pytest.mark.asyncio
async def test_disabled_and_invalid_capture_have_no_work():
    clock = Clock()
    source = Scope(100, 200)
    capture = Capture(SummaryConfig((source,), enabled=False), clock)
    history = SimpleNamespace(page=AsyncMock())
    capture.add(msg(clock, 1))
    await capture.preload(source, history)
    assert capture.read(source) == ()
    history.page.assert_not_awaited()
    enabled = Capture(SummaryConfig((source,)), clock)
    for message in (msg(clock, 1, bot=True), msg(clock, 2, scope=Scope(9, 9)),
                    replace(msg(clock, 3), content=""), replace(msg(clock, 4), content="x"*4001)):
        enabled.add(message)
    assert enabled.read(source) == ()


@pytest.mark.asyncio
async def test_preload_count_bound_survives_full_history_and_retry():
    clock = Clock()
    source = Scope(100, 200)
    capture = Capture(SummaryConfig((source,), max_messages=3, page_size=2), clock)
    history = SimpleNamespace(page=AsyncMock(side_effect=[(msg(clock, 10), msg(clock, 9)), (msg(clock, 8),)]))
    await capture.preload(source, history)
    assert [m.id for m in capture.read(source)] == [8, 9, 10]
    assert [call.kwargs["limit"] for call in history.page.call_args_list] == [2, 1]


@pytest.mark.asyncio
async def test_failed_preload_retries_without_cursor_hole_and_reconnect_uses_retention():
    clock = Clock()
    source = Scope(100, 200)
    capture = Capture(SummaryConfig((source,), page_size=2), clock)
    history = SimpleNamespace(page=AsyncMock(side_effect=[(msg(clock, 4), msg(clock, 3)), RuntimeError("synthetic")]))
    with pytest.raises(RuntimeError):
        await capture.preload(source, history)
    assert not capture.ready(source)
    history.page = AsyncMock(side_effect=[(msg(clock, 4), msg(clock, 3)), (msg(clock, 2), msg(clock, 1)), ()])
    await capture.preload(source, history)
    assert capture.ready(source)
    assert [m.id for m in capture.read(source)] == [1, 2, 3, 4]
    history.page = AsyncMock(return_value=())
    await capture.preload(source, history)
    assert history.page.call_args.kwargs["after"] == clock.now() - timedelta(hours=24)


@pytest.mark.parametrize("kwargs", [{"max_messages": 1001}, {"page_size": 101}, {"retention_hours": 169},
    {"result_capacity": 33}, {"enabled": "false"}, {"sources": [Scope(100, 200)]},
    {"sources": (Scope(100, 200), Scope(100, 201))}])
def test_configuration_bounds_are_explicit(kwargs):
    with pytest.raises(ValidationError):
        SummaryConfig(**({"sources": (Scope(100, 200),)} | kwargs))
