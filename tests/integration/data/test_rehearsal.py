import hashlib
import json

import pytest

import database_manager
from scripts.rehearse_v2_data import check_copy


@pytest.mark.asyncio
async def test_offline_rehearsal_tool_on_synthetic_archive_preserves_source_and_reports_no_rows(legacy_db, tmp_path):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    previous = (database_manager.DB_PATH, database_manager.DATA_DIR, database_manager.SQL_BACKUP_PATH, database_manager.db_lock)
    report = await check_copy(legacy_db, tmp_path)
    assert report["old_reader"] == "pass"
    assert report["reader_coverage"]["watch_sessions"] == 2
    assert report["reader_coverage"]["playlist_items"] == 2
    assert report["semantic_reconciliation"] == "pass"
    assert report["counts_before"] == report["counts_after"]
    encoded = json.dumps(report)
    assert "session-one" not in encoded and "example.invalid" not in encoded
    assert "raw-url" not in encoded and "friend" not in encoded
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before
    assert (database_manager.DB_PATH, database_manager.DATA_DIR, database_manager.SQL_BACKUP_PATH, database_manager.db_lock) == previous
