"""Build an exact retry release offline, without activation or production writes.

Run only with the reviewed commit/archive digest. Services, current data and
configuration must still match the stopped Phase 10B failure state.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('/var/lib/discordbot')
WORK = Path('/home/os/discordbot-phase10')
OLD = Path('/opt/discordbot/releases/r-49639828a3c2f181-3dac82a792fad576')
CONFIG = Path('/etc/discordbot/config.json')
DB_SHA = '28291bf37128dd62815c818ac45865c8a504cc04a2b3dbb9a8a564d8226dab1d'
PRESERVED = {
    'phase10-precutover-63c7722/failed-attempt': '52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af',
    'phase10-retry-368c8ebf7cbf-favorites-failed-20260919T065256492640Z': 'fab61bdda1dd2c8b664c5fd19525d1cdd46f20c82d630a94ce2ed4caf6f5cc65',
    'phase10-retry-368c8ebf7cbff244-favorites-resume-guard-preservation': 'fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f',
    'phase10-retry-49639828a3c2f181-operator-failed-20260919T092351777156Z': DB_SHA,
}
CONFIG_SHA = '41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40'
SCOPES = {'discord-bot': ('discord_token', 'gemini_key', 'control_key'),
          'watch-web': ('capability_key', 'control_key'),
          'operations': ('db_key', 'backup_ssh_key', 'known_hosts')}
CREDENTIAL_SOURCES = {name:CONFIG.parent/'secrets'/name for names in SCOPES.values() for name in names}
CREDENTIAL_SOURCES.update(backup_ssh_key=CONFIG.parent/'backup-ssh/id_ed25519',
                          known_hosts=CONFIG.parent/'backup-ssh/known_hosts')
SOURCE_NAMES = {'src', 'tests', 'deploy', 'docs', 'scripts', 'cogs', 'database_manager.py',
                'main_bot.py', 'pyproject.toml', 'requirements.txt', 'requirements-dev.txt',
                'README.md', 'AGENTS.md', 'CHANGELOG.md', '.gitignore', 'envtemplate.txt'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError('Linked evidence refused')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o644)
    temporary.replace(path)


def checked(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Bounded verification step failed')
    return result.stdout


def safe_archive(archive: zipfile.ZipFile, commit: str) -> None:
    if archive.comment.decode().strip() != commit:
        raise ValueError('Source identity mismatch')
    seen = set()
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if (path.is_absolute() or '..' in path.parts or not path.parts or '\\' in item.filename
                or path.parts[0] not in SOURCE_NAMES or item.filename in seen
                or stat.S_ISLNK(item.external_attr >> 16)
                or path.suffix.lower() in {'.db', '.sql', '.enc', '.pyc', '.log', '.pem', '.key'}
                or any(part in {'.env', '__pycache__', '.git'} for part in path.parts)):
            raise ValueError('Source inventory refused')
        seen.add(item.filename)


def unchanged() -> None:
    for name in ('discord-bot', 'watch-web', 'discordbot-staging-discord',
                 'discordbot-backup', 'discordbot-update', 'discordbot-manual'):
        props = dict(line.split('=', 1) for line in checked(['systemctl', 'show', name+'.service',
            '-p', 'ActiveState', '-p', 'MainPID']).splitlines())
        if props != {'MainPID': '0', 'ActiveState': 'inactive'}:
            raise RuntimeError('Stopped services required')
    for name in ('backup', 'update', 'manual'):
        if checked(['systemctl', 'show', 'discordbot-'+name+'.timer', '-p', 'ActiveState', '--value']).strip() != 'inactive':
            raise RuntimeError('Stopped timers required')
    if Path('/opt/discordbot/current').resolve(strict=True) != OLD or digest(CONFIG) != CONFIG_SHA:
        raise RuntimeError('Release or configuration changed')
    for directory, expected in {'.':DB_SHA, **PRESERVED}.items():
        path = ROOT/directory/'data/bot_database.db'
        if digest(path) != expected or any(Path(str(path)+suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            raise RuntimeError('Production data changed; reconciliation required')


def protected_identity() -> dict[str, str]:
    """Compare every protected file without publishing names or content."""
    result = {}
    for directory in [*(ROOT/name for name in ('data','state','cache','backups','audit')), CONFIG.parent,
                      *(ROOT/name for name in PRESERVED)]:
        rows = [(str(path.relative_to(directory)), digest(path)) for path in sorted(directory.rglob('*')) if path.is_file()]
        result[str(directory)] = hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()
    return result


def build_worker(run: Path, commit: str, wheels: Path) -> None:
    from discordbot.operations.adapters.build import Builder, CommandRunner
    from discordbot.operations.adapters.filesystem import ReleaseStore

    store = ReleaseStore(Path('/opt/discordbot'))
    builder = Builder(store, CommandRunner(), run/'source', wheels, python='/usr/bin/python3.12')
    started = time.monotonic()
    release = builder.build(commit)
    python = store.path(release)/'.venv/bin/python'
    report = run/'pytest.xml'
    result = subprocess.run([str(python), '-m', 'pytest', 'tests/', '-q', '-p', 'no:cacheprovider',
        '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning',
        '-o', 'xfail_strict=true', '--basetemp='+str(run/'pytest-tmp'), '--junitxml='+str(report)],
        cwd=run/'source', timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={'PATH':os.defpath, 'PYTHON_DOTENV_DISABLED':'1', 'PYTHONDONTWRITEBYTECODE':'1',
             'HOME':str(run), 'LANG':'C.UTF-8', 'GIT_CONFIG_NOSYSTEM':'1'})
    suites = ET.parse(report).getroot().findall('testsuite')
    counts = {name:sum(int(s.get(name, '0')) for s in suites) for name in ('tests', 'failures', 'errors', 'skipped')}
    skipped = [case.get('name') for suite in suites for case in suite.findall('testcase') if case.find('skipped') is not None]
    failures = [case.get('name') for suite in suites for case in suite.findall('testcase')
                if case.find('failure') is not None or case.find('error') is not None]
    evidence = {'release':release, 'commit':commit, 'test_counts':counts, 'skipped_tests':skipped,
                'failed_tests':failures, 'test_exit_code':result.returncode, 'activated':False}
    record(run/'build-result.json', evidence)
    if result.returncode or counts['failures'] or counts['errors'] or not counts['tests']:
        raise RuntimeError('Strict suite failed')
    if any(not name.startswith('test_shipped_watch_browser_client[') for name in skipped):
        raise RuntimeError('Unexpected skipped test')
    builder.publish(release)
    manifest = store.validate(release)
    evidence.update(dependency_hash=manifest['dependency_hash'], schema=[manifest['schema_min'],manifest['schema_max']],
                    manifest_sha256=digest(store.path(release)/'manifest.json'), manifest_files=len(manifest['files']),
                    seconds=round(time.monotonic()-started, 3), immutable_validation='pass')
    record(run/'build-result.json', evidence)


def credential_worker(run: Path, service: str, release: str) -> None:
    source = Path('/opt/discordbot/releases')/release/'app'
    spec = importlib.util.spec_from_file_location('retry_preflight', source/'deploy/production/preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
    result = module.check(CONFIG, credentials, service, True)
    if any(os.access(path, os.R_OK) for path in CREDENTIAL_SOURCES.values()):
        raise ValueError('Source credential readable outside mount')
    result.update(direct_source_access='denied', effective_uid=os.geteuid())
    print(json.dumps(result))


def parent(run: Path, commit: str, checksum: str, wheels: Path) -> int:
    import grp
    import pwd
    from discordbot.operations.adapters.filesystem import ExclusiveLock

    output = WORK/('retry-build-'+commit[:12]+'.json')
    evidence = {'commit':commit, 'stage':'admission', 'activated':False, 'services_started':False,
                'canonical_overwritten':False, 'started_unix':time.time()}
    try:
        if run.exists() or output.exists():
            raise ValueError('New verification paths required')
        with ExclusiveLock(ROOT/'operations.lock').acquire():
            unchanged()
            protected_before = protected_identity()
            archive = WORK/('source-'+commit+'.zip')
            if digest(archive) != checksum:
                raise ValueError('Archive checksum differs')
            uid, gid = pwd.getpwnam('discordbot-deploy').pw_uid, grp.getgrnam('discordbot').gr_gid
            run.mkdir(mode=0o750)
            run.chmod(0o750)
            os.chown(run,uid,gid)
            source = run/'source'
            source.mkdir()
            with zipfile.ZipFile(archive) as exported:
                safe_archive(exported,commit)
                exported.extractall(source)
            for path in (source,*source.rglob('*')):
                os.chown(path,uid,gid)
                path.chmod(0o750 if path.is_dir() else 0o640)
            helper = run/Path(__file__).name
            shutil.copyfile(__file__,helper)
            helper.chmod(0o444)
            base = ['systemd-run','--wait','--pipe','--collect','-p','Group=discordbot',
                    '-p','PrivateNetwork=yes','-p','ProtectSystem=strict','-p','ProtectHome=yes',
                    '-p','NoNewPrivileges=yes','-p','PrivateTmp=yes','-p','UMask=0027']
            evidence['stage'] = 'offline_build_full_strict'
            record(output,evidence)
            try:
                checked(base+['--unit=discordbot-phase10-retry-build','-p','User=discordbot-deploy',
                    '-p','RuntimeMaxSec=1500','-p','ReadWritePaths=/opt/discordbot/releases '+str(run),
                    '-p','InaccessiblePaths=/etc/discordbot /var/lib/discordbot/data /var/lib/discordbot/state /var/lib/discordbot/cache',
                    str(OLD/'.venv/bin/python'),'-I','-B',str(helper),'--worker','build','--commit',commit,'--run',str(run),
                    '--wheels',str(wheels)],1530)
            finally:
                if (run/'build-result.json').is_file():
                    evidence['build'] = json.loads((run/'build-result.json').read_text())
            release = evidence['build']['release']
            evidence['credentials'] = {}
            for service,names in SCOPES.items():
                evidence['stage'] = 'credential_'+service
                record(output,evidence)
                command = base+['--unit=discordbot-phase10-retry-'+service,'-p','RuntimeMaxSec=30',
                    '-p','User='+('discordbot-deploy' if service=='operations' else 'discordbot')]
                for name in names:
                    command += ['-p','LoadCredential='+name+':'+str(CREDENTIAL_SOURCES[name])]
                command += [str(Path('/opt/discordbot/releases')/release/'.venv/bin/python'),'-I','-B',str(helper),
                            '--worker',service,'--release',release,'--commit',commit,'--run',str(run)]
                evidence['credentials'][service] = json.loads(checked(command,45))
            unchanged()
            if protected_identity() != protected_before:
                raise RuntimeError('Protected state changed during isolated verification')
            evidence.update(stage='verified_not_activated', canonical_sha256=DB_SHA, config_sha256=CONFIG_SHA,
                            current_unchanged=True, services_stopped=True, protected_state_unchanged=True,
                            preservation_count=len(PRESERVED))
    except Exception as error:
        evidence.update(failed_stage=evidence['stage'],stage='failed',error_type=type(error).__name__)
    record(output,evidence)
    print('Stopped release verification: '+evidence['stage']+'. See safe retry-build result.')
    return 0 if evidence['stage']=='verified_not_activated' else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--archive-sha256')
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--worker',choices=('build',*SCOPES))
    parser.add_argument('--release')
    parser.add_argument('--wheels',type=Path,default=ROOT/'wheels')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.commit) or args.run != ROOT/('phase10-retry-build-'+args.commit[:12]):
        raise SystemExit('Exact source and isolated path required')
    if args.wheels.parent != ROOT or not re.fullmatch(r'(?:wheels|phase10-wheels-[a-z0-9-]+)',args.wheels.name) or args.wheels.is_symlink():
        raise SystemExit('Reviewed local wheelhouse required')
    if args.worker and args.worker != 'build' and not re.fullmatch(r'r-[0-9a-f]{16}-[0-9a-f]{16}',args.release or ''):
        raise SystemExit('Exact release required')
    source = args.run/'source/src' if args.worker=='build' else OLD/'app/src'
    if args.worker and args.worker != 'build':
        source = Path('/opt/discordbot/releases')/args.release/'app/src'
    sys.path.insert(0,str(source))
    if args.worker=='build':
        build_worker(args.run,args.commit,args.wheels)
        return 0
    if args.worker:
        credential_worker(args.run,args.worker,args.release)
        return 0
    if not re.fullmatch(r'[0-9a-f]{64}',args.archive_sha256 or ''):
        raise SystemExit('Reviewed archive checksum required')
    if os.geteuid()!=0:
        os.execvp('sudo',['sudo','--',str(OLD/'.venv/bin/python'),'-I','-B',str(Path(__file__).resolve()),*sys.argv[1:]])
    return parent(args.run,args.commit,args.archive_sha256,args.wheels)


if __name__=='__main__':
    raise SystemExit(main())
