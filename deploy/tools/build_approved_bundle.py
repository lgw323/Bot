"""Build an offline Pi release bundle from one reviewed public Git commit."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


REF = 'refs/heads/approved'
FULL_SHA = re.compile(r'[0-9a-f]{40}\Z')
ROOT_FILES = ('pyproject.toml', 'requirements.txt', 'requirements-dev.txt')
SCOPE = ('src', 'tests', 'deploy', *ROOT_FILES)
# These tests exercise operator scripts outside the installed app. Keep their
# approved versions with the previous release instead of importing PC tooling.
OPERATOR_TESTS = {
    'tests/architecture/test_rebuild_documentation.py',
    'tests/integration/operations/cutover_model.py',
    'tests/integration/operations/test_a9_candidate_packet.py',
    'tests/integration/operations/test_a9_local_harness.py',
    'tests/integration/operations/test_cutover_controller.py',
    'tests/integration/operations/test_stopped_wal_helper.py',
}
FORBIDDEN_SUFFIXES = (
    '.db', '.db-wal', '.db-shm', '.db-journal', '.sqlite', '.sqlite3', '.sqlite-wal',
    '.sqlite-shm', '.sqlite3-wal', '.sqlite3-shm', '.sql', '.log', '.pyc', '.pyo',
    '.key', '.pem', '.p12', '.pfx', '.bundle', '.zip', '.tgz', '.tar', '.gz', '.whl',
)


def git(repo: Path, *args: str, input_bytes: bytes = b'', env: dict[str, str] | None = None) -> bytes:
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_ALLOW_PROTOCOL='file',
                       GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1', LC_ALL='C')
    if env:
        environment.update(env)
    proc = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(repo), *args],
                          input=input_bytes, capture_output=True, env=environment, timeout=120)
    if proc.returncode:
        raise ValueError(f'git {args[0]} failed')
    return proc.stdout


def included(path: str) -> bool:
    return (not path.startswith(('deploy/runbooks/', 'deploy/tools/', 'tests/integration/source_review/'))
            and not path.lower().endswith(('.md', '.rst')) and path not in OPERATOR_TESTS)


def projected_entries(repo: Path, commit: str) -> dict[bytes, bytes]:
    listing = git(repo, 'ls-tree', '-rlz', commit, '--', *SCOPE)
    entries = {}
    total_size = 0
    for item in listing.split(b'\0'):
        if not item:
            continue
        metadata, path = item.split(b'\t', 1)
        name = path.decode('utf-8')
        if not included(name):
            continue
        mode, kind, oid, size = metadata.split()
        parts = PurePosixPath(name.lower()).parts
        if (mode not in (b'100644', b'100755') or kind != b'blob' or '\\' in name or ':' in name
                or any(not ch.isprintable() for ch in name) or any(part.startswith('.') for part in parts)
                or {'__pycache__', 'node_modules', 'logs', 'secrets'} & set(parts)
                or parts[-1] in ('music_state.json', 'id_rsa', 'id_ed25519', 'credentials.json')
                or parts[-1].endswith(FORBIDDEN_SUFFIXES)):
            raise ValueError('forbidden artifact or non-regular file in release payload')
        total_size += int(size)
        entries[path] = mode + b' ' + oid
    if len(entries) > 10000 or total_size > 64 * 1024 * 1024:
        raise ValueError('source payload exceeds the release size limit')
    required = {*ROOT_FILES, 'deploy/launch.py', 'deploy/dependencies.pins'}
    if not all(p.encode() in entries for p in required) or not all(
            any(path.startswith(prefix) for path in entries) for prefix in (b'src/discordbot/', b'tests/')):
        raise ValueError('release payload is incomplete')
    return entries


def open_previous(repo: Path, bundle: Path) -> str:
    git(repo, 'init', '--bare', '--template=', '--quiet', '.')
    heads = git(repo, 'bundle', 'list-heads', str(bundle)).decode('ascii').splitlines()
    if len(heads) != 1:
        raise ValueError('previous bundle must expose only refs/heads/approved')
    sha, ref = heads[0].split()
    if ref != REF or not FULL_SHA.fullmatch(sha):
        raise ValueError('previous bundle must expose only refs/heads/approved')
    # Verifying in an empty repository excludes bundles that depend on missing history.
    git(repo, 'bundle', 'verify', str(bundle))
    git(repo, '-c', 'fetch.fsckObjects=true', 'fetch', '--quiet', '--no-tags', str(bundle), f'{REF}:{REF}')
    if git(repo, 'cat-file', '-t', sha).strip() != b'commit':
        raise ValueError('previous approved reference must identify a commit')
    return sha


def retain_equivalent_python(source: Path, release: Path, current: dict[bytes, bytes],
                             old: dict[bytes, bytes]) -> int:
    retained = 0
    for name in current.keys() & old.keys():
        if not name.endswith(b'.py') or current[name] == old[name]:
            continue
        new_mode, new_id = current[name].decode('ascii').split()
        old_mode, old_id = old[name].decode('ascii').split()
        if new_mode != old_mode:
            continue
        new_content = git(source, 'cat-file', 'blob', new_id)
        old_content = git(release, 'cat-file', 'blob', old_id)
        if b'\0' not in new_content and new_content.replace(b'\r\n', b'\n') == old_content.replace(b'\r\n', b'\n'):
            # Python treats CRLF and LF as the same source lines. Preserve the
            # approved bytes, including when a different file needs a rollout.
            current[name] = old[name]
            retained += 1
    return retained


def build(source: Path, previous: Path, candidate: str, output: Path) -> dict[str, str | int]:
    if not FULL_SHA.fullmatch(candidate) or git(source, 'cat-file', '-t', candidate).strip() != b'commit':
        raise ValueError('candidate must be the full SHA of an existing local commit')
    previous = previous.resolve(strict=True)
    output = output.absolute()
    if os.path.lexists(output):
        raise FileExistsError('output already exists; choose an unused filename')
    current = projected_entries(source, candidate)
    with tempfile.TemporaryDirectory(prefix='.approved-bundle-', dir=output.parent) as temp:
        work = Path(temp)
        repo = work / 'private.git'
        repo.mkdir()
        parent = open_previous(repo, previous)
        old = projected_entries(repo, parent)
        retained = retain_equivalent_python(source, repo, current, old)
        report = {'source': candidate, 'previous': parent, 'approved': parent, 'status': 'unchanged',
                  'retained_python_eol': retained}
        if current == old:
            return report

        # Borrow only blobs referenced by the selected index entries. No public
        # commit is installed as a ref or parent in the private release graph.
        objects = git(source, 'rev-parse', '--path-format=absolute', '--git-path', 'objects').decode('utf-8').strip()
        alternate = {'GIT_ALTERNATE_OBJECT_DIRECTORIES': json.dumps(Path(objects).as_posix(), ensure_ascii=False)}
        git(repo, 'read-tree', parent)
        changes = [b'0 ' + b'0' * 40 + b'\t' + name for name in sorted(old.keys() - current.keys())]
        changes.extend(current[name] + b'\t' + name for name in sorted(current) if old.get(name) != current[name])
        git(repo, 'update-index', '-z', '--index-info', input_bytes=b'\0'.join(changes) + b'\0', env=alternate)
        tree = git(repo, 'write-tree', env=alternate).decode('ascii').strip()
        # Given the same two commits, produce the same reviewed release identity.
        stamp = max(int(git(source, 'show', '-s', '--format=%ct', candidate)),
                    int(git(repo, 'show', '-s', '--format=%ct', parent)) + 1)
        identity = dict(alternate, GIT_AUTHOR_NAME='Release operator', GIT_COMMITTER_NAME='Release operator',
                        GIT_AUTHOR_EMAIL='release@localhost', GIT_COMMITTER_EMAIL='release@localhost',
                        GIT_AUTHOR_DATE=f'@{stamp} +0000', GIT_COMMITTER_DATE=f'@{stamp} +0000')
        approved = git(repo, 'commit-tree', tree, '-p', parent, '-m', f'Approved source {candidate}',
                       env=identity).decode('ascii').strip()
        git(repo, 'update-ref', REF, approved, parent, env=alternate)
        staged = work / 'release.bundle'
        git(repo, 'bundle', 'create', str(staged), REF, env=alternate)
        verified = work / 'verified.git'
        verified.mkdir()
        if (open_previous(verified, staged) != approved
                or git(verified, 'rev-parse', approved + '^@').decode().splitlines() != [parent]
                or projected_entries(verified, approved) != current):
            raise ValueError('release bundle does not reproduce the reviewed payload and parent')
        git(verified, 'fsck', '--strict', '--no-dangling')
        staged.chmod(0o600)
        os.link(staged, output)  # Atomic publication, never replace an earlier bundle.
        return dict(report, status='created', approved=approved, tree=tree)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='local reviewed source checkout or bare repository')
    parser.add_argument('--previous', type=Path, required=True, help='previous standalone approved release bundle')
    parser.add_argument('--candidate', required=True, help='full 40-character reviewed source commit')
    parser.add_argument('--output', type=Path, required=True, help='new local bundle filename; unused when unchanged')
    args = parser.parse_args()
    try:
        report = build(args.repo, args.previous, args.candidate, args.output)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Bundle preparation stopped: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
