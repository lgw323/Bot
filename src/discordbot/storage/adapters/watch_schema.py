"""Additive Watch owner lease, idempotency and Discord cleanup outbox."""

WATCH_DDL = (
    "CREATE TABLE v2_watch_owner (id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL, lease REAL NOT NULL)",
    "CREATE TABLE v2_watch_intents (session_id TEXT PRIMARY KEY, guild_id INTEGER NOT NULL, created_by INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, closed INTEGER NOT NULL CHECK(closed IN (0,1)), channel_id INTEGER, message_id INTEGER, admin_channel INTEGER, admin_message INTEGER, cleaned INTEGER NOT NULL CHECK(cleaned IN (0,1)))",
)
WATCH_TABLES = frozenset(statement.split()[2] for statement in WATCH_DDL)
