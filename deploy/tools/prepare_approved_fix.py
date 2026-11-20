"""Unprivileged workers for one reviewed release. Never run these modes as root."""
from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET


LOCK = 'bd1ffa96253a4d84b8f229cee226699c54fd3f50ca74b82fa3255adb29093bac'
ROOT = Path('/opt/discordbot')
WHEELS = Path('/var/lib/discordbot/wheels')
REF = 'refs/heads/approved'
TEST_NODE = r'tests/integration/(?:music|operations)/test_[a-zA-Z0-9_]{1,96}\.py(?:::[a-zA-Z][a-zA-Z0-9_]{0,95}){0,2}'
MODULE = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
ERROR_TYPES = {'AssertionError', 'ImportError', 'ModuleNotFoundError', 'PermissionError', 'FileNotFoundError',
    'OSError', 'RuntimeError', 'TypeError', 'ValueError', 'AttributeError', 'KeyError', 'TimeoutError',
    'ConnectionError', 'CalledProcessError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'OperationalError',
    'DataIntegrityError', 'ExternalTemporaryError', 'Failed'}


def known_imports(app: Path) -> set[str]:
    """Only report a missing name already present in the reviewed code or its pins."""
    found = {'tests', 'compatibility', 'scripts', 'deploy', 'discordbot'}
    for source in (app / 'src', app / 'tests', app / 'deploy'):
        for path in source.rglob('*.py'):
            try:
                tree = ast.parse(path.read_bytes())
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    found.add(node.module)
                    found.update(f'{node.module}.{alias.name}' for alias in node.names if alias.name != '*')
    for row in (app / 'deploy/dependencies.pins').read_text().splitlines():
        if '==' in row and not row.lstrip().startswith('#'):
            found.add(row.partition('==')[0].strip().replace('-', '_'))
    return {prefix for name in found for prefix in ('.'.join(name.split('.')[:i]) for i in range(1, len(name.split('.')) + 1))}


def pytest_report(output: bytes, junit: Path, admitted_modules: set[str]) -> dict:
    text = output[-1024 * 1024:].decode('utf8', errors='replace')
    nodes = []
    for match in re.finditer(r'^(?:FAILED|ERROR) (' + TEST_NODE + r')(?=\[|\s|$)', text, re.M):
        if match[1] not in nodes and len(nodes) < 16:
            nodes.append(match[1])
    errors = set()
    missing = set()

    def classify(details: str) -> None:
        for name in re.findall(r'\b([A-Za-z]+(?:Error|Failed)|Failed)(?=[:\s]|$)', details):
            if name in ERROR_TYPES:
                errors.add(name)
        for name in re.findall(r"No module named ['\"](" + MODULE + r")[\"']", details):
            if len(name) <= 96 and name in admitted_modules:
                missing.add(name)

    classify(text)
    try:
        if junit.stat().st_size <= 16 * 1024**2:
            for case in ET.parse(junit).iter('testcase'):
                issues = list(case.findall('failure')) + list(case.findall('error'))
                if not issues:
                    continue
                for issue in issues:
                    classify((issue.get('message', '') + '\n' + (issue.text or ''))[:65536])
                path = case.get('file', '')
                if not re.fullmatch(TEST_NODE, path):
                    path = case.get('name', '').replace('.', '/') + '.py'
                if re.fullmatch(TEST_NODE, path) and len(nodes) < 16 and all(n.split('::')[0] != path for n in nodes):
                    nodes.append(path)
    except (OSError, ET.ParseError):
        pass
    counts = {}
    for line in reversed(text.splitlines()):
        if re.search(r'\bin [0-9]+(?:\.[0-9]+)?s\b', line):
            for count, category in re.findall(r'\b([0-9]{1,5}) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)\b', line):
                if int(count) <= 10000:
                    counts[{'error': 'errors', 'warning': 'warnings'}.get(category, category)] = int(count)
            if counts:
                break
    return {'failed_tests': nodes, 'error_types': sorted(errors)[:8], 'missing_modules': sorted(missing)[:8],
            'pytest_counts': counts}


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def identity(commit: str) -> str:
    return 'r-' + commit[:16] + '-' + LOCK[:16]


def run_git(repo: Path, *args: str) -> str:
    env = dict(PATH='/usr/bin:/bin', HOME='/nonexistent', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL='/dev/null', GIT_ALLOW_PROTOCOL='file', GIT_TERMINAL_PROMPT='0')
    command = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', *args]
    return subprocess.run(command, cwd=repo, env=env, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, timeout=120).stdout.strip()


def build(commit: str, bundle: Path, previous: str) -> None:
    from discordbot.operations.adapters.build import CommandRunner
    from discordbot.operations.adapters.filesystem import ReleaseStore
    from discordbot.operations.adapters.source import SourceBuilder

    store = ReleaseStore(ROOT)
    target = store.path(identity(commit))
    need(not target.exists() and not target.is_symlink(), 'staged_candidate_exists')
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / 'source'
        repo.mkdir()
        run_git(repo, 'init', '--bare', '--quiet', '--template=', '.')
        need(run_git(repo, 'bundle', 'list-heads', str(bundle)) == f'{commit} {REF}', 'bundle_ref')
        run_git(repo, 'bundle', 'verify', str(bundle))
        run_git(repo, '-c', 'fetch.fsckObjects=true', 'fetch', '--no-tags', str(bundle), f'{REF}:{REF}')
        need(run_git(repo, 'rev-parse', '--verify', REF + '^{commit}') == commit, 'bundle_commit')
        run_git(repo, 'merge-base', '--is-ancestor', previous, commit)
        immutable = ('deploy', 'requirements.txt', 'requirements-dev.txt', 'pyproject.toml',
                     'src/discordbot/storage', 'src/discordbot/operations/adapters/recovery.py',
                     'src/discordbot/operations/adapters/deployment.py')
        need(not run_git(repo, 'diff', '--name-only', previous, commit, '--', *immutable), 'deployment_contract_changed')
        policy = Path(directory) / 'policy.json'
        policy.write_text(json.dumps({'repository': str(repo), 'ref': REF}))
        builder = SourceBuilder(store, CommandRunner(), policy, WHEELS)
        builder.python = '/usr/bin/python3.12'
        need(builder.build(commit) == identity(commit), 'candidate_identity')
        expected = {}
        for row in run_git(repo, 'ls-tree', '-r', '-z', commit, '--', 'deploy', 'src', 'tests',
                           'pyproject.toml', 'requirements.txt', 'requirements-dev.txt').split('\0'):
            if row:
                header, path = row.split('\t', 1)
                mode, kind, oid = header.split()
                need(mode in ('100644', '100755') and kind == 'blob', 'unexpected_payload_member')
                expected[path] = oid
        app = target / 'app'
        checked = set()
        for member in app.rglob('*'):
            if member.is_file():
                name = member.relative_to(app).as_posix()
                data = member.read_bytes()
                git_id = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                need(expected.get(name) == git_id, 'source_blob_mismatch')
                checked.add(name)
        need(checked == set(expected), 'source_inventory_mismatch')


def test(commit: str, bundle: Path) -> None:
    from discordbot.operations.adapters.admission import installed_operations_args
    target = ROOT / 'releases' / identity(commit)
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / 'comparison'
        fixture.mkdir()
        run_git(fixture, 'init', '--quiet', '--template=', '.')
        run_git(fixture, 'fetch', '--no-tags', str(bundle), REF)
        need(run_git(fixture, 'rev-parse', '--verify', 'FETCH_HEAD^{commit}') == commit, 'wrong_test_fixture')
        run_git(fixture, 'checkout', commit, '--', 'compatibility')
        app = target / 'app'
        env = dict(PATH='/usr/bin:/bin', HOME=tmp, PYTHONDONTWRITEBYTECODE='1',
                   PYTHON_DOTENV_DISABLED='1', PYTHONPATH=os.pathsep.join(map(str, (app / 'src', app / 'tests', fixture))))
        junit = Path(tmp) / 'native.xml'
        command = [str(target / '.venv/bin/python'), '-B', '-m', 'pytest', *installed_operations_args(),
                   'tests/integration/music', '-p', 'no:cacheprovider', '-q', '--tb=line', '--color=no',
                   '--show-capture=no', '-o', 'junit_family=xunit1', '--junitxml', str(junit),
                   '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning']
        result = subprocess.run(command, cwd=app, env=env, capture_output=True, timeout=900)
        if result.returncode:
            report = pytest_report(result.stdout + b'\n' + result.stderr, junit, known_imports(app))
            print('native_tests ' + json.dumps(report, separators=(',', ':')), flush=True)
            raise RuntimeError('native_tests_failed')


def publish(commit: str) -> None:
    from discordbot.operations.adapters.build import Builder, CommandRunner
    from discordbot.operations.adapters.filesystem import ReleaseStore
    Builder(ReleaseStore(ROOT), CommandRunner(), Path('/nonexistent'), WHEELS).publish(identity(commit))
    verify(commit)


def verify(commit: str) -> None:
    from discordbot.operations.adapters.filesystem import ReleaseStore

    manifest = ReleaseStore(ROOT).validate(identity(commit))
    need(manifest['commit'] == commit and manifest['dependency_hash'] == LOCK
         and manifest['schema_min'] == manifest['schema_max'] == 5, 'manifest_mismatch')


async def checkpoint(destination: Path) -> None:
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.deployment import backup_once

    cfg = json.loads(Path('/etc/discordbot/config.json').read_bytes())
    database = Path(cfg['paths']['database'])
    need(database == Path('/var/lib/discordbot/data/bot_database.db')
         and cfg['environment'] == 'production', 'unexpected_database')
    archive, audit = destination / 'archive', destination / 'audit'
    archive.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    # A read-only WAL database may need to rebuild its shared-memory index on
    # open. Do that on a private copy of the fully stopped database and WAL.
    with tempfile.TemporaryDirectory(dir=destination) as tmp:
        copy = Path(tmp) / database.name
        for suffix in ('', '-wal', '-journal'):
            source = Path(str(database) + suffix)
            try:
                fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                if suffix:
                    continue
                raise
            with os.fdopen(fd, 'rb') as handle:
                before = os.fstat(handle.fileno())
                need(stat.S_ISREG(before.st_mode) and before.st_size < 128 * 1024**2, 'invalid_checkpoint_source')
                with Path(str(copy) + suffix).open('xb') as writer:
                    shutil.copyfileobj(handle, writer)
                after = source.stat(follow_symlinks=False)
                need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                     (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'checkpoint_source_changed')
        settings = SimpleNamespace(database=copy, backups=archive, audit=audit, key_id=cfg['key_id'],
            secrets=SimpleNamespace(db_key=(Path(os.environ['CREDENTIALS_DIRECTORY']) / 'db_key').read_bytes().strip()),
            backup_remote=None)
        current = (ROOT / 'current').resolve(strict=True).name
        result = await backup_once(settings, Audit(audit), current)
    latest = json.loads((archive / 'latest.json').read_bytes())
    need(latest.get('identity') == result and len(list(archive.glob('*.enc'))) == 1, 'checkpoint_unverified')


def main() -> int:
    import pwd
    args = argparse.ArgumentParser()
    args.add_argument('mode', choices=('build', 'test', 'publish', 'verify', 'switch', 'quiescent', 'checkpoint'))
    args.add_argument('commit')
    args.add_argument('argument', nargs='?')
    args.add_argument('--previous', required=True)
    a = args.parse_args()
    user = 'discordbot' if a.mode == 'checkpoint' else 'discordbot-deploy'
    need(os.geteuid() == pwd.getpwnam(user).pw_uid != 0, 'wrong_worker_uid')
    need(all(bool(re.fullmatch('[0-9a-f]{40}', ref)) for ref in (a.commit, a.previous)), 'invalid_commit')
    base = Path('/run/discordbot-promotion-base') if a.mode in ('build', 'test', 'publish') else ROOT / 'releases' / identity(a.previous)
    sys.path.insert(0, str(base / 'app/src'))
    if a.mode == 'build':
        build(a.commit, Path(a.argument), a.previous)
    elif a.mode == 'test':
        test(a.commit, Path(a.argument))
    elif a.mode == 'publish':
        publish(a.commit)
    elif a.mode == 'verify':
        verify(a.commit)
    elif a.mode == 'switch':
        from discordbot.operations.adapters.filesystem import ReleaseStore
        store = ReleaseStore(ROOT)
        need(store.current() == identity(a.argument), 'active_release_changed')
        verify(a.commit)
        store.activate(identity(a.commit))
        need(store.current() == identity(a.commit), 'pointer_unconfirmed')
    elif a.mode == 'quiescent':
        from discordbot.operations.adapters.quiescence import CgroupQuiescence
        for unit in ('discord-bot.service', 'watch-web.service'):
            CgroupQuiescence().verify(unit)
    else:
        asyncio.run(checkpoint(Path(a.argument)))
    print('verified', a.mode, flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        reason = str(error) if type(error) is RuntimeError else type(error).__name__
        sys.exit('worker_error ' + (reason if re.fullmatch('[A-Za-z_]+', reason) else 'worker_failed'))
