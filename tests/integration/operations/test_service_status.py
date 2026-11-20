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
    for key in ('backup', 'update', 'manual'):
        timer = f'discordbot-{key}.timer'
        worker = f'discordbot-{key}.service'
        result[timer] = dict(Id=timer, LoadState='loaded', ActiveState='active', SubState='waiting',
                             UnitFileState='enabled', LastTriggerUSec='Sat 2026-10-31 08:00:00 UTC',
                             NextElapseUSecRealtime='Sat 2026-10-31 12:00:00 UTC')
        result[worker].update(ActiveState='inactive', SubState='dead', Result='success',
            ExecMainStatus='0', ExecMainExitTimestamp='Sat 2026-10-31 08:00:34.293840 UTC')
    result['discordbot-manual.service'].update(Result='exec-condition')
    result['discordbot-manual.timer']['NextElapseUSecRealtime'] = ''
    result['discordbot-manual.timer']['next_epoch_us'] = str(int((NOW+timedelta(seconds=45)).timestamp())*1_000_000)
    return result


@pytest.fixture
def provider(monkeypatch):
    rows = units()
    monkeypatch.setattr(module, '_query_units', lambda: rows)
    async def health(port, path):
        assert port in (9010, 9011) and path == '/health/ready'
        return 200, dict(ready=True, service='discord-bot' if port == 9010 else 'watch-web', release=RELEASE)
    monkeypatch.setattr(module, '_health', health)
    return module.ReadOnlyServiceStatus(Executor(), now=lambda: NOW), rows


@pytest.mark.asyncio
async def test_current_inventory_distinguishes_runtime_readiness_process_and_timer_evidence(provider):
    status, _ = provider
    snapshot = await status.snapshot()
    assert module.validate_observations(snapshot) == snapshot
    rows = {row.key: row for row in snapshot}
    assert tuple(rows) == ('bot', 'watch', 'salary', 'astral', 'study', 'cloudflared', 'backup', 'update', 'manual')
    assert all(row.observed_at == NOW for row in snapshot)
    assert rows['bot'].version == rows['watch'].version == RELEASE
    for key in ('salary', 'astral', 'study', 'cloudflared'):
        assert rows[key].state == '실행 중' and rows[key].health == '미확인' and rows[key].version is None
        assert 'systemd' in rows[key].health_scope
    for key in ('backup', 'update', 'manual'):
        assert rows[key].state == '예약 대기' and rows[key].enabled is True
        assert rows[key].last_trigger == NOW.replace(hour=8, minute=0)
        assert rows[key].version is None
    assert '복원 무결성 증명은 별도' in rows['backup'].health_scope
    assert '정상 종료' in rows['backup'].recent_job and '정상 종료' in rows['update'].recent_job
    assert rows['backup'].next_run == rows['update'].next_run == NOW.replace(hour=12, minute=0)
    assert rows['manual'].next_run == NOW+timedelta(seconds=45)
    assert rows['manual'].recent_job == '처리할 요청 없음'


@pytest.mark.parametrize('state,sub,expected', [('failed', 'failed', '실패'), ('inactive', 'dead', '실행 중 아님'),
    ('activating', 'start', '실행 중 아님'), ('active', 'exited', '실행 중 아님'), ('unknown-secret', 'secret', '미확인')])
@pytest.mark.asyncio
async def test_process_state_does_not_promote_http_probe_to_process_health(provider, state, sub, expected):
    status, rows = provider
    rows['salary-meter.service'].update(ActiveState=state, SubState=sub)
    result = (await status.snapshot())[2]
    assert result.state == expected
    assert result.health == '미확인'  # Salary Meter has no readiness endpoint in this collector.


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
    assert [c.args for c in health.call_args_list] == [(9010, '/health/ready'), (9011, '/health/ready')]
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
    wall_us = int(NOW.timestamp())*1_000_000
    output = 'Id=study-static.service\nLoadState=loaded\n\nId=discordbot-manual.timer\nLoadState=loaded\n'
    run = Mock(side_effect=[SimpleNamespace(returncode=0, stdout=output),
                            SimpleNamespace(returncode=0, stdout=json.dumps([
                                {'unit': 'discordbot-manual.timer', 'next': wall_us}]))])
    monkeypatch.setattr(module.subprocess, 'run', run)
    rows = module._query_units()
    assert rows['study-static.service']['LoadState'] == 'loaded'
    assert rows['discordbot-manual.timer']['next_epoch_us'] == str(wall_us)
    show, timers = run.call_args_list
    assert show.args[0] == ['/usr/bin/systemctl', 'show', *module.UNITS,
                            '--property=' + ','.join(module.PROPERTIES), '--no-pager']
    assert timers.args[0] == ['/usr/bin/systemctl', 'list-timers', '--all', '--no-pager',
                              '--output=json', 'discordbot-backup.timer', 'discordbot-update.timer', 'discordbot-manual.timer']
    assert show.kwargs['timeout'] == 2
    assert timers.kwargs['timeout'] == 1
    for call in (show, timers):
        assert call.kwargs['stdin'] is subprocess.DEVNULL
        assert set(call.kwargs['env']) == {'PATH', 'LC_ALL', 'TZ'}
        assert not call.kwargs.get('shell', False)
    assert not any(p in module.PROPERTIES for p in ('Environment', 'ExecStart', 'User', 'Description'))


@pytest.mark.parametrize('text', ['', 'Id=study-static.service\nId=study-static.service', 'Id=ssh.service\nLoadState=loaded',
    'Id=study-static.service\nEnvironment=TOKEN=secret', 'Id=study-static.service\n\nId=study-static.service', 'x' * 16385])
def test_unexpected_or_ambiguous_systemctl_output_is_discarded(text):
    assert module._unit_rows(text) == {}


@pytest.mark.asyncio
async def test_backup_exit_not_a_restore_proof_missing_future_bad_timestamp(provider):
    status, units = provider
    worker = units['discordbot-backup.service']
    worker.update(Result='exit-code', ExecMainStatus='1')
    row = next(row for row in await status.snapshot() if row.key == 'backup')
    assert '실패 종료' in row.recent_job
    worker['ExecMainExitTimestamp'] = 'Sat 2099-01-01 00:00:00 UTC'
    units['discordbot-backup.timer']['NextElapseUSecRealtime'] = 'Fri 2026-10-30 12:00:00 UTC'
    row = next(row for row in await status.snapshot() if row.key == 'backup')
    assert row.recent_job == module.NO_JOB and row.next_run is None


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ('backup', 'update', 'manual'))
async def test_inactive_timer_does_not_advertise_next_run_or_unobserved_result(provider, key):
    status, units = provider
    units[f'discordbot-{key}.timer'].update(ActiveState='inactive', UnitFileState='disabled',
                                           LastTriggerUSec='Sat 2099-01-01 00:00:00 UTC')
    units[f'discordbot-{key}.service']['LoadState'] = 'not-found'
    row = next(row for row in await status.snapshot() if row.key == key)
    assert row.state == '실행 중 아님' and row.enabled is False
    assert row.next_run is None and row.last_trigger is None
    assert row.recent_job == module.NO_JOB


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
    assert await module._health(9010, '/health/ready') == (200, {'status': 'ok'})
    assert factory.call_args.kwargs['trust_env'] is False
    assert factory.call_args.kwargs['timeout'].total == 0.6
    assert get.call_args.args == ('http://127.0.0.1:9010/health/ready',)
    assert get.call_args.kwargs['allow_redirects'] is False
    assert session.closed and response.closed
    transport(monkeypatch, b'not followed', status=302)
    assert await module._health(9010, '/health/ready') == (302, {})


@pytest.mark.parametrize('body', [b'x' * 2049, b'{"ready":true,"ready":false}', b'[]', b'not json'])
@pytest.mark.asyncio
async def test_http_invalid_duplicate_and_oversize_data_not_a_valid_contract(monkeypatch, body):
    _, session, _, response = transport(monkeypatch, body)
    try:
        assert await module._health(9010, '/health/ready') == (200, {})
    except ValueError:
        pass  # caller maps JSON errors to unknown, never exports raw content
    assert session.closed and response.closed


@pytest.mark.asyncio
async def test_trickling_http_response_has_total_deadline_not_idle_timeout(monkeypatch):
    _, session, _, response = transport(monkeypatch, b'', trickle=True)
    start = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await module._health(9010, '/health/ready')
    assert asyncio.get_running_loop().time() - start < 1.5
    assert session.closed and response.closed
