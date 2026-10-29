"""Operational failure events export typed codes, never exception payloads."""
import json
from unittest.mock import AsyncMock

import pytest

from discordbot.platform.errors import DatabaseUnavailableError, ExternalTemporaryError


def events_for(service, event):
    rows = [row for row in service.telemetry._buffer.drain() if row.event == event]
    assert rows
    assert 'PRIVATE_SOURCE' not in json.dumps([row.as_dict() for row in rows])
    return rows


@pytest.mark.asyncio
async def test_maintenance_failure_emits_typed_database_code(service, monkeypatch):
    monkeypatch.setattr(service.writer, 'heartbeat', AsyncMock(side_effect=DatabaseUnavailableError(
        'PRIVATE_SOURCE', context={'sql': 'PRIVATE_SOURCE', 'user_id': 987654321})))
    await service.sweep()
    rows = events_for(service, 'watch.maintenance')
    assert dict(rows[0].fields) == {'error_code': 'database_unavailable', 'exception_type': 'DatabaseUnavailableError'}


@pytest.mark.asyncio
async def test_metadata_failure_emits_typed_provider_code(service, invite, monkeypatch):
    monkeypatch.setattr(service.metadata, 'title', AsyncMock(side_effect=ExternalTemporaryError('PRIVATE_SOURCE')))
    await service.add(invite.capability, 'https://youtu.be/aaaaaaaaaaa', 'synthetic')
    rows = events_for(service, 'watch.metadata')
    assert dict(rows[0].fields) == {'error_code': 'external_temporary', 'exception_type': 'ExternalTemporaryError'}


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
    assert dict(rows[0].fields) == {'error_code': code, 'exception_type': kind}
