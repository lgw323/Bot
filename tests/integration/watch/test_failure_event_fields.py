"""Operational failure events export typed codes, never exception payloads."""
import json
from unittest.mock import AsyncMock

import pytest

from discordbot.platform.errors import DatabaseUnavailableError, ExternalTemporaryError
from discordbot.platform.diagnostics import safe_frame_location


def events_for(service, event):
    rows = [row for row in service.telemetry._buffer.drain() if row.event == event]
    assert rows
    encoded = json.dumps([row.as_dict() for row in rows])
    assert 'PRIVATE_SOURCE' not in encoded and '987654321' not in encoded
    return rows


def assert_safe_failure_fields(row, code, kind):
    fields = dict(row.fields)
    assert set(fields) == {'error_code','exception_type','stack_frames','trace_limited'}
    assert fields['error_code'] == code and fields['exception_type'] == kind
    assert fields['trace_limited'] is True  # AsyncMock/test traceback frames stay private.
    frames = fields['stack_frames']
    assert 1 <= len(frames) <= 5
    assert all(safe_frame_location(frame) == frame for frame in frames)
    assert any(frame.startswith('discordbot/watch/application/service.py:') for frame in frames)


@pytest.mark.asyncio
async def test_maintenance_failure_emits_typed_database_code(service, monkeypatch):
    monkeypatch.setattr(service.writer, 'heartbeat', AsyncMock(side_effect=DatabaseUnavailableError(
        'PRIVATE_SOURCE', context={'sql': 'PRIVATE_SOURCE', 'user_id': 987654321})))
    await service.sweep()
    rows = events_for(service, 'watch.maintenance')
    assert_safe_failure_fields(rows[0], 'database_unavailable', 'DatabaseUnavailableError')


@pytest.mark.asyncio
async def test_metadata_failure_emits_typed_provider_code(service, invite, monkeypatch):
    monkeypatch.setattr(service.metadata, 'title', AsyncMock(side_effect=ExternalTemporaryError('PRIVATE_SOURCE')))
    await service.add(invite.capability, 'https://youtu.be/aaaaaaaaaaa', 'synthetic')
    rows = events_for(service, 'watch.metadata')
    assert_safe_failure_fields(rows[0], 'external_temporary', 'ExternalTemporaryError')


@pytest.mark.asyncio
@pytest.mark.parametrize('error,result,code,kind', [
    (DatabaseUnavailableError('PRIVATE_SOURCE'), 'uncertain_close', 'database_unavailable', 'DatabaseUnavailableError'),
    (TimeoutError('PRIVATE_SOURCE'), 'deadline', 'deadline_exceeded', 'TimeoutError'),
])
async def test_shutdown_failure_retains_safe_cause(service, invite, monkeypatch, error, result, code, kind):
    actor = service.resolve(invite.capability)
    monkeypatch.setattr(actor, 'call', AsyncMock(side_effect=error))
    await service.stop()
    rows = events_for(service, 'watch.shutdown')
    assert rows[0].result == result
    assert_safe_failure_fields(rows[0], code, kind)
