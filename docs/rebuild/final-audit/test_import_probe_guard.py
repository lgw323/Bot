"""Focused source-runner rejection tests; never run an unguarded probe command."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import import_probe_guard as boundary

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('code', [
    "open('data/forbidden.db').read()",
    "open('.env').read()",
    "import socket; socket.create_connection(('192.0.2.1', 443))",
    "open('../not-owned-probe.txt', 'w').write('synthetic')",
    "import subprocess; subprocess.run(['unapproved'])",
])
def test_parent_denies_unreviewed_code_for_each_boundary(code):
    # Source runner must reject before process creation. All strings are synthetic.
    with pytest.raises(PermissionError, match='source regression denies unapproved child process'):
        subprocess.run([sys.executable, '-I', '-c', code], cwd=ROOT,
                       env={}, capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize('override', [
    {'cwd': ROOT / 'data'}, {'cwd': ROOT / '.env'}, {'shell': True},
    {'executable': sys.executable}, {'creationflags': 0}, {'stdin': subprocess.PIPE},
])
def test_parent_denies_launch_shape_changes(override):
    kwargs = dict(cwd=ROOT, env={}, capture_output=True, text=True, timeout=15)
    kwargs.update(override)
    with pytest.raises(PermissionError, match='import probe launch shape changed'):
        subprocess.run([sys.executable, '-I', '-c', boundary.reviewed_script(ROOT)], **kwargs)


@pytest.mark.parametrize('event,args', [
    ('open', (str(ROOT / 'data/forbidden.db'), 'r', 0)),
    ('open', (str(ROOT / '.env'), 'r', 0)),
    ('socket.getaddrinfo', ('example.invalid', 443, 0, 0, 0)),
    ('subprocess.Popen', ('unapproved', 'unapproved', str(ROOT), {})),
    ('os.system', ('unapproved',)),
])
def test_parent_audit_rejects_direct_events(event, args):
    with pytest.raises(PermissionError):
        sys.audit(event, *args)


def test_launch_token_is_not_available_to_later_calls():
    assert not boundary.approved_launch((sys.executable, [], str(ROOT), {}))


def test_original_test_bytes_and_guarded_child_receipt():
    assert boundary.reviewed_script(ROOT)
    assert len(boundary.LAUNCHES) == 1
    receipt = boundary.LAUNCHES[0]
    assert receipt['flags'] == ['-I', '-B', '-c']
    assert receipt['child_negative_events'] == 12
    assert set(receipt['environment_keys']) <= {
        'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE', 'TEMP', 'TMP', 'PYTHON_DOTENV_DISABLED'}
    assert list(Path(receipt['owned']).iterdir()) == []
