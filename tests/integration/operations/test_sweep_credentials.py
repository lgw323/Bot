"""Credential metadata only: never open real credentials, services or networks."""
import importlib.util
from pathlib import Path
import stat
import struct
from types import SimpleNamespace
import sys

import pytest


def safety():
    path = Path(__file__).resolve().parents[3] / 'deploy/production/sweep-safety.py'
    spec = importlib.util.spec_from_file_location('sweep_credential_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def acl(uid=999, group=0, other=0, mask=4, named=4):
    entries = [(1, 4, 0xffffffff), (2, named, uid), (4, group, 0xffffffff),
               (16, mask, 0xffffffff), (32, other, 0xffffffff)]
    return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *e) for e in entries)


@pytest.fixture
def metadata(monkeypatch):
    module = safety()
    state = SimpleNamespace(mode=stat.S_IFREG | 0o440, owner=0, acl=acl(), readonly=True,
                            linked=False, names={'synthetic'}, closed=[], opened=[], acl_error=False)
    def info():
        return SimpleNamespace(st_mode=state.mode, st_uid=state.owner)
    entry = SimpleNamespace(name='synthetic', is_file=lambda: stat.S_ISREG(state.mode),
                            is_symlink=lambda: state.linked, stat=info, lstat=info)
    directory = SimpleNamespace(iterdir=lambda: [entry] if state.names else [],
                                is_symlink=lambda: False, is_dir=lambda: True)
    def opened(path, flags):
        if state.linked:
            raise OSError('synthetic linked path')
        state.opened.append(flags)
        return 7
    def get_acl(fd, name):
        assert fd == 7 and name == 'system.posix_acl_access'
        if state.acl_error:
            raise OSError('synthetic missing ACL')
        return state.acl
    monkeypatch.setattr(module, 'os', SimpleNamespace(
        O_RDONLY=0, O_NOFOLLOW=1, O_NONBLOCK=2, O_CLOEXEC=4, ST_RDONLY=1,
        open=opened, close=state.closed.append, fstat=lambda fd: info(), getxattr=get_acl,
        statvfs=lambda path: SimpleNamespace(f_flag=int(state.readonly)),
        fstatvfs=lambda fd: SimpleNamespace(f_flag=int(state.readonly))))
    return module, directory, state


def test_service_only_systemd_acl_is_accepted_by_full_sweep(metadata):
    module, directory, state = metadata
    module.check_credentials(directory, {'synthetic'}, 999)
    assert state.closed == [7]
    assert state.opened == [7]  # nofollow + nonblock + cloexec; content is never read


@pytest.mark.parametrize('change', ['wrong_uid', 'group_reader', 'other_reader', 'writer_mask',
    'named_writer', 'extra_reader', 'malformed', 'missing', 'acl_error', 'wrong_owner',
    'writable_acl', 'symlink', 'directory', 'fifo', 'writable_mount'])
def test_unsafe_credentials_remain_hard_failures(metadata, change):
    module, directory, state = metadata
    if change == 'wrong_uid': state.acl = acl(uid=998)
    if change == 'group_reader': state.acl = acl(group=4)
    if change == 'other_reader': state.acl = acl(other=4)
    if change == 'writer_mask': state.acl = acl(mask=6)
    if change == 'named_writer': state.acl = acl(named=6)
    if change == 'extra_reader': state.acl += struct.pack('<HHI', 2, 4, 998)
    if change == 'malformed': state.acl = b'invalid'
    if change == 'missing': state.acl = None
    if change == 'acl_error': state.acl_error = True
    if change == 'wrong_owner': state.owner = 998
    if change == 'writable_acl': state.mode = stat.S_IFREG | 0o640
    if change == 'symlink': state.linked = True
    if change == 'directory': state.mode = stat.S_IFDIR | 0o400
    if change == 'fifo': state.mode = stat.S_IFIFO | 0o400
    if change == 'writable_mount': state.readonly = False
    with pytest.raises(RuntimeError, match='^credential_permission$'):
        module.check_credentials(directory, {'synthetic'}, 999)
    assert len(state.closed) == len(state.opened)


@pytest.mark.parametrize('mode,owner', [(0o400, 0), (0o600, 999)])
def test_private_regular_credentials_on_readonly_mount_remain_accepted(metadata, mode, owner):
    module, directory, state = metadata
    state.mode, state.owner = stat.S_IFREG | mode, owner
    module.check_credentials(directory, {'synthetic'}, 999)
    assert state.closed == [7]


def test_unexpected_credential_scope_is_never_accepted(metadata):
    module, directory, state = metadata
    with pytest.raises(RuntimeError, match='^credential_scope$'):
        module.check_credentials(directory, {'different'}, 999)
    assert state.opened == []


@pytest.mark.parametrize('actual_uid', [999, 998, 0])
def test_acl_is_bound_to_configured_service_account_not_observer_root(monkeypatch, actual_uid):
    module = safety()
    def account(name):
        assert name == 'discordbot'
        return SimpleNamespace(pw_uid=999)
    monkeypatch.setitem(sys.modules, 'pwd', SimpleNamespace(getpwnam=account))
    class Process:
        def __truediv__(self, part):
            return self
        def stat(self):
            return SimpleNamespace(st_uid=actual_uid)
    monkeypatch.setattr(module, 'Path', lambda _: Process())
    if actual_uid == 999:
        assert module.credential_service_uid(123) == 999
    else:
        with pytest.raises(RuntimeError, match='^credential_permission$'):
            module.credential_service_uid(123)


@pytest.mark.parametrize('unsafe', [False, True])
def test_real_acl_validator_keeps_observer_running_or_hard_stops(metadata, tmp_path, monkeypatch, unsafe):
    from .test_music_smoke_observer import observer
    from .test_full_sweep_observer import healthy, RELEASE
    module, directory, state = metadata
    if unsafe:
        state.acl = acl(other=4)
    guard = observer()
    clock, stops, summaries = [0.], [], []
    monkeypatch.setattr(guard.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(guard.time, 'sleep', lambda _: clock.__setitem__(0, clock[0] + 5))
    monkeypatch.setattr(guard, 'diagnostics', lambda _: {'recent_stages': [
        {'event': 'summary.request', 'result': 'external_temporary', 'http_status': 503}]})
    monkeypatch.setattr(guard, 'preserve_failure', lambda *a: stops.append(clock[0]) or {'pair_stopped': True})
    def check(*args):
        module.check_credentials(directory, {'synthetic'}, 999)
        return {'credential_scope': 'verified'}
    checker = SimpleNamespace(identity=lambda _: {}, check=check, SAFE_FAILURES=module.SAFE_FAILURES)
    common = SimpleNamespace(METRICS=set(), sample=healthy, write_json=lambda p, v: summaries.append(v))
    args = SimpleNamespace(policy='full-sweep', since_unix=1, release=RELEASE, seconds=12)
    guard.observe_loop(args, tmp_path, tmp_path, tmp_path / 'preserved', common, checker, lambda _: True)
    assert stops == ([0] if unsafe else [15])
    final = summaries[-1]
    assert final['last']['guard_trigger'] == ('safety_invariant_failed' if unsafe else 'sweep_finished_or_deadline')
    if unsafe:
        assert final['last']['safety']['reason'] == 'credential_permission'
    else:
        assert final['last']['health']['9011']['ready']
        assert final['soft_failures'][0]['http_status'] == 503
