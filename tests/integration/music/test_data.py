import asyncio

import pytest

from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.music.ports.repository import Favorite
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


@pytest.mark.asyncio
async def test_cf21_actual_start_atomic_dedupe_restart_global_favorites(tmp_path):
    database = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
    request = lambda: DatabaseRequest.within(5)
    await DataRecovery(database).bootstrap(request())
    await database.start()
    repo = SqliteMusicRepository(database)
    try:
        results = await asyncio.gather(*(repo.record_start(100, "same-logical-session", "same-url", "Title", request()) for _ in range(8)))
        assert sum(results) == 1
        await repo.record_start(200, "same-logical-session", "same-url", "Title", request())
        await repo.record_start(100, "another-session", "same-url", "Title", request())
        assert (await repo.list_play_counts(100, request()))[0].count == 2
        assert (await repo.list_play_counts(200, request()))[0].count == 1
        await repo.put_favorite(10, Favorite("same-url", "Title"), request())
        await repo.put_favorite(10, Favorite("same-url", "Updated"), request())
        assert await repo.list_favorites(10, request()) == (Favorite("same-url", "Updated"),)
        assert await repo.remove_favorite(10, "same-url", request())
        assert not await repo.remove_favorite(10, "same-url", request())
    finally: await database.stop()
    reopened = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
    await reopened.start()
    try:
        repo = SqliteMusicRepository(reopened)
        assert not await repo.record_start(100, "same-logical-session", "same-url", "Title", request())
        assert (await repo.list_play_counts(100, request()))[0].count == 2
    finally: await reopened.stop()


@pytest.mark.asyncio
async def test_music_receipts_survive_encrypted_backup_restore(tmp_path):
    from cryptography.fernet import Fernet
    from discordbot.storage.adapters.recovery import RecoveryCandidate
    source = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic-source.db"))
    request = lambda: DatabaseRequest.within(5)
    await DataRecovery(source).bootstrap(request())
    await source.start()
    destination = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic-restored.db"))
    try:
        repo = SqliteMusicRepository(source)
        await repo.record_start(100, "synthetic-session", "synthetic-url", "Synthetic title", request())
        key = Fernet.generate_key()
        backup = tmp_path / "synthetic-encrypted.sql"
        before = await DataRecovery(source).backup(backup, key, request())
        assert b"synthetic-session" not in backup.read_bytes()
        after = await DataRecovery(destination).restore_copy(RecoveryCandidate(backup, key), destination.config.path, request())
        assert before.metadata_checksum == after.metadata_checksum and after.migration_version == 5
        await destination.start()
        repo = SqliteMusicRepository(destination)
        assert not await repo.record_start(100, "synthetic-session", "synthetic-url", "Synthetic title", request())
        assert (await repo.list_play_counts(100, request()))[0].count == 1
    finally:
        await destination.stop()
        await source.stop()
