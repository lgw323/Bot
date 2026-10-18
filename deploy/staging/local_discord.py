"""LOCAL SYNTHETIC Gateway substitute; never a production Discord entrypoint.

Runs actual platform/SQLite/listener adapters for credential-free Linux lifecycle
and deploy rehearsals. It does not simulate a successful Discord/Gemini login.
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path


async def run(release: Path) -> None:
    sys.path.insert(0, str(release / "app/src"))
    from discordbot.composition.config import PlatformConfig, ServiceKind, Environment
    from discordbot.composition.runtime import ProcessRuntime, require_clean_shutdown
    from discordbot.operations.adapters.cli import validate_candidate
    from discordbot.operations.adapters.filesystem import ReleaseStore
    from discordbot.operations.adapters.hosting import Servers, health_app, server, TelemetryDrain
    from discordbot.operations.adapters.probe import Probe
    from discordbot.platform.telemetry import build_json_handler
    from discordbot.storage.adapters.execution import SqliteDatabase, DatabaseConfig

    if not Path("/var/lib/discordbot/STAGING_SYNTHETIC_ONLY").is_file():
        raise RuntimeError("Synthetic staging marker required")
    ReleaseStore(Path("/opt/discordbot")).validate(release.name)
    database_path = Path("/var/lib/discordbot/data/bot_database.db")
    await validate_candidate(database_path)
    database = SqliteDatabase(DatabaseConfig(database_path))
    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.DISCORD_BOT, Environment.TEST, release.name),
                             resources=(database,))
    probe = Probe(database, runtime, Path("/var/lib/discordbot/backups/latest.json"))
    app = health_app(runtime, lambda: probe.ready() and listeners.ready(),
                     lambda: {**probe.gauges(), "staging_synthetic_gateway": 1})
    @app.get("/health/staging")
    async def synthetic():
        return {"synthetic_gateway": True, "external_integration": False}
    listeners = Servers((server(app, 9010),), runtime.supervisor)
    drain = TelemetryDrain(runtime)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    def stop():
        runtime.health.stop_accepting()
        stopped.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    logger = logging.getLogger("discordbot")
    handler = build_json_handler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        await runtime.start()
        await probe.start()
        await listeners.start()
        await drain.start()
        logger.info("staging.synthetic_gateway.started")
        await stopped.wait()
    finally:
        runtime.health.stop_accepting()
        try:
            async with asyncio.timeout(10):
                await listeners.stop()
                await probe.stop()
                await drain.stop()
        finally:
            report = await runtime.shutdown()
            drain.flush()
            logger.removeHandler(handler)
            handler.close()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
            require_clean_shutdown(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-local-only", required=True, action="store_true")
    args = parser.parse_args()
    asyncio.run(run(Path("/opt/discordbot/current").resolve(strict=True)))
