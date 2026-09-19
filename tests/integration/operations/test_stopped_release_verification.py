"""Operator export guards, using synthetic archives only."""
import importlib.util
import io
from pathlib import Path
import stat
import zipfile

import pytest


def verifier():
    path = Path(__file__).resolve().parents[3]/'deploy/production/verify-stopped-release.py'
    spec = importlib.util.spec_from_file_location('stopped_verifier',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', ['../src/escape.py', '/src/escape.py', 'src/../../escape.py',
                                  'src/.env', 'tests/actual.db', 'data/actual.sql', 'src/link.py'])
def test_retry_export_rejects_unsafe_inventory(name):
    with zipfile.ZipFile(io.BytesIO(),'w') as archive:
        archive.comment = b'a'*40
        item = zipfile.ZipInfo(name)
        if name=='src/link.py':
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(item,'synthetic')
        with pytest.raises(ValueError,match='inventory'):
            verifier().safe_archive(archive,'a'*40)


def test_retry_export_requires_exact_commit_and_allows_test_support():
    with zipfile.ZipFile(io.BytesIO(),'w') as archive:
        archive.comment = b'a'*40
        for name in ('src/example.py','database_manager.py','scripts/synthetic.sh','docs/example.md'):
            archive.writestr(name,'synthetic')
        verifier().safe_archive(archive,'a'*40)
        with pytest.raises(ValueError,match='identity'):
            verifier().safe_archive(archive,'b'*40)


def test_retry_preflight_uses_installed_production_credential_sources():
    sources = verifier().CREDENTIAL_SOURCES
    assert sources['backup_ssh_key'].as_posix()=='/etc/discordbot/backup-ssh/id_ed25519'
    assert sources['known_hosts'].as_posix()=='/etc/discordbot/backup-ssh/known_hosts'
    for name in ('db_key','discord_token','gemini_key','control_key','capability_key'):
        assert sources[name].as_posix()=='/etc/discordbot/secrets/'+name


@pytest.mark.parametrize('change', ['unknown', 'missing', 'duplicate', 'none'])
def test_retry_browser_skip_inventory_is_closed(change):
    module = verifier()
    allowed = sorted(module.NODELESS_BROWSER_CASES)
    module.validate_browser_skips(allowed)
    if change == 'unknown':
        invalid = allowed + ['test_shipped_watch_playback_reconciliation[unreviewed]']
    elif change == 'missing':
        invalid = allowed[1:]
    elif change == 'duplicate':
        invalid = allowed + allowed[:1]
    else:
        invalid = []
    with pytest.raises(RuntimeError, match='inventory'):
        module.validate_browser_skips(invalid)


def test_protected_identity_detects_state_and_preservation_changes_without_content(tmp_path, monkeypatch):
    module = verifier()
    monkeypatch.setattr(module, 'ROOT', tmp_path/'root')
    monkeypatch.setattr(module, 'CONFIG', tmp_path/'config/config.json')
    monkeypatch.setattr(module, 'PRESERVED', {'old-failure':'synthetic-hash'})
    for directory in [*(module.ROOT/name for name in ('data','state','cache','backups','audit','old-failure')), module.CONFIG.parent]:
        directory.mkdir(parents=True)
        (directory/'synthetic').write_text('private synthetic content')
    before = module.protected_identity()
    assert 'private synthetic content' not in str(before)
    (module.ROOT/'state/synthetic').write_text('changed state')
    assert module.protected_identity() != before
    before = module.protected_identity()
    (module.ROOT/'old-failure/synthetic').write_text('changed preservation')
    assert module.protected_identity() != before
