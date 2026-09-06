"""Offline copy-only Phase 3 rehearsal. No credentials, network, or Pi access.

Use the repository venv with PYTHONPATH=src and an explicit --source. The source is
opened only to hash/copy bytes. SQLite/V1 readers receive temporary working copies.
Only safe aggregate results are emitted; all working copies are removed on exit.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
from discordbot.storage.adapters.migrations import MIGRATIONS
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.sqlite_repository import SqliteWatchRepository


def fingerprint(path: Path) -> dict[str, str | int]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"size": path.stat().st_size, "sha256": digest}


def request() -> DatabaseRequest:
    return DatabaseRequest.within(30, "phase-03-offline-rehearsal")


async def check_copy(copy: Path, directory: Path) -> dict[str, object]:
    worker = SqliteDatabase(DatabaseConfig(copy))
    try:
        before = require_valid(await worker.inspect(request()))
        migrated = directory / "expanded.db"
        after = await DataRecovery(worker).migrated_copy(copy, migrated, request())
        repeated = await DataRecovery(worker).migrated_copy(migrated, directory / "expanded-again.db", request())
    finally:
        await worker.stop()
    assert before.counts == after.counts == repeated.counts
    assert before.data_checksum == after.data_checksum == repeated.data_checksum
    assert after.migration_version == repeated.migration_version == len(MIGRATIONS)

    # V1's own API is the rollback oracle. Output is never printed or serialized.
    import database_manager as legacy
    previous = (legacy.DB_PATH, legacy.DATA_DIR, legacy.SQL_BACKUP_PATH, legacy.db_lock)
    legacy.DB_PATH = migrated
    legacy.DATA_DIR = directory
    legacy.SQL_BACKUP_PATH = directory / "unused.sql"
    legacy.db_lock = asyncio.Lock()
    runtime = SqliteDatabase(DatabaseConfig(migrated))
    try:
        await runtime.start()
        engagement = SqliteEngagementRepository(runtime)
        music = SqliteMusicRepository(runtime)
        watch = SqliteWatchRepository(runtime)
        # One adapter-private aggregate query supplies keys to exercise all readers.
        keys = await runtime.read(request(), lambda conn: (
            tuple(conn.execute("SELECT user_id,guild_id FROM users")),
            tuple(conn.execute("SELECT guild_id FROM music_settings UNION SELECT guild_id FROM music_play_counts")),
        ))
        matched = {"members": 0, "global_user_rows": 0, "favorite_users": 0,
                   "music_guilds": 0, "watch_sessions": 0, "playlist_items": 0}
        for uid, gid in keys[0]:
            if gid == 0:
                matched["global_user_rows"] += 1
                continue
            v1 = await legacy.get_user_data(uid, gid)
            v2 = await engagement.get_member(gid, uid, request())
            assert (v1["xp"], v1["level"], v1["total_vc_seconds"]) == (v2.xp, v2.level, v2.total_vc_seconds)
            birthdays = await legacy.get_all_birthdays(gid)
            birthday = next((row for row in birthdays if row["user_id"] == uid), None)
            assert (None if birthday is None else (birthday["month"], birthday["day"])) == (None if v2.birth_month is None else (v2.birth_month, v2.birth_day))
            matched["members"] += 1
        favorites = await legacy.get_favorites()
        for uid, rows in favorites.items():
            read = []
            for offset in range(0, len(rows), 100):
                read.extend(await music.list_favorites(int(uid), request(), offset=offset))
            assert sorted((row["url"], row["title"]) for row in rows) == sorted((row.url, row.title) for row in read)
            matched["favorite_users"] += 1
        settings = await legacy.get_music_settings()
        for (gid,) in keys[1]:
            # Absence stays None; V1 aggregate's invented 1.0 default is not persisted.
            volume = await music.get_volume(gid, request())
            if volume is not None:
                assert settings[str(gid)]["volume"] == volume
            expected = settings[str(gid)]["play_counts"]
            read = []
            for offset in range(0, len(expected), 100):
                read.extend(await music.list_play_counts(gid, request(), offset=offset))
            assert {row.url: {"title": row.title, "count": row.count} for row in read} == expected
            matched["music_guilds"] += 1
        sessions = await legacy.get_all_watch_sessions()
        for session in sessions:
            gid, sid = session["guild_id"], session["session_id"]
            assert asdict(await watch.get_session(gid, sid, request())) == session
            expected = await legacy.get_watch_playlist(sid)
            read = []
            for offset in range(0, len(expected), 100):
                read.extend(await watch.list_playlist(gid, sid, request(), offset=offset))
            assert [asdict(row) for row in read] == expected
            matched["watch_sessions"] += 1
            matched["playlist_items"] += len(read)
    finally:
        try:
            await runtime.stop()
        finally:
            legacy.DB_PATH, legacy.DATA_DIR, legacy.SQL_BACKUP_PATH, legacy.db_lock = previous
            gc.collect()  # Close V1's legacy context-manager-only SQLite handles.
    return {
        "integrity": "ok", "schema_before": before.schema_variant,
        "schema_after": after.schema_variant, "version_before": before.migration_version,
        "version_after": after.migration_version, "counts_before": dict(before.counts),
        "counts_after": dict(after.counts), "semantic_reconciliation": "pass",
        "repeat_migration": "pass", "old_reader": "pass", "reader_coverage": matched,
        "legacy_warnings": dict(before.warnings),
        "ledger": [{"version": m.version, "identity": m.identity, "checksum": m.checksum} for m in MIGRATIONS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.source.resolve()
    output = args.output.resolve()
    scratch = root / "scratch"
    if scratch not in output.parents or output.exists() or source == output:
        parser.error("output must be a new file beneath the ignored repository scratch directory")
    if not source.is_file() or source.is_symlink():
        parser.error("source must be a standalone regular SQLite file")
    # A bare copy of a live WAL database is not a safe archive. Never inspect it here.
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        parser.error("source has SQLite sidecars; provide a verified standalone archive")
    logging.disable(logging.CRITICAL)
    before = fingerprint(source)
    result: dict[str, object] = {"original_before": before}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="phase03-rehearsal-", dir=output.parent) as directory:
            copy = Path(directory) / "working.db"
            shutil.copyfile(source, copy)
            assert fingerprint(copy) == before
            result.update(asyncio.run(check_copy(copy, Path(directory))))
        result["working_copies_removed"] = True
        result["status"] = "pass"
    except Exception as exc:
        # No traceback, SQL, keys, or raw row values can reach reports or console.
        result.update(status="fail", error_type=type(exc).__name__)
    finally:
        after = fingerprint(source)
        result.update(original_after=after, original_unchanged=before == after)
        if before != after:
            result["status"] = "fail"
        output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
