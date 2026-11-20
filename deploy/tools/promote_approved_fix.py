"""Build and switch approved code-only Discord releases under the installed wheel lock."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from uuid import uuid4


OLD = '22d53d291706d07e6e5f0d5b610b974123ee49cd'
WHEEL = 'bd1ffa96253a4d84b8f229cee226699c54fd3f50ca74b82fa3255adb29093bac'
ROOT = Path('/opt/discordbot')
BASE = Path('/opt/discordbot-approved-promotions')
STATE = Path('/var/lib/discordbot/state')
CONFIG = Path('/etc/discordbot')
APPROVED = CONFIG / 'approved-source.bundle'
OPLOCK = Path('/var/lib/discordbot/operations.lock')
PAIR = ('discord-bot.service', 'watch-web.service')
JOBS = ('discordbot-backup', 'discordbot-update', 'discordbot-manual')
TIMERS = tuple(job + '.timer' for job in JOBS)


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def identity(commit: str) -> str:
    return 'r-' + commit[:16] + '-' + WHEEL[:16]


def emit(stage: str, **fields) -> None:
    print(json.dumps({'stage': stage, **fields}), flush=True)


class HostFailure(RuntimeError):
    def __init__(self, reason: str, fields: dict):
        super().__init__(reason)
        self.fields = fields


def test_details(raw: bytes) -> dict:
    if len(raw) > 8192:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    names = {'AssertionError', 'ImportError', 'ModuleNotFoundError', 'PermissionError', 'FileNotFoundError',
             'OSError', 'RuntimeError', 'TypeError', 'ValueError', 'AttributeError', 'KeyError', 'TimeoutError',
             'ConnectionError', 'CalledProcessError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'OperationalError',
             'DataIntegrityError', 'ExternalTemporaryError', 'Failed'}
    fields = {}
    node = r'tests/integration/(?:music|operations)/test_[a-zA-Z0-9_]{1,96}\.py(?:::[a-zA-Z][a-zA-Z0-9_]{0,95}){0,2}'
    module = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
    for key, limit, valid in (('failed_tests', 16, lambda s: re.fullmatch(node, s)),
                              ('error_types', 8, lambda s: s in names),
                              ('missing_modules', 8, lambda s: len(s) <= 96 and re.fullmatch(module, s))):
        items = value.get(key)
        if type(items) is list and len(items) <= limit and all(type(s) is str and valid(s) for s in items):
            fields[key] = items
    counts = value.get('pytest_counts')
    if type(counts) is dict and set(counts) <= {'passed','failed','errors','skipped','xfailed','xpassed','deselected','warnings'}:
        if all(type(n) is int and 0 <= n <= 10000 for n in counts.values()):
            fields['pytest_counts'] = counts
    return fields


def cmd(args: list[str], timeout: int = 60, *, action: str | None = None) -> str:
    result = subprocess.run(args, capture_output=True, check=False, timeout=timeout,
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': '/nonexistent'})
    if result.returncode:
        output = result.stdout + b'\n' + result.stderr
        manager = args[0] == '/usr/bin/systemd-run'
        reason = Path(args[0]).name.replace('-', '_') + '_failed'
        fields = {'exit_code': result.returncode, 'component': 'systemd_manager' if manager else 'service_manager'}
        if action:
            fields['action'] = action
        for value in args:
            if re.fullmatch('--unit=discordbot-promotion-[0-9a-f]{32}', value):
                fields['unit'] = value[7:]
        folded = output.lower()
        for needle, code in ((b'failed to find executable', 'executable_not_found'),
                (b'failed to set up mount namespacing', 'mount_namespace_failed'),
                (b'failed to set unit properties', 'unit_property_rejected'),
                (b'failed to parse', 'invalid_property'), (b'read-only file system', 'read_only'),
                (b'permission denied', 'permission_denied'), (b'no space left', 'disk_full'),
                (b'no such file or directory', 'missing_path')):
            if needle in folded:
                reason = code
                break
        for key in ('TemporaryFileSystem', 'BindPaths', 'BindReadOnlyPaths', 'ReadWritePaths', 'InaccessiblePaths',
                    'PrivateNetwork', 'PrivateTmp', 'ProtectSystem', 'LoadCredential', 'RuntimeMaxSec'):
            if key.encode() in output:
                fields['property'] = key
                break
        for line in output.splitlines():
            if re.fullmatch(rb'worker_error [A-Za-z_]{1,70}', line):
                reason = line.split()[1].decode('ascii')
                fields['component'] = 'native_worker'
            elif action == 'test' and line.startswith(b'native_tests '):
                fields.update(test_details(line.removeprefix(b'native_tests ')))
        raise HostFailure(reason, fields)
    return result.stdout.decode('utf8').strip()


def ctl(*args: str, timeout: int = 60) -> str:
    return cmd(['/usr/bin/systemctl', '--no-pager', *args], timeout)


def prop(unit: str, name: str) -> str:
    return ctl('show', unit, '--property=' + name, '--value')


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def trusted(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    need(path.is_absolute() and path.resolve(strict=True) == path and info.st_uid == 0
         and not info.st_mode & 0o022 and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)),
         'untrusted_operator_path')
    for parent in path.parents:
        meta = parent.lstat()
        need(meta.st_uid == 0 and (not meta.st_mode & 0o022 or bool(meta.st_mode & stat.S_ISVTX)), 'untrusted_parent')


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def deploy_directory(name: str | Path, uid: int, gid: int, *, parent: int | None = None):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        meta = os.fstat(fd)
        need((meta.st_uid, meta.st_gid) == (uid, gid) and not meta.st_mode & 0o022,
             'untrusted_release_directory')
        yield fd
    finally:
        os.close(fd)


def sealed_manifest_hash(directory: int, uid: int, gid: int) -> str:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open('manifest.json', flags, dir_fd=directory), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        need(stat.S_ISREG(meta.st_mode) and (meta.st_uid, meta.st_gid) == (uid, gid)
             and not meta.st_mode & 0o222 and 0 < meta.st_size <= 4 * 1024**2, 'untrusted_release_manifest')
        payload = stream.read(4 * 1024**2 + 1)
        need(len(payload) == meta.st_size, 'release_manifest_changed')
        return hashlib.sha256(payload).hexdigest()


def install_candidate(source: int, destination: int, name: str, manifest: str, uid: int, gid: int) -> None:
    # Both fds are in the host mount namespace. Two systemd ReadWritePaths
    # mounts can have the same st_dev and still reject a rename with EXDEV.
    need(re.fullmatch('r-[0-9a-f]{16}-[0-9a-f]{16}', name) is not None, 'invalid_release_name')
    with deploy_directory(name, uid, gid, parent=source) as candidate:
        inode = os.fstat(candidate)
        need(not inode.st_mode & 0o222 and sealed_manifest_hash(candidate, uid, gid) == manifest,
             'staged_manifest_changed')
        need(os.fstat(source).st_dev == os.fstat(destination).st_dev, 'non_atomic_install_volume')
        with os.scandir(destination) as entries:
            need(sum(item.is_dir(follow_symlinks=False) for item in entries) < 16, 'release_count_cap')
        encoded = os.fsencode(name)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(source, encoded, destination, encoded, 1):  # RENAME_NOREPLACE
            raise OSError(ctypes.get_errno(), 'candidate_rename_failed')
        after = os.stat(name, dir_fd=destination, follow_symlinks=False)
        need(os.path.samestat(inode, after), 'installed_candidate_changed')
        os.fsync(source)
        os.fsync(destination)


def atomic(path: Path, data: bytes, *, mode: int, gid: int = 0) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fchown(handle.fileno(), 0, gid)
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
            os.replace(temp, path)
            sync_dir(path.parent)
        finally:
            temp.unlink(missing_ok=True)


def current() -> str:
    target = (ROOT / 'current').resolve(strict=True)
    need(target.parent == ROOT / 'releases', 'unexpected_active_directory')
    manifest = json.loads((target / 'manifest.json').read_bytes())
    commit = manifest['commit']
    need(re.fullmatch('[0-9a-f]{40}', commit) is not None and manifest['dependency_hash'] == WHEEL
         and target.name == manifest['release'] == identity(commit), 'unexpected_active_manifest')
    return commit


def ref(bundle: Path) -> str:
    trusted(bundle)
    need(0 < bundle.stat().st_size < 128 * 1024**2, 'unexpected_bundle_size')
    raw = cmd(['/usr/bin/git', '-C', '/', '-c', 'core.hooksPath=/dev/null', 'bundle', 'list-heads', str(bundle)])
    match = re.fullmatch('([0-9a-f]{40}) refs/heads/approved', raw)
    need(match is not None, 'unexpected_approved_branch')
    return match[1]


@contextmanager
def lock(path: Path, *, create: bool = False):
    flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b') as stream:
        meta = os.fstat(stream.fileno())
        need(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, 'invalid_lock_inode')
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def healthy(commit: str, seconds: int = 60) -> None:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + seconds
    while True:
        try:
            for unit, port in zip(PAIR, (9010, 9011)):
                service = unit.removesuffix('.service')
                for flag in ('live', 'ready'):
                    with opener.open(f'http://127.0.0.1:{port}/health/{flag}', timeout=3) as result:
                        row = json.loads(result.read(8193))
                    need(row.get(flag) is True and row.get('release') == identity(commit)
                         and row.get('service') == service, 'pair_not_ready')
            return
        except (OSError, ValueError, RuntimeError):
            if time.monotonic() >= deadline:
                raise RuntimeError('pair_not_ready') from None
            time.sleep(1)


class Promotion:
    def __init__(self, previous: str, commit: str, bundle: Path, sha: str):
        self.old, self.new, self.bundle, self.sha = previous, commit, bundle, sha
        self.stage = BASE / commit
        self.worker_file = Path(__file__).resolve().with_name('prepare_approved_fix.py')
        self.uid = pwd.getpwnam('discordbot-deploy').pw_uid
        self.gid = grp.getgrnam('discordbot').gr_gid
        self.old_bundle = self.stage / 'previous.bundle'
        self.new_bundle = self.stage / 'candidate.bundle'
        self.staged_worker = self.stage / self.worker_file.name
        self.receipt = self.stage / 'prepared.json'
        self.intent = self.stage / 'transaction.json'
        self.build_stage: Path | None = None

    def worker(self, action: str, commit: str, argument: str | None = None) -> None:
        old_root = ROOT / 'releases' / identity(self.old)
        user = 'discordbot' if action == 'checkpoint' else 'discordbot-deploy'
        props = [f'User={user}', 'Group=discordbot', 'NoNewPrivileges=yes', 'ProtectSystem=strict',
                 'ProtectHome=yes', 'PrivateNetwork=yes', 'PrivateTmp=yes', 'KillMode=control-group',
                 'UMask=0077', 'RuntimeMaxSec=1800', 'TimeoutStopSec=15',
                 'InaccessiblePaths=-/run/dbus/system_bus_socket -/run/systemd/private -/etc/discordbot/secrets -/etc/discordbot/backup-ssh']
        interpreter = old_root / '.venv/bin/python'
        if action in ('build', 'test', 'publish'):
            need(self.build_stage is not None, 'missing_build_stage')
            alias = Path('/run/discordbot-promotion-base')
            bind = 'BindReadOnlyPaths' if action == 'test' else 'BindPaths'
            props.extend(['TemporaryFileSystem=/opt/discordbot',
                          f'{bind}={self.build_stage}/releases:{ROOT}/releases {self.build_stage}/candidates:{ROOT}/candidates',
                          f'BindReadOnlyPaths={old_root}:{alias}',
                          'InaccessiblePaths=/etc/discordbot /var/lib/discordbot/data /var/lib/discordbot/backups /var/lib/discordbot/state /var/lib/discordbot/audit /var/lib/discordbot/source'])
            if action != 'test':
                props.append('ReadWritePaths=/opt/discordbot/releases /opt/discordbot/candidates')
            interpreter = alias / '.venv/bin/python'
        elif action == 'checkpoint':
            props.extend(['LoadCredential=db_key:/etc/discordbot/secrets/db_key',
                          f'ReadWritePaths={argument}', 'InaccessiblePaths=/var/lib/discordbot/backups'])
        elif action == 'switch':
            props.append(f'ReadWritePaths={ROOT}')
        argv = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
                '--unit=discordbot-promotion-' + uuid4().hex]
        for p in props:
            argv.extend(['--property', p])
        # systemd-run resolves argv[0] in the caller's namespace before unit
        # creation. The interpreter alias itself exists only in the new namespace.
        argv.extend(['/usr/bin/env', '--', str(interpreter), '-IB', str(self.staged_worker), action, commit])
        if argument is not None:
            argv.append(argument)
        argv.extend(['--previous', self.old])
        emit('worker', action=action)
        cmd(argv, timeout=1840, action=action)

    def save_inputs(self) -> None:
        for source, destination, mode in ((APPROVED, self.old_bundle, 0o640), (self.bundle, self.new_bundle, 0o640),
                                          (self.worker_file, self.staged_worker, 0o644)):
            trusted(source)
            if destination.exists():
                trusted(destination)
                if digest(source) != digest(destination):
                    need(destination == self.staged_worker and not self.receipt.exists()
                         and not (self.stage / 'native-verified.json').exists()
                         and not (ROOT / 'releases' / identity(self.new)).exists(), 'previous_inputs_differ')
                    previous_hash = digest(destination)
                    preserved = self.stage / ('worker-before-' + previous_hash + '.py')
                    if not preserved.exists():
                        os.link(destination, preserved)
                    trusted(preserved)
                    need(digest(preserved) == previous_hash, 'previous_worker_changed')
                    atomic(destination, source.read_bytes(), mode=mode, gid=self.gid)
            else:
                atomic(destination, source.read_bytes(), mode=mode, gid=self.gid)

    def prepare(self) -> None:
        need(current() == self.old and ref(APPROVED) == self.old, 'old_release_changed')
        need(digest(Path('/var/lib/discordbot/wheels/wheel-lock.json')) == WHEEL, 'wheel_lock_changed')
        healthy(self.old, 6)
        self.save_inputs()
        if self.receipt.exists():
            self.prepared()
            emit('prepared', commit=self.new)
            return
        need(self.stage.stat().st_dev == (ROOT / 'releases').stat().st_dev, 'non_atomic_install_volume')
        installed = ROOT / 'releases' / identity(self.new)
        qa = self.stage / 'native-verified.json'
        if qa.exists():
            trusted(qa)
            evidence = json.loads(qa.read_bytes())
            need(evidence['commit'] == self.new and evidence['bundle'] == self.sha
                 and re.fullmatch('build-[0-9a-f]{32}', evidence['directory']) is not None, 'invalid_build_receipt')
            self.build_stage = self.stage / evidence['directory']
        else:
            need(not installed.exists(), 'existing_candidate_without_test_receipt')
            need(shutil.disk_usage(self.stage).free > 1536 * 1024**2, 'insufficient_build_space')
            self.build_stage = self.stage / ('build-' + uuid4().hex)
            self.build_stage.mkdir(mode=0o755)
            for folder in ('releases', 'candidates'):
                directory = self.build_stage / folder
                directory.mkdir(mode=0o750)
                os.chown(directory, self.uid, self.gid)
                directory.chmod(0o2750)
            self.worker('build', self.new, str(self.new_bundle))
            self.worker('test', self.new, str(self.new_bundle))
            self.worker('publish', self.new)
            with deploy_directory(self.build_stage / 'releases', self.uid, self.gid) as source:
                with deploy_directory(installed.name, self.uid, self.gid, parent=source) as candidate:
                    manifest = sealed_manifest_hash(candidate, self.uid, self.gid)
            evidence = {'bundle': self.sha, 'commit': self.new, 'manifest': manifest,
                        'directory': self.build_stage.name}
            atomic(qa, json.dumps(evidence).encode(), mode=0o600)
        trusted(ROOT.parent, directory=True)
        trusted(self.build_stage, directory=True)
        with deploy_directory(ROOT, self.uid, self.gid) as layout:
            with deploy_directory('releases', self.uid, self.gid, parent=layout) as destination:
                if not installed.exists():
                    emit('worker', action='install')
                    with deploy_directory(self.build_stage / 'releases', self.uid, self.gid) as source:
                        install_candidate(source, destination, installed.name, evidence['manifest'], self.uid, self.gid)
                with deploy_directory(installed.name, self.uid, self.gid, parent=destination) as candidate:
                    need(sealed_manifest_hash(candidate, self.uid, self.gid) == evidence['manifest'], 'installed_manifest_changed')
        self.worker('verify', self.new)
        need(current() == self.old and ref(APPROVED) == self.old, 'active_release_changed')
        result = {'previous': self.old, 'commit': self.new, 'bundle': self.sha,
                  'worker': digest(self.staged_worker), 'old_bundle': digest(self.old_bundle)}
        atomic(self.receipt, json.dumps(result).encode(), mode=0o600)
        emit('prepared', commit=self.new)

    def prepared(self) -> None:
        for item in (self.receipt, self.old_bundle, self.new_bundle, self.staged_worker):
            trusted(item)
        info = json.loads(self.receipt.read_bytes())
        need(info == {'previous': self.old, 'commit': self.new, 'bundle': self.sha, 'worker': digest(self.staged_worker),
                      'old_bundle': digest(self.old_bundle)} and digest(self.new_bundle) == self.sha
             and ref(self.old_bundle) == self.old and ref(self.new_bundle) == self.new, 'prepared_receipt_changed')
        self.worker('verify', self.new)
        self.worker('verify', self.old)

    def preserving_backup(self) -> None:
        unit = JOBS[0] + '.service'
        command = prop(unit, 'ExecStart')
        need('/opt/discordbot-backup/releases/' in command and '/backup.py' in command
             and '/opt/discordbot/current' not in command, 'preserving_backup_not_installed')
        proof = STATE / 'preserving-backup-verification.json'
        previous = json.loads(proof.read_bytes()).get('identity') if proof.exists() else None
        emit('preserving_backup')
        ctl('start', unit, timeout=600)
        record = json.loads(proof.read_bytes())
        need(prop(unit, 'Result') == 'success' and prop(unit, 'ExecMainStatus') == '0'
             and record.get('identity') and record['identity'] != previous and record.get('verified') is True
             and record.get('local_prior_preserved') is True and record.get('remote_restored') is True,
             'preserving_backup_unconfirmed')

    def idle(self) -> None:
        for name in JOBS:
            unit = name + '.service'
            need(prop(unit, 'ActiveState') == 'inactive' and prop(unit, 'MainPID') == '0', 'operations_job_busy')
        status = subprocess.run(['/usr/bin/python3', '-IB', '/etc/discordbot/approved-timers.py', '--check-inbox'],
                                capture_output=True, timeout=10).returncode
        need(status == 1, 'pending_or_unreadable_inbox')

    def checkpoint(self) -> None:
        destination = Path(tempfile.mkdtemp(prefix='stopped-', dir=self.stage))
        # The runtime UID can read its own database and any 0600 SQLite sidecars.
        os.chown(destination, pwd.getpwnam('discordbot').pw_uid, self.gid)
        self.worker('checkpoint', self.new, str(destination))

    def stop(self, *, recovering: bool = False) -> None:
        try:
            ctl('stop', *PAIR, timeout=150)
        except RuntimeError:
            if not recovering:
                raise
        for unit in PAIR:
            need(prop(unit, 'ActiveState') in (('inactive', 'failed') if recovering else ('inactive',))
                 and prop(unit, 'MainPID') == '0' and (recovering or prop(unit, 'Result') == 'success'), 'pair_stop_uncertain')
        self.worker('quiescent', self.new)

    def set_source(self, target: str) -> None:
        desired = self.new_bundle if target == self.new else self.old_bundle
        need(ref(APPROVED) in (self.old, self.new), 'unexpected_previous_source')
        trusted(CONFIG, directory=True)
        atomic(APPROVED, desired.read_bytes(), mode=0o640, gid=self.gid)
        need(digest(APPROVED) == digest(desired) and ref(APPROVED) == target, 'source_switch_unconfirmed')

    def restart(self, target: str) -> None:
        ctl('start', *PAIR, timeout=140)
        healthy(target)

    def mark(self, status: str, source: str, target: str) -> None:
        atomic(self.intent, json.dumps({'status': status, 'source': source, 'target': target}).encode(), mode=0o600)

    def resume_timers(self) -> None:
        need(current() == ref(APPROVED) and current() in (self.old, self.new), 'cannot_rearm_mixed_sources')
        ctl('enable', '--now', *TIMERS)
        need(all(prop(t, 'UnitFileState') == 'enabled' and prop(t, 'ActiveState') == 'active' for t in TIMERS),
             'timer_restore_unconfirmed')

    def recover(self, source: str, target: str) -> None:
        # A cancelled/disconnected controller may have completed either atomic
        # pointer change. Roll back to the recorded pre-transaction identity.
        need(current() in (source, target) and ref(APPROVED) in (source, target), 'unknown_recovery_identity')
        ctl('disable', '--now', *TIMERS)
        self.idle()
        with lock(OPLOCK):
            self.idle()
            active = current()
            if active != source:
                self.stop(recovering=True)
                self.checkpoint()
                self.worker('switch', source, active)
            self.restart(source)
            self.set_source(source)
        self.resume_timers()
        self.mark('recovered', source, target)
        emit('rolled_back', commit=source)

    def apply(self, *, rollback: bool) -> None:
        self.prepared()
        source, target = (self.new, self.old) if rollback else (self.old, self.new)
        if self.intent.exists():
            trusted(self.intent)
            previous = json.loads(self.intent.read_bytes())
            if previous['status'] == 'in_progress':
                need(rollback and {previous['source'], previous['target']} == {self.old, self.new},
                     'previous_transaction_needs_rollback')
                self.recover(self.old, self.new)
                return
        need(current() == ref(APPROVED) == source, 'release_or_approved_branch_moved')
        if not rollback:
            healthy(source, 8)
        self.idle()
        need(all(prop(t, 'UnitFileState') == 'enabled' and prop(t, 'ActiveState') == 'active' for t in TIMERS),
             'unexpected_timer_baseline')
        emit('pause_timers')
        self.mark('in_progress', source, target)
        restore_timers = True
        try:
            ctl('disable', '--now', *TIMERS)
            self.idle()
            self.preserving_backup()
            with lock(OPLOCK):
                self.idle()
                need(current() == ref(APPROVED) == source, 'release_changed_before_cutover')
                try:
                    emit('stop_pair')
                    self.stop()
                    self.checkpoint()
                    self.worker('switch', target, source)
                    self.restart(target)
                    self.set_source(target)
                except BaseException:
                    # Restore only code and the scheduler source. The live database remains the authority.
                    restore_timers = False
                    emit('recovering_previous_release')
                    self.stop(recovering=True)
                    active = current()
                    if active != source:
                        need(active == target, 'unrecognized_active_release')
                        self.checkpoint()
                        self.worker('switch', source, active)
                    self.restart(source)
                    self.set_source(source)
                    restore_timers = True
                    emit('previous_release_recovered')
                    raise
        finally:
            if restore_timers:
                self.resume_timers()
                self.mark('settled', source, target)
            else:
                emit('uncertain_timers_disabled')
        need(current() == ref(APPROVED) == target, 'final_source_mismatch')
        healthy(target)
        emit('deployed' if not rollback else 'rolled_back', commit=target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'apply', 'rollback'))
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--previous', default=OLD, help='exact currently approved predecessor commit')
    parser.add_argument('--sha256', required=True)
    a = parser.parse_args()
    need(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', a.commit) is not None
         and re.fullmatch('[a-f0-9]{40}', a.previous) is not None and a.commit != a.previous
         and re.fullmatch('[a-f0-9]{64}', a.sha256) is not None, 'invalid_operator_arguments')
    need(ref(a.bundle) == a.commit and digest(a.bundle) == a.sha256, 'input_bundle_does_not_match_approval')
    os.umask(0o022)
    BASE.mkdir(mode=0o755, exist_ok=True)
    trusted(BASE, directory=True)
    promotion = Promotion(a.previous, a.commit, a.bundle, a.sha256)
    promotion.stage.mkdir(mode=0o755, exist_ok=True)
    trusted(promotion.stage, directory=True)
    with lock(BASE / 'controller.lock', create=True):
        def interrupted(signum, frame):
            raise InterruptedError('operator_transaction_interrupted')
        signal.signal(signal.SIGTERM, interrupted)
        if a.mode == 'prepare':
            promotion.prepare()
        else:
            promotion.apply(rollback=a.mode == 'rollback')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except HostFailure as error:
        emit('blocked', reason=str(error), **error.fields)
        sys.exit(1)
    except Exception as error:
        reason = str(error) if type(error) is RuntimeError else type(error).__name__
        emit('blocked', reason=reason if re.fullmatch('[A-Za-z_]+', reason) else 'operator_failure')
        sys.exit(1)
