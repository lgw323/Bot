"""A3-M1: synthetic schema additions must fail before writable readiness/publication."""

import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.discord_app import build_discord_runtime
from discordbot.composition.runtime import require_clean_shutdown
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.platform.errors import ConflictError, DataIntegrityError, StartupError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER, decode, restore_script
from discordbot.storage.adapters.engagement_schema import ENGAGEMENT_TABLES
from discordbot.storage.adapters.execution import SqliteDatabase, WorkControl, checked_validation
from discordbot.storage.adapters.migrations import apply_pending, validate_ledger
from discordbot.storage.adapters.music_schema import MUSIC_TABLES
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.adapters.schema import LEGACY_DDL, SCHEMA, create_legacy_schema, table_columns
from discordbot.storage.adapters.watch_schema import WATCH_TABLES
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState
from scripts.rehearse_v2_data import check_copy


GENERATED_XP_DDL = (
    "ALTER TABLE users ADD COLUMN unexpected INTEGER "
    "GENERATED ALWAYS AS (xp) VIRTUAL CHECK (unexpected < 2)"
)
GOVERNED_TABLES = sorted(set(SCHEMA) | ENGAGEMENT_TABLES | WATCH_TABLES | MUSIC_TABLES | {"v2_migrations"})


def request() -> DatabaseRequest:
    return DatabaseRequest.within(10, "a3r-synthetic")


def make_source(path: Path, table: str = "users") -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        create_legacy_schema(conn)
        conn.execute("INSERT INTO users VALUES (10,100,1,1,0,NULL,NULL)")
        if table == "users":
            conn.execute(GENERATED_XP_DDL)
        else:
            apply_pending(conn, lambda: None)
            conn.execute("ALTER TABLE v2_migrations ADD COLUMN unexpected INTEGER GENERATED ALWAYS AS (version) VIRTUAL")


@pytest.mark.parametrize("table", GOVERNED_TABLES)
@pytest.mark.parametrize("kind,hidden", [("VIRTUAL", 2), ("STORED", 3)])
def test_every_governed_table_rejects_unknown_generated_columns(table: str, kind: str, hidden: int) -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
        # Define STORED columns at table creation; ALTER cannot add them to populated tables.
        for ddl in LEGACY_DDL:
            if ddl.split()[2] == table:
                ddl = ddl.replace(" (", f" (unexpected INTEGER GENERATED ALWAYS AS (1) {kind}, ", 1)
            conn.execute(ddl)
        if table not in SCHEMA:
            apply_pending(conn, lambda: None)
            if table == "v2_migrations":
                # Rebuild only this synthetic ledger definition for the STORED case.
                ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
                rows = conn.execute("SELECT * FROM v2_migrations").fetchall()
                conn.execute("DROP TABLE v2_migrations")
                conn.execute(ddl[:-1] + f", unexpected INTEGER GENERATED ALWAYS AS (1) {kind})")
                conn.executemany("INSERT INTO v2_migrations(version,identity,checksum,state,applied_at) VALUES (?,?,?,?,?)", rows)
            else:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN unexpected INTEGER GENERATED ALWAYS AS (1) {kind}')
        ordinary = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        complete = conn.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
        assert len(complete) == len(ordinary) + 1
        assert next(row for row in complete if row[1] == "unexpected")[6] == hidden
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        before = tuple(conn.iterdump())
        expected = DatabaseState.INVALID_LEDGER if table == "v2_migrations" else DatabaseState.WRONG_SCHEMA
        assert checked_validation(conn).state is expected
        assert tuple(conn.iterdump()) == before
        if table == "v2_migrations":
            with pytest.raises(DataIntegrityError, match="ledger layout"):
                validate_ledger(conn)
            with pytest.raises(DataIntegrityError, match="ledger layout"):
                apply_pending(conn, lambda: None)
            assert tuple(conn.iterdump()) == before


@pytest.mark.parametrize("column", ["birth_month", "channel_id"])
@pytest.mark.parametrize("kind", ["VIRTUAL", "STORED"])
def test_expected_nullable_name_and_type_do_not_authorize_generated_column(column: str, kind: str) -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        for ddl in LEGACY_DDL:
            conn.execute(ddl.replace(f"{column} INTEGER", f"{column} INTEGER GENERATED ALWAYS AS (NULL) {kind}"))
        assert checked_validation(conn).state is DatabaseState.WRONG_SCHEMA


def test_virtual_table_hidden_columns_are_visible_and_unsupported() -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        create_legacy_schema(conn)
        conn.execute("DROP TABLE music_settings")
        try:
            conn.execute("CREATE VIRTUAL TABLE music_settings USING fts5(guild_id,volume)")
        except sqlite3.OperationalError as exc:
            if str(exc) == "no such module: fts5":
                pytest.skip("SQLite build has no FTS5 module for the synthetic hidden-column fixture")
            raise
        complete = table_columns(conn, "music_settings")
        assert any(column.hidden == 1 for column in complete)
        assert len(complete) > len(conn.execute("PRAGMA table_info(music_settings)").fetchall())
        assert checked_validation(conn).state is DatabaseState.WRONG_SCHEMA


@pytest.mark.asyncio
@pytest.mark.parametrize("generated", [False, True])
async def test_real_runtime_gates_feature_admission_on_schema(tmp_path: Path, generated: bool) -> None:
    source = tmp_path / "source.db"
    if generated:
        make_source(source)
    else:
        with closing(sqlite3.connect(source)) as conn:
            create_legacy_schema(conn)
    db = SqliteDatabase(DatabaseConfig(source))
    feature = AsyncMock()
    feature.name = "synthetic-feature"
    feature.required = True
    config = PlatformConfig(service=ServiceKind.DISCORD_BOT, environment=Environment.TEST, release="a3r-test")
    runtime = build_discord_runtime(config, resources=(db, feature))
    try:
        if generated:
            with pytest.raises(StartupError):
                await runtime.start()
            feature.start.assert_not_awaited()
            assert not runtime.health.ready_payload()["ready"]
        else:
            await runtime.start()
            feature.start.assert_awaited_once()
            assert runtime.health.ready_payload()["ready"]
    finally:
        require_clean_shutdown(await runtime.shutdown())
    assert db.admitted == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("table,state", [("users", DatabaseState.WRONG_SCHEMA), ("v2_migrations", DatabaseState.INVALID_LEDGER)])
async def test_startup_rejects_generated_schema_before_xp_write(tmp_path: Path, table: str, state: DatabaseState) -> None:
    source = tmp_path / "source.db"
    make_source(source, table)
    before = source.read_bytes()
    db = SqliteDatabase(DatabaseConfig(source))
    try:
        assert (await db.inspect(request())).state is state
        with pytest.raises(DataIntegrityError) as failure:
            await db.start()
        assert failure.value.context["state"] == state.value
        with pytest.raises(ConflictError):
            await SqliteEngagementRepository(db).add_progress(100, 10, 1, 0, request())
        assert db.startup_cleanup_complete and db.admitted == (0, 0)
    finally:
        await db.stop()
    assert source.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["users", "v2_migrations"])
@pytest.mark.parametrize("operation", ["migration", "rehearsal", "backup", "restore"])
async def test_generated_schema_cannot_be_promoted(tmp_path: Path, table: str, operation: str) -> None:
    source = tmp_path / "source.db"
    make_source(source, table)
    before = source.read_bytes()
    destination = tmp_path / "output"
    key = Fernet.generate_key()
    db = SqliteDatabase(DatabaseConfig(source))
    recovery = DataRecovery(db)
    state = DatabaseState.WRONG_SCHEMA if table == "users" else DatabaseState.INVALID_LEDGER
    try:
        if operation == "restore":
            # Produce the adversarial envelope independently of the repaired backup gate.
            with closing(sqlite3.connect(source)) as conn:
                sql = "\n".join(conn.iterdump()).encode("utf-8")
            payload = BACKUP_HEADER + Fernet(key).encrypt(sql)
            backup = tmp_path / "input.encrypted"
            backup.write_bytes(payload)
            decoded, legacy = decode(payload, key, db.config.max_backup_bytes)
            with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
                restore_script(conn, decoded, legacy=legacy, key=key, control=WorkControl(request()))
                assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
                assert checked_validation(conn).state is state
            with pytest.raises(DataIntegrityError) as failure:
                await recovery.restore_copy(RecoveryCandidate(backup, key), destination, request())
            assert backup.read_bytes() == payload
        elif operation == "backup":
            destination.write_bytes(b"synthetic-last-good")
            with pytest.raises(DataIntegrityError) as failure:
                await recovery.backup(destination, key, request())
        elif operation == "migration":
            with pytest.raises(DataIntegrityError) as failure:
                await recovery.migrated_copy(source, destination, request())
        else:
            with pytest.raises(DataIntegrityError) as failure:
                await check_copy(source, tmp_path)
            assert not (tmp_path / "expanded.db").exists()
        assert failure.value.context["state"] == state.value
        if operation == "backup":
            assert destination.read_bytes() == b"synthetic-last-good"
        else:
            assert not destination.exists()
        assert not list(tmp_path.glob(".discordbot-candidate-*"))
    finally:
        await db.stop()
    assert source.read_bytes() == before


@pytest.mark.asyncio
async def test_generated_constraint_really_breaks_repository_xp_without_validation_boundary(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as conn:
        create_legacy_schema(conn)
        conn.execute("INSERT INTO users VALUES (10,100,1,1,0,NULL,NULL)")
        conn.commit()
    db = SqliteDatabase(DatabaseConfig(source))
    try:
        await db.start()
        # Bypass only the startup boundary by introducing the DDL after valid startup.
        # This is a causal proof, not a promise to monitor external live DDL changes.
        with closing(sqlite3.connect(source)) as conn:
            conn.execute(GENERATED_XP_DDL)
        with pytest.raises(DataIntegrityError, match="SQLite integrity failure"):
            await SqliteEngagementRepository(db).add_progress(100, 10, 1, 0, request())
        member = await SqliteEngagementRepository(db).get_member(100, 10, request())
        assert member is not None and member.xp == 1
    finally:
        await db.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("omit_birthdays", [False, True])
@pytest.mark.parametrize("omit_watch_pair", [False, True])
async def test_canonical_and_permitted_variants_keep_full_roundtrip_and_xp(
    tmp_path: Path, omit_birthdays: bool, omit_watch_pair: bool,
) -> None:
    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as conn:
        for ddl in LEGACY_DDL:
            if omit_birthdays:
                ddl = ddl.replace(", birth_month INTEGER, birth_day INTEGER", "")
            if omit_watch_pair:
                ddl = ddl.replace(", channel_id INTEGER, message_id INTEGER", "")
            conn.execute(ddl)
        conn.execute("INSERT INTO users(user_id,guild_id,xp) VALUES (10,100,1)")
        conn.commit()
    db = SqliteDatabase(DatabaseConfig(source))
    worker = SqliteDatabase(DatabaseConfig(tmp_path / "unused.db"))
    restored = SqliteDatabase(DatabaseConfig(tmp_path / "restored.db"))
    try:
        await db.start()
        repo = SqliteEngagementRepository(db)
        await repo.add_progress(100, 10, 1, 0.25, request())
        member = await repo.get_member(100, 10, request())
        assert member is not None and (member.xp, member.total_vc_seconds) == (2, 0.25)
        recovery = DataRecovery(worker)
        migrated = tmp_path / "migrated.db"
        report = await recovery.migrated_copy(source, migrated, request())
        assert report.migration_version == 5
        migrated_db = SqliteDatabase(DatabaseConfig(migrated))
        try:
            await migrated_db.start()
            key = Fernet.generate_key()
            backup = tmp_path / "backup.encrypted"
            backed_up = await DataRecovery(migrated_db).backup(backup, key, request())
            recovered = await recovery.restore_copy(RecoveryCandidate(backup, key), restored.config.path, request())
            assert recovered == backed_up == report
        finally:
            await migrated_db.stop()
        with closing(sqlite3.connect(restored.config.path)) as conn:
            assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
            assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert conn.execute("PRAGMA user_version").fetchone() == (0,)
        await restored.start()
        assert await SqliteEngagementRepository(restored).get_member(100, 10, request()) == member
        await SqliteEngagementRepository(restored).add_progress(100, 10, 1, 0, request())
    finally:
        await db.stop()
        await worker.stop()
        await restored.stop()
