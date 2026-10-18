import pytest


@pytest.mark.parametrize('versions,result', [(b'\x01\x01','rollback'), (b'\x02\x02','wal'), (b'\x03\x03',None)])
def test_stopped_verifier_reads_only_journal_header_metadata(tmp_path, monkeypatch, versions, result):
    from .test_production_tools import tool
    module = tool('production/verify-stopped-release.py')
    (tmp_path/'data').mkdir()
    path = tmp_path/'data/bot_database.db'
    content = b'SQLite format 3\x00' + b'\x10\x00' + versions + b'private synthetic body'
    path.write_bytes(content)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    if result:
        assert module.canonical_journal_header() == result
    else:
        with pytest.raises(RuntimeError, match='unsupported'): module.canonical_journal_header()
    assert path.read_bytes() == content
