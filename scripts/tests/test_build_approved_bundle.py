"""Exercise the operator bundle builder using disposable Git histories only."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


tool = Path(__file__).resolve().parents[2] / 'deploy' / 'tools' / 'build_approved_bundle.py'
spec = importlib.util.spec_from_file_location('approved_bundle', tool)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def git(repo, *args):
    return builder.git(repo, *args).decode().strip()


def commit(repo, text):
    git(repo, 'add', '-A')
    git(repo, '-c', 'user.name=test', '-c', 'user.email=fixture@invalid', 'commit', '-qm', text)
    return git(repo, 'rev-parse', 'HEAD')


def change(repo, path, text):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


@pytest.fixture
def histories(tmp_path):
    old = tmp_path / 'approved history'
    public = tmp_path / 'public history'
    for repo, branch in ((old, 'approved'), (public, 'main')):
        repo.mkdir()
        git(repo, 'init', '--quiet', '--template=', '--initial-branch=' + branch, '.')
        for path in (*builder.ROOT_FILES, 'deploy/launch.py', 'deploy/dependencies.pins',
                     'src/discordbot/module.py', 'tests/test_runtime.py'):
            change(repo, path, 'synthetic baseline\n')
        change(repo, 'docs/context.md', branch + '\n')
        change(repo, 'tests/integration/operations/test_a9_candidate_packet.py', branch + '\n')
        commit(repo, branch)
    bundle = tmp_path / 'previous.bundle'
    git(old, 'bundle', 'create', str(bundle), builder.REF)
    return old, public, bundle


def test_changed_payload_uses_only_previous_history_and_committed_files(tmp_path, histories):
    old, public, previous = histories
    source_only_parent = git(public, 'rev-parse', 'HEAD')
    (public / 'src/discordbot/module.py').unlink()
    change(public, 'src/discordbot/new.py', 'reviewed\n')
    change(public, 'docs/private-name.md', 'outside the payload\n')
    change(public, 'deploy/tools/pc_operator.py', 'operator-only fixture\n')
    sha = commit(public, 'reviewed change')
    change(public, 'src/discordbot/new.py', 'uncommitted\n')
    output = tmp_path / 'new.bundle'
    result = builder.build(public, previous, sha, output)
    assert result['source'] == sha and result['status'] == 'created'
    received = tmp_path / 'received'
    received.mkdir()
    approved = builder.open_previous(received, output)
    parent = git(old, 'rev-parse', 'HEAD')
    assert approved == result['approved'] and result['previous'] == parent
    assert git(received, 'rev-list', approved).splitlines() == [approved, parent]
    assert git(received, 'show', approved + ':src/discordbot/new.py') == 'reviewed'
    assert git(received, 'show', approved + ':docs/context.md') == 'approved'
    assert git(received, 'show', approved + ':tests/integration/operations/test_a9_candidate_packet.py') == 'approved'
    assert set(git(received, 'diff', '--name-only', parent, approved).splitlines()) == {
        'src/discordbot/new.py', 'src/discordbot/module.py'}
    assert subprocess.run(['git', '-C', str(received), 'cat-file', '-e', source_only_parent],
                          capture_output=True).returncode != 0
    assert subprocess.run(['git', '-C', str(received), 'cat-file', '-e', sha],
                          capture_output=True).returncode != 0
    assert builder.build(public, previous, sha, tmp_path / 'retry.bundle') == result
    with pytest.raises(FileExistsError):
        builder.build(public, previous, sha, output)


def test_docs_tooling_and_excluded_tests_do_not_create_a_release(tmp_path, histories):
    old, public, previous = histories
    for path in ('README.md', 'deploy/runbooks/deploy.md', 'deploy/tools/local.py',
                 'scripts/tests/test_operator.py', 'tests/integration/operations/test_a9_candidate_packet.py'):
        change(public, path, 'new operator instructions\n')
    sha = commit(public, 'documentation and operator tools')
    output = tmp_path / 'unused.bundle'
    result = builder.build(public, previous, sha, output)
    assert result['status'] == 'unchanged' and result['approved'] == git(old, 'rev-parse', 'HEAD')
    assert result['source'] == sha and not output.exists()


@pytest.mark.parametrize('filename', ['src/discordbot/.env', 'tests/private.db', 'tests/data/sql-dump.sql',
                                      'deploy/secrets/key', 'src/__pycache__/x.pyc'])
def test_rejects_forbidden_tracked_artifacts_without_writing_output(tmp_path, histories, filename):
    _, public, previous = histories
    change(public, filename, 'synthetic fixture\n')
    sha = commit(public, 'forbidden test path')
    output = tmp_path / 'must-not-exist.bundle'
    with pytest.raises(ValueError, match='forbidden artifact'):
        builder.build(public, previous, sha, output)
    assert not output.exists()


def test_requires_full_commit_and_single_standalone_approved_input(tmp_path, histories):
    old, public, previous = histories
    sha = git(public, 'rev-parse', 'HEAD')
    out = tmp_path / 'unused.bundle'
    for ref in ('main', sha[:8], 'f'*40):
        with pytest.raises(ValueError):
            builder.build(public, previous, ref, out)
    git(old, 'branch', 'extra')
    extra = tmp_path / 'extra.bundle'
    git(old, 'bundle', 'create', str(extra), '--branches')
    with pytest.raises(ValueError, match='only refs/heads/approved'):
        builder.build(public, extra, sha, out)
    change(old, 'tests/test_runtime.py', 'second\n')
    commit(old, 'prerequisite')
    thin = tmp_path / 'thin.bundle'
    git(old, 'bundle', 'create', str(thin), '^HEAD^', builder.REF)
    with pytest.raises(ValueError, match='bundle failed'):
        builder.build(public, thin, sha, out)
    assert not out.exists()


def test_python_eol_only_preserves_previous_blob_even_with_other_changes(tmp_path, histories):
    old, public, previous = histories
    for repo, ending in ((old, b'\r\n'), (public, b'\n')):
        (repo / 'src/discordbot/module.py').write_bytes(b'print("fixture")' + ending)
        (repo / 'deploy/settings.example.json').write_bytes(b'{}' + b'\r\n')
        git(repo, 'config', 'core.autocrlf', 'false')
        commit(repo, 'equivalent source texts')
    previous = tmp_path / 'python-crlf.bundle'
    git(old, 'bundle', 'create', str(previous), builder.REF)
    sha = git(public, 'rev-parse', 'HEAD')
    output = tmp_path / 'result.bundle'
    result = builder.build(public, previous, sha, output)
    assert result['status'] == 'unchanged' and result['retained_python_eol'] == 1
    assert not output.exists()

    (public / 'deploy/settings.example.json').write_bytes(b'{}\n')
    sha = commit(public, 'byte-level non-Python change')
    result = builder.build(public, previous, sha, output)
    received = tmp_path / 'receiver'
    received.mkdir()
    release = builder.open_previous(received, output)
    assert result['status'] == 'created' and result['retained_python_eol'] == 1
    assert builder.git(received, 'show', release + ':src/discordbot/module.py') == b'print("fixture")\r\n'
    assert builder.git(received, 'show', release + ':deploy/settings.example.json') == b'{}\n'
