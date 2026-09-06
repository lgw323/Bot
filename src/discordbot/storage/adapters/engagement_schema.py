"""Reviewed additive Phase 4 metadata; legacy user columns remain unchanged."""

ENGAGEMENT_DDL = (
    "CREATE TABLE v2_engagement_runtime (id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL)",
    "CREATE TABLE v2_engagement_events (guild_id INTEGER NOT NULL, event_id TEXT NOT NULL, expires REAL NOT NULL, PRIMARY KEY(guild_id,event_id))",
    "CREATE TABLE v2_engagement_voice (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, epoch TEXT NOT NULL, stream TEXT NOT NULL, sequence INTEGER NOT NULL, channel_id INTEGER, muted INTEGER NOT NULL CHECK(muted IN (0,1)), tick REAL NOT NULL, duration REAL NOT NULL CHECK(duration>=0), PRIMARY KEY(guild_id,user_id))",
    "CREATE TABLE v2_engagement_birthday (guild_id INTEGER PRIMARY KEY, day TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('claimed','sent','uncertain')))",
    "CREATE INDEX v2_engagement_expiry ON v2_engagement_events(expires)",
)
ENGAGEMENT_TABLES = frozenset(statement.split()[2] for statement in ENGAGEMENT_DDL if statement.startswith("CREATE TABLE"))
