"""Build initial immutable code and bootstrap a NEW synthetic staging database."""

import asyncio
import json
import sys
import time
from pathlib import Path


def main() -> None:
    # -I ignores PYTHONDONTWRITEBYTECODE. Keep this exported build source clean
    # before importing it, without weakening Builder's forbidden-artifact gate.
    sys.dont_write_bytecode = True
    source = Path("/var/lib/discordbot/staging-source")
    sys.path.insert(0, str(source / "src"))
    from discordbot.operations.adapters.build import Builder, CommandRunner
    from discordbot.operations.adapters.filesystem import ReleaseStore
    from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
    from discordbot.storage.adapters.recovery import DataRecovery
    from discordbot.storage.ports.contracts import DatabaseRequest

    if not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise SystemExit("Explicit local synthetic installation marker required")
    store = ReleaseStore(Path("/opt/discordbot"))
    if store.current() is not None:
        raise SystemExit("Initial build refuses an existing current release")
    started = time.monotonic()
    builder = Builder(store, CommandRunner(), source, Path("/var/lib/discordbot/wheels"), python="/usr/bin/python3.12")
    identity = builder.build("7d596ade8c721931437560ad9e6828762018972c")
    release = store.path(identity)
    builder.runner.run([str(release / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider",
                       "tests/integration/operations", "--confcutdir=tests/integration/operations", "-q",
                       "-W", "error::RuntimeWarning", "-W", "error::pytest.PytestUnraisableExceptionWarning"], release / "app", 300)
    async def bootstrap() -> None:
        path = Path("/var/lib/discordbot/data/bot_database.db")
        database = SqliteDatabase(DatabaseConfig(path))
        try:
            report = await DataRecovery(database).bootstrap(DatabaseRequest.within(30))
            assert report.migration_version == 5
            path.chmod(0o660)
        finally:
            await database.stop()
    asyncio.run(bootstrap())
    builder.publish(identity)
    store.activate(identity)
    result = {"release": identity, "schema": 5, "synthetic_only": True,
              "duration_seconds": round(time.monotonic() - started, 3)}
    Path("/var/lib/discordbot/state/initial-build.json").write_text(json.dumps(result))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
