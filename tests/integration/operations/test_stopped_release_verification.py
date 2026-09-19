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
