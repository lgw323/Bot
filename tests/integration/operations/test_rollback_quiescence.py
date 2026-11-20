from pathlib import Path

import pytest

from discordbot.operations.adapters.deployment import Services
from discordbot.operations.application.deployment import Deployment
from discordbot.platform.errors import DataIntegrityError, ExternalTemporaryError
from .test_deployment import Fake
from .test_filesystem import symlinks_on_windows


class Runner:
    """Synthetic systemd only. No subprocess, host cgroup or production data."""

    def __init__(self, root, *, command_fails=False, remaining=False):
        self.root, self.command_fails, self.remaining = root, command_fails, remaining
        self.calls = []
        self.reads = 0
        self.raw = None
        self.race = False
        self.running = False
        self.finish_partial = False
        self.states = {name: dict(LoadState='loaded', ActiveState='failed', Result='exit-code',
            MainPID='0', ControlGroup='/system.slice/' + name + '.service') for name in Services.names}

    def run(self, args, cwd, timeout):
        assert args in (['systemctl', 'stop', *Services.names], ['systemctl', 'start', *Services.names])
        assert 0 < timeout <= 90
        self.calls.append(args[1])
        if args[1] == 'stop' and self.finish_partial:
            self.states['watch-web'].update(ActiveState='failed', MainPID='0', Result='exit-code')
            (self.root / 'system.slice/watch-web.service/cgroup.procs').write_bytes(b'')
        if args[1] == 'start':
            self.running = True
            for row in self.states.values():
                row.update(ActiveState='active', MainPID='123')
        elif self.running:
            self.running = False
            for row in self.states.values():
                row.update(ActiveState='failed', MainPID='0')
        if args[1] == 'stop' and self.remaining:
            self.states['watch-web'].update(ActiveState='active', MainPID='99')
        if args[1] == 'stop' and self.command_fails:
            raise ExternalTemporaryError('PRIVATE_COMMAND_CANARY')

    def read(self, args, cwd, timeout):
        assert args[:2] == ['systemctl', 'show'] and args[2] in self.states
        assert 0 < timeout <= 10
        name = args[2]
        if args[-1] == '--value':
            return self.states[name][args[3].removeprefix('--property=')]
        assert args[3] == '--property=LoadState,ActiveState,MainPID,ControlGroup'
        self.reads += 1
        if self.race and self.reads >= 3:
            self.states['discord-bot'].update(ActiveState='active', MainPID='100')
        if self.raw is not None:
            return self.raw
        row = self.states[name]
        return '\n'.join(k + '=' + row[k] for k in ['LoadState', 'ActiveState', 'MainPID', 'ControlGroup'])


@pytest.fixture
def pair(tmp_path):
    root = tmp_path / 'synthetic-cgroup-v2'
    root.mkdir()
    (root / 'cgroup.controllers').write_text('cpu memory\n')
    for name in Services.names:
        group = root / 'system.slice' / (name + '.service')
        group.mkdir(parents=True)
        (group / 'cgroup.procs').write_bytes(b'')
    runner = Runner(root)
    return root, runner, Services(runner, tmp_path, (19010, 19011), cgroup_root=root)


def test_unclean_stopped_pair_is_rejected_forward_but_proved_for_rollback(pair):
    root, runner, services = pair
    with pytest.raises(ExternalTemporaryError):
        services.stop()
    services.stop_for_rollback()
    assert runner.calls == ['stop', 'stop']
    assert runner.reads == 4
    assert all(row['Result'] == 'exit-code' for row in runner.states.values())


def test_nonzero_stop_result_still_requires_independent_quiescence(pair):
    root, runner, services = pair
    runner.command_fails = True
    services.stop_for_rollback()
    assert runner.reads == 4 and runner.calls == ['stop']


def test_nonzero_stop_with_partial_live_pair_blocks_recovery(pair):
    root, runner, services = pair
    runner.command_fails = runner.remaining = True
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


@pytest.mark.parametrize('field,value', [
    ('LoadState', 'not-found'), ('LoadState', 'masked'),
    ('ActiveState', 'active'), ('ActiveState', 'deactivating'),
    ('ActiveState', 'PRIVATE_STATE_CANARY'), ('MainPID', '9'), ('MainPID', ''),
    ('MainPID', '00'), ('MainPID', 'PRIVATE_PID_CANARY'),
    ('ControlGroup', '/system.slice/ssh.service'), ('ControlGroup', '/../PRIVATE_PATH_CANARY'),
])
def test_unknown_or_live_unit_metadata_fails_closed_without_leaking(pair, field, value):
    root, runner, services = pair
    runner.states['watch-web'][field] = value
    with pytest.raises(ExternalTemporaryError) as caught:
        services.stop_for_rollback()
    assert 'PRIVATE_' not in str(caught.value)


@pytest.mark.parametrize('raw', ['', 'LoadState=loaded',
    'LoadState=loaded\nActiveState=failed\nMainPID=0\nLoadState=loaded',
    'LoadState=loaded\nActiveState=failed\nMainPID=0\nControlGroup=\nUnexpected=x',
    'PRIVATE_RAW_CANARY' * 400, b'private'])
def test_missing_duplicate_extra_and_unbounded_metadata_fails_closed(pair, raw):
    root, runner, services = pair
    runner.raw = raw
    with pytest.raises(ExternalTemporaryError) as caught:
        services.stop_for_rollback()
    assert 'PRIVATE_' not in str(caught.value)


def test_state_change_after_cgroup_walk_is_rejected(pair):
    root, runner, services = pair
    runner.race = True
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()
    assert runner.reads == 3


@pytest.mark.parametrize('depth', [0, 1, 3])
def test_orphan_pid_in_any_descendant_blocks_recovery(pair, depth):
    root, runner, services = pair
    group = root / 'system.slice/watch-web.service'
    for n in range(depth):
        group /= 'child-' + str(n)
        group.mkdir()
        (group / 'cgroup.procs').write_bytes(b'')
    (group / 'cgroup.procs').write_text('71\n')
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


def test_empty_cgroup_including_descendants_is_proved(pair):
    root, runner, services = pair
    group = root / 'system.slice/watch-web.service/worker/finalizer'
    group.mkdir(parents=True)
    (group.parent / 'cgroup.procs').write_bytes(b'')
    (group / 'cgroup.procs').write_bytes(b'')
    services.stop_for_rollback()


def test_missing_proc_evidence_is_not_an_empty_group(pair):
    root, runner, services = pair
    (root / 'system.slice/watch-web.service/cgroup.procs').unlink()
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


def test_unreadable_proc_evidence_fails_closed_and_hides_os_path(pair, monkeypatch):
    root, runner, services = pair
    original = services.quiescence._regular
    def denied(path, maximum):
        if path.name == 'cgroup.procs':
            raise PermissionError('PRIVATE_OS_PATH_CANARY')
        return original(path, maximum)
    monkeypatch.setattr(services.quiescence, '_regular', denied)
    with pytest.raises(ExternalTemporaryError) as caught:
        services.stop_for_rollback()
    assert 'PRIVATE_' not in str(caught.value) and caught.value.__suppress_context__


def test_absent_cgroup_requires_readable_v2_root_and_stopped_unit(pair):
    root, runner, services = pair
    for name in Services.names:
        group = root / 'system.slice' / (name + '.service')
        (group / 'cgroup.procs').unlink()
        group.rmdir()
        runner.states[name]['ControlGroup'] = ''
    services.stop_for_rollback()
    (root / 'cgroup.controllers').unlink()
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


def test_symlinked_descendant_is_not_followed(pair, tmp_path):
    root, runner, services = pair
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'cgroup.procs').write_text('53\n')
    (root / 'system.slice/watch-web.service/escape').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()
    assert (outside / 'cgroup.procs').read_text() == '53\n'


def test_missing_expected_hierarchy_is_unknown_not_absence(pair):
    root, runner, services = pair
    for name in Services.names:
        group = root / 'system.slice' / (name + '.service')
        (group / 'cgroup.procs').unlink()
        group.rmdir()
        runner.states[name]['ControlGroup'] = ''
    (root / 'system.slice').rmdir()
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


def test_unreadable_expected_hierarchy_is_unknown_not_absence(pair, monkeypatch):
    import os
    root, runner, services = pair
    original = os.scandir
    def denied(path):
        if Path(path) == root / 'system.slice':
            raise PermissionError('PRIVATE_SLICE_CANARY')
        return original(path)
    monkeypatch.setattr(os, 'scandir', denied)
    with pytest.raises(ExternalTemporaryError) as caught:
        services.stop_for_rollback()
    assert 'PRIVATE_' not in str(caught.value)


def test_unit_path_as_a_file_is_unknown_not_absence(pair):
    root, runner, services = pair
    group = root / 'system.slice/watch-web.service'
    (group / 'cgroup.procs').unlink()
    group.rmdir()
    group.write_text('PRIVATE_NON_DIRECTORY_CANARY')
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


def test_deep_cgroup_tree_has_a_hard_bound(pair):
    root, runner, services = pair
    group = root / 'system.slice/watch-web.service'
    for n in range(17):
        group /= 'child'
        group.mkdir()
        (group / 'cgroup.procs').write_bytes(b'')
    with pytest.raises(ExternalTemporaryError):
        services.stop_for_rollback()


class RealStopPort(Fake):
    def __init__(self, services, *, incompatible=False, old_unready=False):
        super().__init__()
        self.services, self.incompatible, self.old_unready = services, incompatible, old_unready
        def probe(index, path):
            row = services.runner.states[services.names[index]]
            return {'ready': row['ActiveState'] == 'active', 'live': True,
                    'service': services.names[index], 'release': self.pointer.identity}
        self.services.probe = probe

    def stop(self):
        self.call('stop')
        self.services.stop()

    def stop_for_rollback(self):
        self.call('rollback_stop')
        self.services.stop_for_rollback()

    def start(self):
        self.call('start')
        self.services.start()

    def compatible(self, release):
        self.call('compatible:' + release.identity)
        if self.incompatible and release.identity == 'old':
            raise DataIntegrityError('synthetic incompatible previous release')

    def ready(self, release):
        self.call('ready:' + release.identity)
        if self.old_unready and release.identity == 'old':
            raise ExternalTemporaryError('synthetic previous readiness failure')
        self.services.ready(release.identity, timeout=0)


def test_original_failed_exit_regression_recovers_old_without_claiming_new_success(pair):
    root, runner, services = pair
    port = RealStopPort(services)
    result = Deployment(port).run('revision')
    assert (result.result, result.stage, result.rollback) == ('failed', 'stop', 'ok')
    assert port.pointer.identity == 'old' and not port.locked
    assert 'activate:new' not in port.calls
    assert port.calls.index('compatible:old') < port.calls.index('activate:old') < port.calls.index('start')
    assert 'ready:old' in port.calls and 'smoke:old' in port.calls
    assert runner.calls == ['stop', 'stop', 'start']


def test_original_nonzero_command_regression_recovers_only_after_proof(pair):
    root, runner, services = pair
    runner.command_fails = True
    result = Deployment(RealStopPort(services)).run('revision')
    assert (result.result, result.stage, result.rollback) == ('failed', 'stop', 'ok')
    assert runner.calls == ['stop', 'stop', 'start']


def test_partial_stop_can_recover_after_the_remaining_unit_is_proved_stopped(pair):
    root, runner, services = pair
    runner.states['discord-bot'].update(ActiveState='inactive', Result='success')
    runner.states['watch-web'].update(ActiveState='active', MainPID='91')
    (root / 'system.slice/watch-web.service/cgroup.procs').write_text('91\n')
    runner.finish_partial = runner.command_fails = True
    port = RealStopPort(services)
    result = Deployment(port).run('revision')
    assert (result.result, result.stage, result.rollback) == ('failed', 'stop', 'ok')
    assert 'ready:old' in port.calls and 'smoke:old' in port.calls
    assert runner.calls == ['stop', 'stop', 'start']


def test_partial_stop_with_live_process_never_starts_old_or_new(pair):
    root, runner, services = pair
    runner.remaining = True
    port = RealStopPort(services)
    result = Deployment(port).run('revision')
    assert result.rollback == 'failed_stop_unconfirmed'
    assert 'start' not in port.calls and 'activate:old' not in port.calls
    assert runner.calls == ['stop', 'stop', 'stop']


def test_incompatible_previous_data_is_never_activated_or_restored(pair):
    root, runner, services = pair
    port = RealStopPort(services, incompatible=True)
    result = Deployment(port).run('revision')
    assert result.result == 'failed' and result.rollback == 'failed'
    assert 'activate:old' not in port.calls and 'start' not in port.calls
    assert 'backup:old' not in port.calls


def test_previous_readiness_failure_is_not_recovery_success(pair):
    root, runner, services = pair
    port = RealStopPort(services, old_unready=True)
    result = Deployment(port).run('revision')
    assert result.result == 'failed' and result.rollback == 'failed'
    assert port.calls.count('activate:old') == port.calls.count('start') == 1
    assert 'smoke:old' not in port.calls
    assert runner.calls == ['stop', 'stop', 'start', 'stop']


def test_previous_identity_mismatch_is_not_recovery_success(pair):
    root, runner, services = pair
    port = RealStopPort(services)
    services.probe = lambda index, path: {'ready': True, 'service': services.names[index], 'release': 'wrong'}
    result = Deployment(port).run('revision')
    assert result.result == 'failed' and result.rollback == 'failed'
    assert port.calls.count('start') == 1 and 'smoke:old' not in port.calls
