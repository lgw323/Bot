"""Unprivileged observations only; all OS and HTTP transports are fake."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import AsyncMock
import asyncio
import json
import subprocess

import pytest

from discordbot.operations.adapters import service_status as module

NOW = datetime(2026, 10, 31, 11, 15, tzinfo=timezone.utc)
RELEASE = 'r-' + 'a' * 16 + '-' + 'b' * 16


class Executor:
    async def run(self, fn):
        return fn()


def units():
    result = {s.unit: dict(Id=s.unit, LoadState='loaded', ActiveState='active', SubState='running')
              for s in module.SERVICES}
    result[module.TIMER] = dict(Id=module.TIMER, LoadState='loaded', ActiveState='active', SubState='waiting',
                               NextElapseUSecRealtime='Sat 2026-10-31 12:00:00 UTC')
    result['discordbot-backup.service'].update(ActiveState='inactive', SubState='dead', Result='success',
        ExecMainStatus='0', ExecMainExitTimestamp='Sat 2026-10-31 08:00:34.293840 UTC')
    return result


@pytest.fixture
def provider(monkeypatch):
    rows = units()
    monkeypatch.setattr(module, '_query_units', lambda: rows)
    async def health(port, path):
        if port in (9010, 9011):
            return 200, dict(ready=True, service='discord-bot' if port == 9010 else 'watch-web', release=RELEASE)
        return 200, {'status': 'ok'}
    monkeypatch.setattr(module, '_health', health)
    return module.ReadOnlyServiceStatus(Executor(), now=lambda: NOW), rows


@pytest.mark.asyncio
async def test_six_independent_scopes_versions_and_backup_evidence(provider):
    status, _ = provider
    rows = await status.snapshot()
    assert module.validate_observations(rows) == rows
    assert [r.key for r in rows] == ['bot', 'watch', 'supper', 'forme', 'cloudflared', 'backup']
    assert all(r.observed_at == NOW for r in rows)
    assert rows[0].version == rows[1].version == RELEASE
    assert all(r.version is None for r in rows[2:])
    assert '정적 HTTP' in rows[2].health_scope and '정적 HTTP' in rows[3].health_scope
    assert rows[4].health == '미확인' and '공개 경로' in rows[4].health_scope
    assert rows[5].state == '예약 대기' and '정상 종료' in rows[5].recent_job
    assert '복원 무결성 증명은 별도' in rows[5].health_scope
    assert rows[5].next_run == NOW.replace(hour=12, minute=0)


@pytest.mark.parametrize('state,sub,expected', [('failed', 'failed', '실패'), ('inactive', 'dead', '실행 중 아님'),
    ('activating', 'start', '실행 중 아님'), ('active', 'exited', '실행 중 아님'), ('unknown-secret', 'secret', '미확인')])
@pytest.mark.asyncio
async def test_process_state_does_not_promote_http_probe_to_process_health(provider, state, sub, expected):
    status, rows = provider
    rows['supper.service'].update(ActiveState=state, SubState=sub)
    result = (await status.snapshot())[2]
    assert result.state == expected
    assert result.health == '통과'  # independent HTTP evidence, not overall green


@pytest.mark.parametrize('error', [PermissionError('secret'), subprocess.TimeoutExpired('secret', 2),
                                  UnicodeError('secret')])
@pytest.mark.asyncio
async def test_unit_access_failure_never_leaks_error_or_reuses_previous_state(provider, monkeypatch, error):
    status, _ = provider
    assert (await status.snapshot())[0].state == '실행 중'
    monkeypatch.setattr(module, '_query_units', Mock(side_effect=error))
    rows = await status.snapshot()
    assert rows[0].state == '미확인' and rows[0].health == '통과'
    assert rows[4].observed_at is None and rows[4].state == '미확인'
    assert 'secret' not in repr(rows)


@pytest.mark.parametrize('code,body,expected', [(200, dict(ready=False, service='discord-bot', release=RELEASE), '미통과'),
    (503, dict(ready=False, service='discord-bot', release=RELEASE), '미통과'),
    (200, dict(ready=True, service='watch-web', release=RELEASE), '미확인'),
    (200, dict(ready=1, service='discord-bot', release=RELEASE), '미확인'),
    (200, dict(ready=True, service='discord-bot', release='private/user/token'), '미확인'),
    (302, {}, '미확인')])
@pytest.mark.asyncio
async def test_runtime_version_and_ready_contract_is_not_guesswork(provider, monkeypatch, code, body, expected):
    status, _ = provider
    monkeypatch.setattr(module, '_health', AsyncMock(return_value=(code, body)))
    result = (await status.snapshot())[0]
    assert result.health == expected
    assert result.version in (None, RELEASE)
    assert 'private/user/token' not in repr(result)


@pytest.mark.asyncio
async def test_http_timeout_gives_unknown_and_uses_fixed_loopback_paths(provider, monkeypatch):
    status, _ = provider
    health = AsyncMock(side_effect=TimeoutError('secret query'))
    monkeypatch.setattr(module, '_health', health)
    rows = await status.snapshot()
    assert [c.args for c in health.call_args_list] == [(9010, '/health/ready'), (9011, '/health/ready'),
                                                     (5080, '/api/health'), (5090, '/api/v1/health')]
    assert all(r.health == '미확인' for r in rows)
    assert 'secret' not in repr(rows)


@pytest.mark.parametrize('when', [None, datetime(2026, 10, 31), '2026-10-31'])
@pytest.mark.asyncio
async def test_clock_not_trusted_means_no_probe_or_fresh_claim(monkeypatch, when):
    query = Mock(side_effect=AssertionError('must not query'))
    monkeypatch.setattr(module, '_query_units', query)
    status = module.ReadOnlyServiceStatus(Executor(), now=lambda: when)
    rows = await status.snapshot()
    assert rows == module.unknown_observations() and module.validate_observations(rows) == rows
    query.assert_not_called()


@pytest.mark.parametrize('port', [0, 65536, True, '9010', 1.5])
def test_no_user_supplied_url_or_invalid_port(port):
    with pytest.raises(ValueError):
        module.ReadOnlyServiceStatus(Executor(), bot_port=port)


def test_systemd_command_is_readonly_fixed_allowlist_no_auth_or_environment(monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='Id=forme.service\nLoadState=loaded\n'))
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module._query_units()['forme.service']['LoadState'] == 'loaded'
    args, kwargs = run.call_args
    assert args[0] == ['/usr/bin/systemctl', 'show', *module.UNITS,
                       '--property=' + ','.join(module.PROPERTIES), '--no-pager']
    assert kwargs['timeout'] == 2 and kwargs['stdin'] is subprocess.DEVNULL
    assert set(kwargs['env']) == {'PATH', 'LC_ALL', 'TZ'}
    assert kwargs.get('shell', False) is False
    assert not any(p in module.PROPERTIES for p in ('Environment', 'ExecStart', 'User', 'Description'))


@pytest.mark.parametrize('text', ['', 'Id=forme.service\nId=forme.service', 'Id=ssh.service\nLoadState=loaded',
    'Id=forme.service\nEnvironment=TOKEN=secret', 'Id=forme.service\n\nId=forme.service', 'x' * 16385])
def test_unexpected_or_ambiguous_systemctl_output_is_discarded(text):
    assert module._unit_rows(text) == {}


@pytest.mark.asyncio
async def test_backup_exit_not_a_restore_proof_missing_future_bad_timestamp(provider):
    status, rows = provider
    rows['discordbot-backup.service'].update(Result='exit-code', ExecMainStatus='1')
    assert '실패 종료' in (await status.snapshot())[-1].recent_job
    rows['discordbot-backup.service']['ExecMainExitTimestamp'] = 'Sat 2099-01-01 00:00:00 UTC'
    rows[module.TIMER]['NextElapseUSecRealtime'] = 'Fri 2026-10-30 12:00:00 UTC'
    result = (await status.snapshot())[-1]
    assert result.recent_job == module.NO_JOB and result.next_run is None


@pytest.mark.asyncio
async def test_inactive_or_unloaded_timer_does_not_advertise_next_run(provider):
    status, rows = provider
    rows[module.TIMER]['ActiveState'] = 'inactive'
    assert (await status.snapshot())[-1].next_run is None
    assert (await status.snapshot())[-1].state == '실행 중 아님'
    rows['discordbot-backup.service']['LoadState'] = 'not-found'
    assert (await status.snapshot())[-1].recent_job == module.NO_JOB


@pytest.mark.parametrize('field,value', [('health_scope', 'secret user message'), ('label', '@everyone'),
    ('recent_job', 'TOKEN=secret'), ('version', 'secret'), ('version_provenance', 'GitHub main'),
    ('observed_at', datetime(2026, 10, 31)), ('next_run', NOW), ('state', 'healthy'),
    ('state', '실행 중'), ('health', '통과')])
def test_render_boundary_rejects_injected_provider_text(field, value):
    rows = module.unknown_observations()
    poisoned = (replace(rows[0], **{field: value}), *rows[1:])
    with pytest.raises(ValueError):
        module.validate_observations(poisoned)


class Context:
    def __init__(self, value):
        self.value = value
        self.closed = False

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        self.closed = True


def transport(monkeypatch, body, status=200, *, trickle=False):
    async def chunks(size):
        assert size == 2049
        if trickle:
            while True:
                await asyncio.sleep(0.02)
                yield b' '
        yield body
    response = Context(SimpleNamespace(status=status, content=SimpleNamespace(iter_chunked=chunks)))
    get = Mock(return_value=response)
    session = Context(SimpleNamespace(get=get))
    factory = Mock(return_value=session)
    monkeypatch.setattr(module.aiohttp, 'ClientSession', factory)
    return factory, session, get, response


@pytest.mark.asyncio
async def test_http_transport_no_proxy_or_redirect_and_bounded_json(monkeypatch):
    factory, session, get, response = transport(monkeypatch, b'{"status":"ok"}')
    assert await module._health(5080, '/api/health') == (200, {'status': 'ok'})
    assert factory.call_args.kwargs['trust_env'] is False
    assert factory.call_args.kwargs['timeout'].total == 0.6
    assert get.call_args.args == ('http://127.0.0.1:5080/api/health',)
    assert get.call_args.kwargs['allow_redirects'] is False
    assert session.closed and response.closed
    transport(monkeypatch, b'not followed', status=302)
    assert await module._health(5080, '/api/health') == (302, {})


@pytest.mark.parametrize('body', [b'x' * 2049, b'{"ready":true,"ready":false}', b'[]', b'not json'])
@pytest.mark.asyncio
async def test_http_invalid_duplicate_and_oversize_data_not_a_valid_contract(monkeypatch, body):
    _, session, _, response = transport(monkeypatch, body)
    try:
        assert await module._health(5080, '/api/health') == (200, {})
    except ValueError:
        pass  # caller maps JSON errors to unknown, never exports raw content
    assert session.closed and response.closed


@pytest.mark.asyncio
async def test_trickling_http_response_has_total_deadline_not_idle_timeout(monkeypatch):
    _, session, _, response = transport(monkeypatch, b'', trickle=True)
    start = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await module._health(5080, '/api/health')
    assert asyncio.get_running_loop().time() - start < 1.5
    assert session.closed and response.closed
