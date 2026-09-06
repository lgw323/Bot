from contextlib import closing
import gc
import sqlite3

import pytest
import pytest_asyncio

import database_manager
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseConfig


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Create through the actual V1 schema writer using only synthetic rows."""
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(database_manager, "DB_PATH", path)
    database_manager._prepare_database_schema()
    # V1's connection context commits but does not close. Reap that legacy handle
    # before measuring bytes or allowing a later GC-triggered WAL checkpoint.
    gc.collect()
    with closing(sqlite3.connect(path)) as conn:
        conn.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?)", [
            (10, 0, 0, 1, 0, None, None),
            (10, 100, 31, 2, 119.5, 2, 29),
            (10, 200, 7, 1, 60, 2, 31),
        ])
        conn.executemany("INSERT INTO favorites VALUES (?,?,?)", [
            (10, f"https://example.invalid/track?raw={i:02d}", f"친구's\n음악 {i}") for i in range(27)
        ])
        conn.execute("INSERT INTO favorites VALUES (11,'another-user','Other')")
        conn.executemany("INSERT INTO music_settings VALUES (?,?)", [(100, 0.75), (200, 1.0)])
        conn.executemany("INSERT INTO music_play_counts VALUES (?,?,?,?)", [
            (100, f"raw-url-{i:02d}", f"Song {i}", i + 1) for i in range(60)
        ] + [(200, "raw-url-59", "Second guild", 1000)])
        conn.executemany("INSERT INTO watch_sessions VALUES (?,?,?,?,?,?)", [
            ("session-one", 100, 10, "2020-01-01 00:00:00", 1001, 1002),
            ("session-two", 200, 10, "2020-01-02 00:00:00", None, None),
        ])
        conn.executemany("INSERT INTO watch_playlists VALUES (?,?,?,?,?)", [
            ("session-one", "same-url", "Title", "<friend>", 4),
            ("session-two", "same-url", "Other", "Someone", 1),
        ])
        conn.commit()
    return path


@pytest_asyncio.fixture
async def database(legacy_db):
    db = SqliteDatabase(DatabaseConfig(legacy_db))
    await db.start()
    try:
        yield db
    finally:
        await db.stop()
