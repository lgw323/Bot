"""A3-M3: only reviewed UNIQUE constraints may reach writable admission/recovery."""

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
from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.cli import validate_candidate
from discordbot.operations.adapters.recovery import Backups
from discordbot.platform.errors import ConflictError, DataIntegrityError, StartupError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER, decode, restore_script
from discordbot.storage.adapters.engagement_schema import ENGAGEMENT_TABLES
from discordbot.storage.adapters.execution import SqliteDatabase, WorkControl, checked_validation
from discordbot.storage.adapters.migrations import LEDGER_DDL, apply_pending
from discordbot.storage.adapters.music_schema import MUSIC_TABLES
from discordbot.storage.adapters.recovery import DataRecovery, RecoveryCandidate
from discordbot.storage.adapters.schema import LEGACY_DDL, SCHEMA
from discordbot.storage.adapters.watch_schema import WATCH_TABLES
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState
from scripts.rehearse_v2_data import check_copy


def request() -> DatabaseRequest:
    return DatabaseRequest.within(10, "a3r3-synthetic")


def make_source(path: Path, *, constrained: bool = True, ledger: bool = False) -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        for ddl in LEGACY_DDL:
            if constrained and not ledger:
                ddl = ddl.replace("xp INTEGER DEFAULT 0", "xp INTEGER DEFAULT 0 UNIQUE")
            conn.execute(ddl)
        conn.execute("INSERT INTO users(user_id,guild_id,xp,total_vc_seconds) VALUES (10,100,1,1.25)")
        conn.execute("INSERT INTO users(user_id,guild_id,xp) VALUES (11,100,2)")
        if ledger:
            apply_pending(conn, lambda: None)
            if constrained:
                rows = conn.execute("SELECT * FROM v2_migrations").fetchall()
                conn.execute("DROP TABLE v2_migrations")
                conn.execute(LEDGER_DDL.replace("checksum TEXT NOT NULL", "checksum TEXT NOT NULL UNIQUE"))
                conn.executemany("INSERT INTO v2_migrations VALUES (?,?,?,?,?)", rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger", [False, True])
async def test_startup_rejects_before_readiness_or_repository_admission(tmp_path: Path, ledger: bool) -> None:
    source = tmp_path / "source.db"
    make_source(source, ledger=ledger)
    before = source.read_bytes()
    state = DatabaseState.INVALID_LEDGER if ledger else DatabaseState.WRONG_SCHEMA
    db = SqliteDatabase(DatabaseConfig(source))
    try:
        assert (await db.inspect(request())).state is state
        with pytest.raises(DataIntegrityError) as failure:
            await db.start()
        assert failure.value.context["state"] == state.value
        with pytest.raises(ConflictError):
            await SqliteEngagementRepository(db).add_progress(100, 10, 1, 0.5, request())
        assert db.startup_cleanup_complete and db.admitted == (0, 0)
    finally:
        await db.stop()
    runtime_db = SqliteDatabase(DatabaseConfig(source))
    feature = AsyncMock()
    feature.name, feature.required = "synthetic-feature", True
    config = PlatformConfig(service=ServiceKind.DISCORD_BOT, environment=Environment.TEST, release="a3r3")
    runtime = build_discord_runtime(config, resources=(runtime_db, feature))
    try:
        with pytest.raises(StartupError):
            await runtime.start()
        feature.start.assert_not_awaited()
        assert not runtime.health.ready_payload()["ready"]
    finally:
        require_clean_shutdown(await runtime.shutdown())
    assert runtime_db.admitted == (0, 0)
    assert source.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger", [False, True])
@pytest.mark.parametrize("operation", ["migration", "rehearsal", "candidate", "restore"])
async def test_unique_schema_cannot_be_published(tmp_path: Path, ledger: bool, operation: str) -> None:
    source, destination = tmp_path / "source.db", tmp_path / "destination.db"
    make_source(source, ledger=ledger)
    if operation == "candidate" and not ledger:
        # Synthetic pre-existing version-5 DB, as accepted by the pre-fix gate.
        with closing(sqlite3.connect(source, isolation_level=None)) as conn:
            apply_pending(conn, lambda: None)
    before = source.read_bytes()
    db = SqliteDatabase(DatabaseConfig(source))
    state = DatabaseState.INVALID_LEDGER if ledger else DatabaseState.WRONG_SCHEMA
    try:
        if operation == "restore":
            with closing(sqlite3.connect(source)) as conn:
                sql = "\n".join(conn.iterdump()).encode("utf-8")
            key = Fernet.generate_key()
            artifact = tmp_path / "input.enc"
            payload = BACKUP_HEADER + Fernet(key).encrypt(sql)
            artifact.write_bytes(payload)
            decoded, legacy = decode(payload, key, db.config.max_backup_bytes)
            with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
                restore_script(conn, decoded, legacy=legacy, key=key, control=WorkControl(request()))
                assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
                assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                assert checked_validation(conn).state is state
            with pytest.raises(DataIntegrityError):
                await DataRecovery(db).restore_copy(RecoveryCandidate(artifact, key), destination, request())
            assert artifact.read_bytes() == payload
        elif operation == "migration":
            with pytest.raises(DataIntegrityError):
                await DataRecovery(db).migrated_copy(source, destination, request())
        elif operation == "candidate":
            with pytest.raises(DataIntegrityError, match="compatibility"):
                await validate_candidate(source)
        else:
            with pytest.raises(DataIntegrityError):
                await check_copy(source, tmp_path)
            assert not (tmp_path / "expanded.db").exists()
            assert not (tmp_path / "expanded-again.db").exists()
        assert not destination.exists()
        assert not list(tmp_path.glob(".discordbot-candidate-*"))
    finally:
        await db.stop()
    assert source.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger", [False, True])
async def test_invalid_backup_preserves_real_encrypted_last_good_and_metadata(tmp_path: Path, ledger: bool) -> None:
    good, bad = tmp_path / "good.db", tmp_path / "bad.db"
    make_source(good, constrained=False, ledger=True)
    make_source(bad, ledger=ledger)
    if not ledger:
        # Exercise the operations wrapper at its expected version, so rejection
        # cannot be explained by its independent version-5 requirement.
        with closing(sqlite3.connect(bad, isolation_level=None)) as conn:
            apply_pending(conn, lambda: None)
    before = bad.read_bytes()
    good_db, bad_db = SqliteDatabase(DatabaseConfig(good)), SqliteDatabase(DatabaseConfig(bad))
    key, latest = Fernet.generate_key(), tmp_path / "latest.enc"
    root, audit = tmp_path / "backups", tmp_path / "audit"
    root.mkdir()
    audit.mkdir()
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="a3r3-backup")
    try:
        await good_db.start()
        await DataRecovery(good_db).backup(latest, key, request())
        last_good = latest.read_bytes()
        decoded, legacy = decode(last_good, key, good_db.config.max_backup_bytes)
        with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
            restore_script(conn, decoded, legacy=legacy, key=key, control=WorkControl(request()))
            assert checked_validation(conn).state is DatabaseState.VALID
        with pytest.raises(DataIntegrityError):
            await DataRecovery(bad_db).backup(latest, key, request())
        assert latest.read_bytes() == last_good
        manager = Backups(good_db, root, key, "synthetic-key", executor, Audit(audit))
        await manager.create("synthetic-release")
        artifacts = {p.name: p.read_bytes() for p in root.iterdir()}
        manager.database = bad_db
        with pytest.raises(DataIntegrityError):
            await manager.create("synthetic-release")
        assert {p.name: p.read_bytes() for p in root.iterdir()} == artifacts
        assert not list(tmp_path.rglob(".discordbot-candidate-*"))
    finally:
        await good_db.stop()
        await bad_db.stop()
        await executor.close(grace_seconds=5)
    assert bad.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("omit_birthdays", [False, True])
@pytest.mark.parametrize("omit_watch_pair", [False, True])
async def test_all_supported_variants_rehearse_without_source_changes(
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
        conn.execute("INSERT INTO users(user_id,guild_id,xp,total_vc_seconds) VALUES (10,100,1,1.25)")
        conn.commit()
    before = source.read_bytes()
    result = await check_copy(source, tmp_path)
    assert result["repeat_migration"] == result["semantic_reconciliation"] == result["old_reader"] == "pass"
    assert result["version_before"] == 0 and result["version_after"] == 5
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".discordbot-candidate-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("constrained", [False, True])
async def test_same_xp_write_distinguishes_real_constraint_from_canonical_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, constrained: bool,
) -> None:
    source, good = tmp_path / "source.db", tmp_path / "good.db"
    make_source(source, constrained=constrained)
    make_source(good, constrained=False)
    with closing(sqlite3.connect(good)) as conn:
        good_report = checked_validation(conn)
    db = SqliteDatabase(DatabaseConfig(source))
    try:
        assert (await db.inspect(request())).state is (DatabaseState.WRONG_SCHEMA if constrained else DatabaseState.VALID)
        if constrained:
            # Deliberately bypass only admission for the causal write proof. All
            # rejection/publication tests above use the real, unmocked validator.
            with monkeypatch.context() as bypass:
                bypass.setattr("discordbot.storage.adapters.execution.inspect_path", lambda *args: good_report)
                await db.start()
        else:
            await db.start()
        repo = SqliteEngagementRepository(db)
        if constrained:
            with pytest.raises(DataIntegrityError, match="SQLite integrity failure"):
                await repo.add_progress(100, 10, 1, 0.5, request())
        else:
            await repo.add_progress(100, 10, 1, 0.5, request())
        member = await repo.get_member(100, 10, request())
        assert member is not None
        assert (member.xp, member.total_vc_seconds) == ((1, 1.25) if constrained else (2, 1.75))
    finally:
        await db.stop()


@pytest.mark.parametrize("clause", [
    ", UNIQUE(xp)",
    ', CONSTRAINT "odd UNIQUE name" UNIQUE("xp")',
    ", UNIQUE(xp COLLATE NOCASE DESC)",
])
def test_table_unique_constraints_reject_even_when_integrity_is_ok(clause: str) -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        for ddl in LEGACY_DDL:
            if ddl.startswith("CREATE TABLE users"):
                ddl = ddl[:-1] + clause + ")"
            conn.execute(ddl)
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert checked_validation(conn).state is DatabaseState.WRONG_SCHEMA


@pytest.mark.parametrize("table", sorted(set(SCHEMA) | ENGAGEMENT_TABLES | WATCH_TABLES | MUSIC_TABLES | {"v2_migrations"}))
@pytest.mark.parametrize("kind", ["plain", "partial", "expression"])
def test_extra_unique_indexes_rejected_on_every_governed_table(table: str, kind: str) -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
        for ddl in LEGACY_DDL:
            conn.execute(ddl)
        apply_pending(conn, lambda: None)
        column = conn.execute(f'PRAGMA table_xinfo("{table}")').fetchone()[1]
        key = f'"{column}"' if kind != "expression" else f'("{column}") + 0'
        where = f' WHERE "{column}" IS NOT NULL' if kind == "partial" else ""
        conn.execute(f'CREATE UNIQUE INDEX "odd name" ON "{table}"({key}){where}')
        before = tuple(conn.iterdump())
        state = DatabaseState.INVALID_LEDGER if table == "v2_migrations" else DatabaseState.WRONG_SCHEMA
        assert checked_validation(conn).state is state
        assert tuple(conn.iterdump()) == before
        if table == "v2_migrations":
            with pytest.raises(DataIntegrityError, match="ledger UNIQUE"):
                apply_pending(conn, lambda: None)
            assert tuple(conn.iterdump()) == before


@pytest.mark.parametrize("clause", ["", "UNIQUE COLLATE NOCASE"])
def test_ledger_identity_uniqueness_must_retain_reviewed_meaning(clause: str) -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
        for ddl in LEGACY_DDL:
            conn.execute(ddl)
        conn.execute(LEDGER_DDL.replace("identity TEXT NOT NULL UNIQUE", "identity TEXT NOT NULL " + clause))
        assert checked_validation(conn).state is DatabaseState.INVALID_LEDGER
        with pytest.raises(DataIntegrityError, match="ledger UNIQUE"):
            apply_pending(conn, lambda: None)


def test_named_table_ledger_unique_and_nonunique_indexes_are_supported() -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as conn:
        for ddl in LEGACY_DDL:
            conn.execute(ddl)
        ddl = LEDGER_DDL.replace("identity TEXT NOT NULL UNIQUE", "identity TEXT NOT NULL")
        conn.execute(ddl.rstrip()[:-1] + ', CONSTRAINT "named unique" UNIQUE("identity"))')
        conn.execute("CREATE INDEX harmless ON users(xp)")
        assert apply_pending(conn, lambda: None) == 5
        assert checked_validation(conn).state is DatabaseState.VALID
