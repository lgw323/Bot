"""Only reproduced, completely classified BUSY gets a bounded recovery window."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discordbot.operations.adapters.probe_policy import ProbePolicy, classified_busy
from discordbot.operations.adapters.probe import Probe
from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.runtime import ProcessRuntime
from discordbot.platform.errors import DatabaseUnavailableError
from .test_music_smoke_observer import observer


def busy():
    return dict(operation='select1_probe', stage='probe_configure', error_code='database_unavailable',
                exception_family='sqlite_operational', sqlite_errorcode=5, sqlite_family='busy',
                connection_opened=True, close_succeeded=True, cleanup_failed=False)


def test_one_busy_requires_two_healthy_probes_and_a_60_second_window():
    policy = ProbePolicy()
    assert policy.failure(busy(), 0, True) == 'bounded_busy'
    assert policy.success(5) == 'recovering'
    assert policy.success(10) == 'recovered'
    assert policy.failure(busy(), 60, True) == 'hard'
    assert policy.success(65) == 'hard'
    policy = ProbePolicy()
    assert policy.failure(busy(), 0, True) == 'bounded_busy'
    assert policy.success(5) == 'recovering'
    assert policy.success(10) == 'recovered'
    assert policy.failure(busy(), 61, True) == 'bounded_busy'


@pytest.mark.parametrize('change', [dict(sqlite_errorcode=6, sqlite_family='locked'),
    dict(sqlite_errorcode=261), dict(sqlite_errorcode=True), dict(stage='probe_close'),
    dict(stage='probe_execute'), dict(close_succeeded=False), dict(cleanup_failed=True),
    dict(connection_opened=False), dict(error_code='data_integrity'), dict(sqlite_family='io'),
    dict(exception_family='unexpected')])
def test_other_classes_never_get_transient_policy(change):
    fields = busy() | change
    policy = ProbePolicy()
    assert policy.failure(fields, 0, True) == 'hard'
    event = fields | dict(event='database.probe_contention', probe_disposition='bounded_busy')
    assert not observer().bounded_probe_busy(event)


def test_generic_repeated_stale_and_expired_are_hard():
    assert ProbePolicy().failure({}, 0, True) == 'hard'
    assert ProbePolicy().failure(busy(), 0, False) == 'hard'
    policy = ProbePolicy()
    assert policy.failure(busy(), 0, True) == 'bounded_busy'
    assert policy.failure(busy(), 5, True) == 'hard'
    policy = ProbePolicy()
    assert policy.failure(busy(), 0, True) == 'bounded_busy'
    assert policy.success(5) == 'recovering'
    assert policy.success(15) == 'recovery_expired'


@pytest.mark.asyncio
async def test_scheduled_probe_records_failure_and_two_successes_without_extra_requests(monkeypatch):
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'synthetic'))
    now = [0.]
    runtime.clock = SimpleNamespace(monotonic=lambda: now[0])
    factories = []
    runtime.supervisor = SimpleNamespace(start=lambda spec, factory: factories.append(factory) or
        asyncio.get_running_loop().create_future())
    database = SimpleNamespace(probe=AsyncMock(side_effect=DatabaseUnavailableError('private', context=busy())))
    probe = Probe(database, runtime)
    probe.database_ready = True
    probe.schedule()
    monkeypatch.setattr('discordbot.operations.adapters.probe.asyncio.sleep', AsyncMock())
    try:
        await factories[0]()
        assert probe.ready() and probe.policy.pending_since == 0
        database.probe.side_effect = None
        now[0] = 5
        await factories[0]()
        assert probe.policy.pending_since == 0
        now[0] = 10
        await factories[0]()
        assert probe.ready() and probe.policy.pending_since is None
        assert database.probe.await_count == 3
        events = runtime.telemetry_buffer.drain()
        assert [event.event for event in events] == ['database.probe_contention', 'database.probe_recovered']
        assert 'private' not in json.dumps([event.as_dict() for event in events])
        database.probe.side_effect = DatabaseUnavailableError('private', context=busy())
        now[0] = 20
        await factories[0]()
        assert not probe.ready()
        assert runtime.telemetry_buffer.drain()[0].event == 'database.probe_failed'
    finally:
        await runtime.executor.close(grace_seconds=1)


def test_observer_preserves_safe_fields_and_never_erases_a_hard_error(monkeypatch):
    module = observer()
    transient = busy() | dict(event='database.probe_contention', probe_disposition='bounded_busy', result='failed')
    private = transient | dict(path='private', sql='private', sqlite_errorname='private', stage_message='private')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0,
        stdout=json.dumps(dict(PRIORITY='6', MESSAGE=json.dumps(private)))))
    result = module.diagnostics(1)
    assert not result['error_codes'] and module.full_sweep_failures(result) == (None, [])
    assert 'private' not in json.dumps(result)
    assert result['recent_stages'][0] == transient
    result['error_codes']['database_unavailable'] = 1
    assert module.full_sweep_failures(result)[0] == 'database_unavailable'
    # A damaged/incomplete subtype never bypasses the generic HARD STOP.
    del transient['close_succeeded']
    assert module.full_sweep_failures({'recent_stages': [transient]})[0]


def test_pending_recovery_lost_readiness_is_immediately_hard():
    from .test_full_sweep_observer import healthy, RELEASE
    value = healthy()
    value['health']['9011'].update(ready=False, metrics={'database_probe_recovery_pending': 1})
    assert observer().health_trigger(value, healthy(), RELEASE, 1) == 'probe_recovery_readiness_lost'


def test_probe_field_allowlist_rejects_sensitive_shapes():
    from discordbot.storage.adapters.probe_diagnostics import safe_probe_fields
    value = safe_probe_fields(dict(stage=['private'], exception_family='private', sqlite_family='private',
        sqlite_errorcode='private', errno_category='private', connection_opened='private', secret='private'))
    assert value == {'operation': 'select1_probe'}


@pytest.mark.parametrize('code', ['deadline_exceeded', 'capacity', 'cancellation', 'internal', None])
def test_terminal_probe_failure_is_hard_even_without_umbrella_code(code):
    event = dict(event='database.probe_failed', result='failed', error_code=code)
    module = observer()
    assert module.full_sweep_failures({'recent_stages':[event]})[0] == 'database_probe_failed'
    # Hard evidence cannot disappear when a long journal tail drops the detail.
    assert module.full_sweep_failures({'event_counts':{'database.probe_failed':1}})[0] == 'database_probe_failed'


def test_full_observer_continues_exact_busy_but_stops_second_hard_event(tmp_path, monkeypatch):
    from .test_full_sweep_observer import healthy, RELEASE
    module = observer()
    clock, stops, results = [0.], [], []
    transient = busy() | dict(event='database.probe_contention', probe_disposition='bounded_busy', result='failed')
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda _: clock.__setitem__(0, clock[0] + 5))
    def diagnostic(_):
        if clock[0] < 10:
            return {'recent_stages':[transient], 'error_codes':{}}
        return {'recent_stages':[transient, {'event':'database.probe_failed', 'error_code':'database_unavailable'}],
                'error_codes':{'database_unavailable':1}}
    monkeypatch.setattr(module, 'diagnostics', diagnostic)
    monkeypatch.setattr(module, 'preserve_failure', lambda *a: stops.append(clock[0]) or {'pair_stopped':True})
    common = SimpleNamespace(METRICS=set(), sample=healthy, write_json=lambda path,data:results.append(data))
    safety = SimpleNamespace(identity=lambda _: {}, check=lambda *a:{'schema':5}, SAFE_FAILURES=set())
    args = SimpleNamespace(policy='full-sweep', since_unix=1, release=RELEASE, seconds=60)
    module.observe_loop(args, tmp_path, tmp_path, tmp_path/'preserved', common, safety, lambda _:True)
    assert stops == [10] and not results[-1]['soft_failures']
    assert results[-1]['last']['guard_trigger'] == 'database_unavailable'
