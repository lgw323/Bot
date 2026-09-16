"""Offline operator tooling uses the V1 reader; excluded from release-only operations tests."""

import gc
import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

import database_manager
from scripts.prepare_production_candidate import fingerprint, prepare, recover, preserve_recovery


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-source.db"
    monkeypatch.setattr(database_manager, "DB_PATH", path)
    database_manager._prepare_database_schema()
    gc.collect()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO users VALUES (10,100,31,2,119.5,2,29)")
        connection.execute("INSERT INTO favorites VALUES (10,'https://example.invalid','Synthetic')")
        connection.commit()
    return path


@pytest.mark.asyncio
async def test_copy_only_candidate_and_real_encrypted_restore(source, tmp_path):
    original = fingerprint(source)
    output = tmp_path / "candidate-run"
    result = await prepare(source, output)
    assert result["source_unchanged"] and result["validation"]["version_after"] == 5
    assert result["validation"]["old_reader"] == "pass"
    assert fingerprint(source) == fingerprint(output / "preserved-original.db") == original
    key = tmp_path / "db_key"
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    recovered = await recover(output, key, "synthetic-key", "synthetic-release")
    assert recovered["backup_restore"] == "verified" and recovered["production_promoted"] is False
    assert recovered["recovery"]["semantic_reconciliation"] == "pass"
    preserved = await preserve_recovery(output, key, "synthetic-key", "synthetic-release")
    assert preserved["preservation_recovery"]["schema"] == 0
    assert preserved["preservation_recovery"]["semantic_reconciliation"] == "pass"
    assert fingerprint(source) == original
    with pytest.raises(ValueError):
        await prepare(source, output)


@pytest.mark.asyncio
async def test_live_sidecar_is_rejected_before_copy(source, tmp_path):
    source.with_name(source.name + "-wal").write_bytes(b"synthetic-sidecar")
    with pytest.raises(ValueError):
        await prepare(source, tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()


@pytest.mark.asyncio
async def test_changed_candidate_rejected_before_key_use(source, tmp_path):
    output = tmp_path / "candidate-run"
    await prepare(source, output)
    candidate = output / "candidate.db"
    candidate.chmod(0o600)
    candidate.write_bytes(b"changed")
    with pytest.raises(ValueError):
        await recover(output, tmp_path / "absent-key", "synthetic", "synthetic-release")
    assert not (output / "backups").exists()
