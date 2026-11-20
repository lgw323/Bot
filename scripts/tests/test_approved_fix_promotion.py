"""Operator-only transaction coverage, using synthetic state and no host commands."""

from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip('fcntl', reason='Linux operator transaction')
from deploy.tools import promote_approved_fix as promotion
from deploy.tools.prepare_approved_fix import known_imports, pytest_report


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    old, new = 'a' * 40, 'b' * 40
    job = object.__new__(promotion.Promotion)
    job.old, job.new, job.intent = old, new, tmp_path / 'intent.json'
    state = SimpleNamespace(active=old, approved=old, timers=True, fault=None, events=[], status=None)

    def event(name):
        state.events.append(name)
        if state.fault == name:
            raise RuntimeError(name)

    def timer_ctl(action, now, *timers):
        assert now == '--now' and timers == promotion.TIMERS
        state.timers = action == 'enable'
        event(action)

    def unit_property(unit, key):
        assert unit in promotion.TIMERS
        return {'UnitFileState': 'enabled' if state.timers else 'disabled',
                'ActiveState': 'active' if state.timers else 'inactive'}[key]

    def switch(mode, target, expected):
        assert mode == 'switch' and state.active == expected and not state.timers
        state.active = target
        event('switch_' + target[0])

    def set_source(target):
        assert state.active == target and not state.timers
        event('source_' + target[0])
        state.approved = target

    def mark(status, source, target):
        state.status = status

    monkeypatch.setattr(promotion, 'ctl', timer_ctl)
    monkeypatch.setattr(promotion, 'prop', unit_property)
    monkeypatch.setattr(promotion, 'current', lambda: state.active)
    monkeypatch.setattr(promotion, 'ref', lambda _: state.approved)
    monkeypatch.setattr(promotion, 'healthy', lambda *args: None)
    monkeypatch.setattr(promotion, 'lock', lambda _: nullcontext())
    monkeypatch.setattr(job, 'mark', mark)
    monkeypatch.setattr(job, 'prepared', lambda: event('prepared'))
    monkeypatch.setattr(job, 'idle', lambda: event('idle'))
    monkeypatch.setattr(job, 'stop', lambda **kwargs: event('stop'))
    monkeypatch.setattr(job, 'preserving_backup', lambda: event('backup'))
    monkeypatch.setattr(job, 'checkpoint', lambda: event('checkpoint'))
    monkeypatch.setattr(job, 'worker', switch)
    monkeypatch.setattr(job, 'restart', lambda target: event('restart_' + target[0]))
    monkeypatch.setattr(job, 'set_source', set_source)
    return job, state


def test_only_verified_candidate_is_armed_and_rollback_restores_both_pointers(rig):
    job, state = rig
    job.apply(rollback=False)
    assert (state.active, state.approved, state.timers) == (job.new, job.new, True)
    assert state.events.index('backup') < state.events.index('stop') < state.events.index('checkpoint')
    assert state.events.index('restart_b') < state.events.index('source_b') < state.events.index('enable')
    job.apply(rollback=True)
    assert (state.active, state.approved, state.timers) == (job.old, job.old, True)


def test_preserving_backup_failure_precedes_downtime(rig):
    job, state = rig
    state.fault = 'backup'
    with pytest.raises(RuntimeError, match='backup'):
        job.apply(rollback=False)
    assert 'stop' not in state.events
    assert (state.active, state.approved, state.timers) == (job.old, job.old, True)


@pytest.mark.parametrize('failure', ['switch_b', 'restart_b', 'source_b'])
def test_failure_after_switch_recovers_code_and_scheduler_source(rig, failure):
    job, state = rig
    state.fault = failure
    with pytest.raises(RuntimeError, match=failure):
        job.apply(rollback=False)
    assert state.events.count('checkpoint') == 2
    assert (state.active, state.approved, state.timers) == (job.old, job.old, True)


def test_unverified_recovery_leaves_scheduler_off(rig, monkeypatch):
    job, state = rig
    state.fault = 'restart_b'
    monkeypatch.setattr(job, 'set_source', lambda target: (_ for _ in ()).throw(RuntimeError('source_conflict')))
    with pytest.raises(RuntimeError, match='source_conflict'):
        job.apply(rollback=False)
    assert not state.timers and state.status == 'in_progress'


@pytest.mark.parametrize('marker', [None, 'native-verified.json', 'prepared.json', 'installed'])
def test_failed_worker_replacement_only_before_native_admission(tmp_path, monkeypatch, marker):
    job = object.__new__(promotion.Promotion)
    job.stage, job.receipt, job.gid, job.new = tmp_path, tmp_path/'prepared.json', 0, 'b' * 40
    job.bundle, job.old_bundle, job.new_bundle = tmp_path/'input.bundle', tmp_path/'old.bundle', tmp_path/'new.bundle'
    job.worker_file, job.staged_worker = tmp_path/'worker-source.py', tmp_path/'worker-destination.py'
    approved = tmp_path/'approved.bundle'
    for f in (approved, job.old_bundle, job.bundle, job.new_bundle):
        f.write_bytes(b'synthetic-source')
    job.worker_file.write_bytes(b'reviewed-worker')
    job.staged_worker.write_bytes(b'failed-worker')
    monkeypatch.setattr(promotion, 'APPROVED', approved)
    monkeypatch.setattr(promotion, 'ROOT', tmp_path)
    monkeypatch.setattr(promotion, 'trusted', lambda _: None)
    # A real atomic rename also keeps the earlier hard-linked inode intact.
    def write_atomic(path, contents, **_):
        pending = path.with_suffix('.new')
        pending.write_bytes(contents)
        pending.replace(path)
    monkeypatch.setattr(promotion, 'atomic', write_atomic)
    if marker:
        if marker == 'installed':
            (tmp_path / 'releases' / promotion.identity(job.new)).mkdir(parents=True)
        else:
            (tmp_path / marker).write_text('{}')
        with pytest.raises(RuntimeError, match='previous_inputs_differ'):
            job.save_inputs()
        assert job.staged_worker.read_bytes() == b'failed-worker'
    else:
        job.save_inputs()
        assert job.staged_worker.read_bytes() == b'reviewed-worker'
        assert [p.read_bytes() for p in tmp_path.glob('worker-before-*.py')] == [b'failed-worker']


def test_systemd_client_start_failure_reports_category_without_raw_output(monkeypatch):
    result = SimpleNamespace(returncode=1, stdout=b'', stderr=b'Failed to find executable /private/synthetic/path')
    monkeypatch.setattr(promotion.subprocess, 'run', Mock(return_value=result))
    with pytest.raises(promotion.HostFailure, match='executable_not_found') as value:
        promotion.cmd(['/usr/bin/systemd-run', '--unit=discordbot-promotion-' + '5' * 32], action='build')
    assert value.value.fields == {'exit_code': 1, 'component': 'systemd_manager', 'action': 'build',
                                  'unit': 'discordbot-promotion-' + '5' * 32}


def test_native_pytest_failure_projection_and_nested_delivery(tmp_path, monkeypatch):
    suite = tmp_path / 'native.xml'
    suite.write_text('''<testsuites><testsuite><testcase name="tests.integration.music.test_collection">
        <error message="collection failure">ModuleNotFoundError: No module named 'compatibility.v1'</error>
        </testcase></testsuite></testsuites>''')
    output = b'''FAILED tests/integration/operations/test_panel.py::TestView::test_rows[private-parameter] - AssertionError: private text
ERROR /some/private/test_other.py::test_does_not_belong
No module named 'sensitive.unapproved'
1 failed, 11 passed, 1 error, 2 warnings in 0.23s
'''
    details = pytest_report(output, suite, {'compatibility.v1'})
    assert details == {
        'failed_tests': ['tests/integration/operations/test_panel.py::TestView::test_rows',
                         'tests/integration/music/test_collection.py'],
        'missing_modules': ['compatibility.v1'], 'error_types': ['AssertionError', 'ModuleNotFoundError'],
        'pytest_counts': {'passed': 11, 'failed': 1, 'errors': 1, 'warnings': 2},
    }
    worker = b'native_tests ' + json.dumps(details).encode()
    monkeypatch.setattr(promotion.subprocess, 'run', Mock(return_value=SimpleNamespace(
        returncode=1, stdout=worker, stderr=b'worker_error native_tests_failed')))
    with pytest.raises(promotion.HostFailure, match='native_tests_failed') as failure:
        promotion.cmd(['/usr/bin/systemd-run'], action='test')
    assert all(failure.value.fields[k] == v for k, v in details.items())
    assert 'private' not in json.dumps(failure.value.fields)


def test_native_module_names_must_be_in_reviewed_code_or_pins(tmp_path):
    for directory in ('src', 'deploy', 'tests'):
        (tmp_path / directory).mkdir()
    (tmp_path / 'tests/test_x.py').write_text('from compatibility.v1.example import Magic\nimport discord.abc\n')
    (tmp_path / 'deploy/dependencies.pins').write_text('yt-dlp==2026.8.19\n')
    admitted = known_imports(tmp_path)
    assert {'compatibility', 'compatibility.v1', 'compatibility.v1.example', 'yt_dlp', 'discord.abc'} <= admitted
    assert 'private_name' not in admitted


def test_native_worker_report_rejects_unexpected_shapes():
    raw = json.dumps({'failed_tests': ['/private/data'], 'error_types': ['secret exception'],
        'missing_modules': ['../private'], 'pytest_counts': {'passed': True}, 'log': 'private'}).encode()
    assert promotion.test_details(raw) == {}
