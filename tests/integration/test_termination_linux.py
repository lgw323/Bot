"""Opt-in real Linux/systemd tests; no production units, credentials or network."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / 'tests/helpers/termination_driver.py'
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.environ.get('A2_LINUX_PROCESS_TESTS') != '1',
                               reason='explicit isolated Linux user-systemd environment required')


def command(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=6)


def eventually(predicate, bound=4):
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('external observation bound exceeded')


@pytest.mark.parametrize('mode', ['clean', 'capacity', 'task', 'thread', 'retained', 'default-executor',
    'interpreter', 'asyncgen', 'resource', 'rollback', 'startup', 'blocked-loop', 'tree',
    'internal-tree', 'escape', 'internal-restart', 'crash', 'worker-crash', 'asyncgen-error',
    'close-error', 'parent-death', 'external-stop', 'repeated-stop', 'optional-degraded', 'optional-resistant'])
def test_real_guardian_worker_under_systemd(tmp_path, mode):
    unit = 'a2r2-' + uuid.uuid4().hex + '.service'
    sentinel = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(10)'])
    cgroup = None
    emergency = False
    try:
        # Even a broken guardian is contained by the external manager. Triggering
        # this safety deadline is a test failure, never remediation evidence.
        restart = ['--property=Restart=on-failure', '--property=RestartSec=100ms',
                   '--property=StartLimitIntervalSec=10', '--property=StartLimitBurst=1'] if mode == 'internal-restart' else []
        command('systemd-run', '--user', '--unit=' + unit, '--property=RuntimeMaxSec=5',
            '--property=TimeoutStopSec=1200ms', '--property=KillMode=control-group',
            '--property=RemainAfterExit=yes', *restart, sys.executable, '-I', '-B', str(DRIVER),
            'guardian', mode, str(tmp_path))
        eventually(lambda: (tmp_path / 'worker.json').exists())
        worker = json.loads((tmp_path / 'worker.json').read_text())['pid']
        guardian = json.loads((tmp_path / 'guardian.json').read_text())['pid']
        props = dict(line.split('=', 1) for line in command('systemctl', '--user', 'show', unit,
            '--property=MainPID,ControlGroup,KillMode,KillSignal,SendSIGKILL').stdout.splitlines())
        assert int(props['MainPID']) == guardian
        assert props['KillMode'] == 'control-group' and props['KillSignal'] == '15' and props['SendSIGKILL'] == 'yes'
        cgroup = Path('/sys/fs/cgroup' + props['ControlGroup'])
        members = {int(v) for v in (cgroup / 'cgroup.procs').read_text().split()}
        assert {guardian, worker} <= members
        (tmp_path / 'go').touch()
        if mode not in ('rollback', 'startup', 'internal-tree', 'escape', 'internal-restart', 'crash', 'optional-resistant'):
            eventually(lambda: (tmp_path / 'armed.json').exists())
            if mode != 'blocked-loop':
                eventually(lambda: 'guardian.ready' in (tmp_path / 'events').read_text())
            if mode == 'parent-death':
                os.kill(guardian, signal.SIGKILL)
            elif mode == 'worker-crash':
                os.kill(worker, signal.SIGKILL)
            elif mode == 'external-stop':
                command('systemctl', '--user', 'stop', unit)
            else:
                os.kill(guardian, signal.SIGTERM)
                if mode == 'repeated-stop':
                    for _ in range(3):
                        try:
                            os.kill(guardian, signal.SIGTERM)
                        except ProcessLookupError:
                            break
                        time.sleep(.01)
        if mode == 'parent-death':
            eventually(lambda: not Path(f'/proc/{worker}').exists())
        else:
            eventually(lambda: (tmp_path / 'result.json').exists())
            result = json.loads((tmp_path / 'result.json').read_text())['code']
            events = (tmp_path / 'events').read_text().splitlines()
            clean = mode in ('clean', 'capacity', 'external-stop', 'repeated-stop', 'optional-degraded')
            assert result == (0 if clean else 1), events
            if clean:
                assert 'guardian.clean' in events and 'guardian.escalation' not in events
                assert (tmp_path / 'resource-stopped.json').exists()
                if mode == 'optional-degraded':
                    assert (tmp_path / 'degraded-ready.json').exists()
                    assert (tmp_path / 'optional-stopped.json').exists()
            elif mode == 'optional-resistant':
                assert 'guardian.escalation' in events
                assert not (tmp_path / 'resource-stopped.json').exists()
            elif mode not in ('crash', 'worker-crash', 'asyncgen-error', 'close-error', 'escape', 'internal-restart'):
                assert 'guardian.escalation' in events, events
            stamps = {row['name']: row['time'] for row in map(json.loads, (tmp_path / 'timings').read_text().splitlines())}
            if 'guardian.escalation' in stamps:
                assert .70 <= stamps['guardian.escalation'] - stamps['guardian.stopping'] <= 1.05
            if mode == 'task':
                assert (tmp_path / 'resisted.json').exists()
                assert 'worker.application_timeout' in events
            if mode in ('task', 'asyncgen', 'default-executor', 'resource', 'rollback'):
                assert 'worker.loop_timeout' in events
            if mode == 'interpreter':
                assert (tmp_path / 'worker-returned.json').exists()
            if mode == 'worker-crash':
                assert 'guardian.worker_crash' in events
            if mode == 'asyncgen-error':
                assert 'worker.failed' in events and 'guardian.clean' not in events
        if mode not in ('clean', 'capacity', 'external-stop', 'repeated-stop', 'optional-degraded'):
            # Prove automatic failure/deactivation cleanup BEFORE an explicit stop.
            eventually(lambda: not cgroup.exists())
        if mode == 'internal-restart':
            def restart_was_bounded():
                state = command('systemctl', '--user', 'show', unit,
                    '--property=NRestarts,ActiveState,MainPID', check=False).stdout
                return all(value in state for value in ('NRestarts=1', 'ActiveState=failed', 'MainPID=0'))
            eventually(restart_was_bounded)
            assert (tmp_path / 'events').read_text().splitlines().count('guardian.started') == 1
        command('systemctl', '--user', 'stop', unit, check=False)
        pids = [json.loads(file.read_text())['pid'] for file in tmp_path.glob('*.json')]
        eventually(lambda: all(not Path(f'/proc/{pid}').exists() for pid in pids))
        eventually(lambda: not cgroup.exists())
        assert sentinel.poll() is None
    except BaseException:
        emergency = True
        raise
    finally:
        command('systemctl', '--user', 'stop', unit, check=False)
        command('systemctl', '--user', 'reset-failed', unit, check=False)
        sentinel.terminate()
        sentinel.wait(timeout=2)
        # No persistent unit or process survives even assertion failures.
        eventually(lambda: 'LoadState=not-found' in command('systemctl', '--user', 'show', unit,
            '--property=LoadState', check=False).stdout)
        if not emergency and cgroup is not None:
            assert not cgroup.exists()
