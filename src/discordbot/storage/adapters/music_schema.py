"""Additive Music logical-session receipts; legacy counters remain readable."""
MUSIC_DDL = (
    "CREATE TABLE v2_music_starts (guild_id INTEGER NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(guild_id,session_id))",
)
MUSIC_TABLES = frozenset(statement.split()[2] for statement in MUSIC_DDL)
