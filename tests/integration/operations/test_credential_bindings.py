from pathlib import Path

import pytest

from .test_production_tools import tool


def test_discovers_unit_and_offhost_dropin_sources_without_guessing_names():
    inspector = tool('production/inspect-credential-bindings.py')
    text = Path('deploy/systemd/discordbot-backup.service').read_text()
    text += '\n' + Path('deploy/production/offhost-backup.service.conf').read_text()
    assert inspector.bindings(text) == {
        'db_key': '/etc/discordbot/secrets/db_key',
        'backup_ssh_key': '/etc/discordbot/backup-ssh/id_ed25519',
        'known_hosts': '/etc/discordbot/backup-ssh/known_hosts'}
    assert inspector.bindings('[Service]\nLoadCredential=old:/etc/discordbot/old\n'
        'LoadCredential=\nLoadCredential=control_key:/etc/discordbot/secrets/control_key') == {
            'control_key': '/etc/discordbot/secrets/control_key'}


@pytest.mark.parametrize('value', ['', '[Service]\nLoadCredential=bad',
    '[Service]\nLoadCredential=control_key:/outside/path',
    '[Service]\nLoadCredential=control_key:/etc/discordbot/../outside',
    '[Service]\nLoadCredential=a:/etc/discordbot/one\nLoadCredential=a:/etc/discordbot/two'])
def test_incomplete_discovery_never_means_missing_credentials(value):
    with pytest.raises(ValueError):
        tool('production/inspect-credential-bindings.py').bindings(value)


def test_metadata_never_opens_contents_and_distinguishes_permission_error(tmp_path, monkeypatch):
    inspector = tool('production/inspect-credential-bindings.py')
    source = tmp_path / 'synthetic-key'
    source.write_bytes(b'synthetic-private-value')
    monkeypatch.setattr(Path, 'read_bytes', lambda *_: pytest.fail('key opened'))
    monkeypatch.setattr(Path, 'read_text', lambda *_: pytest.fail('key opened'))
    assert inspector.metadata(source)['status'] == 'present'
    assert inspector.metadata(tmp_path / 'absent')['status'] == 'missing'
    def denied(_):
        raise PermissionError
    monkeypatch.setattr(Path, 'lstat', denied)
    assert inspector.metadata(source) == {'status': 'unreadable', 'contents_read': False}
