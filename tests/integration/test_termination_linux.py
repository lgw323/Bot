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
    'internal-tree', 'escape', 'crash', 'close-error', 'parent-death', 'external-stop', 'repeated-stop'])
def test_real_guardian_worker_under_systemd(tmp_path, mode):
    unit = 'a2r2-' + uuid.uuid4().hex + '.service'
    sentinel = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(10)'])
    cgroup = None
    emergency = False
    try:
        # Even a broken guardian is contained by the external manager. Triggering
        # this safety deadline is a test failure, never remediation evidence.
        command('systemd-run', '--user', '--unit=' + unit, '--property=RuntimeMaxSec=5',
            '--property=TimeoutStopSec=1200ms', '--property=KillMode=control-group',
            '--property=RemainAfterExit=yes', sys.executable, '-I', '-B', str(DRIVER),
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
        if mode not in ('rollback', 'startup', 'internal-tree', 'escape', 'crash'):
            eventually(lambda: (tmp_path / 'armed.json').exists())
            if mode != 'blocked-loop':
                eventually(lambda: 'guardian.ready' in (tmp_path / 'events').read_text())
            if mode == 'parent-death':
                os.kill(guardian, signal.SIGKILL)
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
            clean = mode in ('clean', 'capacity', 'external-stop', 'repeated-stop')
            assert result == (0 if clean else 1), events
            if clean:
                assert 'guardian.clean' in events and 'guardian.escalation' not in events
                assert (tmp_path / 'resource-stopped.json').exists()
            elif mode not in ('crash', 'close-error', 'escape'):
                assert 'guardian.escalation' in events, events
            if mode == 'task':
                assert (tmp_path / 'resisted.json').exists()
                assert 'worker.application_timeout' in events
            if mode in ('task', 'asyncgen', 'default-executor', 'resource', 'rollback'):
                assert 'worker.loop_timeout' in events
            if mode == 'interpreter':
                assert (tmp_path / 'worker-returned.json').exists()
        # Stop also handles a deliberately setsid-escaped descendant and guardian
        # death: that last containment owner is systemd, not process-name matching.
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
