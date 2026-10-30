import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from discordbot.platform.errors import DeadlineExceededError, ExternalTemporaryError
from discordbot.platform.diagnostics import safe_frame_location
from discordbot.summary.adapters.gemini import GeminiProvider
from discordbot.summary.domain.models import Prompt, Query


def without_public_exception_evidence(fields, kind, source):
    """Retain the exact payload allowlist assertion while checking its new evidence."""
    remaining = dict(fields)
    assert remaining.pop('exception_type') == kind
    assert remaining.pop('trace_limited') is True  # AsyncMock/test frames stay private.
    frames = remaining.pop('stack_frames')
    assert 1 <= len(frames) <= 5
    assert all(safe_frame_location(frame) == frame for frame in frames)
    assert any(frame.startswith(source + ':') for frame in frames)
    return remaining


@pytest.mark.asyncio
@pytest.mark.parametrize('error,expected,reason', [
    (aiohttp.ClientConnectionError('private synthetic connection'), ExternalTemporaryError, 'transport_error'),
    (OSError('private synthetic I/O'), ExternalTemporaryError, 'transport_error'),
    (TimeoutError('private synthetic timeout'), DeadlineExceededError, 'timeout'),
])
async def test_transport_failure_category_without_payload_or_retry(error, expected, reason):
    session = SimpleNamespace(post=MagicMock(side_effect=error), close=AsyncMock())
    provider = GeminiProvider('SYNTHETIC', session=session)
    with pytest.raises(expected) as raised:
        await provider.generate(Prompt('synthetic', 'synthetic'), remaining=60)
    assert dict(raised.value.context) == {'reason': reason}
    assert 'private' not in str(raised.value)
    assert session.post.call_count == 1
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('context,expected', [
    ({'reason': 'http_server_error', 'http_status': 503, 'content': 'private synthetic content'},
     {'reason': 'http_server_error', 'http_status': 503}),
    ({'reason': 'private synthetic reason', 'http_status': 'private synthetic status'}, {}),
    ({'reason': 'transport_error', 'http_status': True, 'user_id': 987654321}, {'reason': 'transport_error'}),
])
async def test_request_telemetry_only_emits_allowlisted_failure_fields(summary, context, expected):
    summary.provider.generate.side_effect = ExternalTemporaryError('private synthetic payload', context=context)
    with pytest.raises(ExternalTemporaryError):
        await summary.service.submit(100, 300, 200, Query())
    events = [event for event in summary.buffer.drain() if event.event == 'summary.request']
    assert len(events) == 1 and events[0].result == 'external_temporary'
    remaining = without_public_exception_evidence(events[0].fields, 'ExternalTemporaryError',
        'discordbot/summary/application/service.py')
    assert remaining == {'duration_seconds': 0, 'queue_depth': 0, **expected}
    encoded = json.dumps(events[0].as_dict())
    assert 'private' not in encoded and '987654321' not in encoded
    summary.provider.generate.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('error,code,kind', [
    (ExternalTemporaryError('PRIVATE_SOURCE', context={'content': 'PRIVATE_SOURCE'}), 'external_temporary', 'ExternalTemporaryError'),
    (TimeoutError('PRIVATE_SOURCE'), 'deadline_exceeded', 'TimeoutError'),
    (type('PRIVATE_SOURCE', (ExternalTemporaryError,), {})('PRIVATE_SOURCE'), 'external_temporary', 'unexpected'),
])
async def test_preload_failure_has_typed_code_without_private_fields(summary, error, code, kind):
    from discordbot.summary.adapters.runtime import SummaryResource
    resource = SummaryResource(SimpleNamespace(), summary.config, summary.provider,
                               summary.clock, summary.service.telemetry)
    resource.history = SimpleNamespace(page=AsyncMock(side_effect=error))
    await resource._reconcile()
    events = summary.buffer.drain()
    assert len(events) == len(summary.config.sources)
    assert all(event.event == 'summary.preload' and event.result == 'failed' for event in events)
    assert all(without_public_exception_evidence(event.fields, kind,
        'discordbot/summary/adapters/runtime.py') == {'error_code': code} for event in events)
    assert 'PRIVATE_SOURCE' not in json.dumps([event.as_dict() for event in events])


@pytest.mark.asyncio
async def test_response_failure_has_boundary_code_without_exception_text(summary):
    from characterization.summary_support import interaction
    from discordbot.summary.adapters.discord_ui import SummaryController
    controller = SummaryController(summary.service)
    request = interaction()
    request.followup.send.side_effect = RuntimeError('PRIVATE_SOURCE')
    try:
        await controller.execute(request, Query())
        events = [event for event in summary.buffer.drain() if event.event == 'summary.response']
        assert len(events) == 1 and events[0].result == 'delivery_failed'
        assert dict(events[0].fields) == {'error_code': 'external_permanent'}
        assert 'PRIVATE_SOURCE' not in json.dumps(events[0].as_dict())
    finally:
        controller.close()
