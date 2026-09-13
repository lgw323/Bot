"""Explicit production executable; importing performs no configuration or login."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from discordbot.composition.config import Environment, PlatformConfig, ResourceLimits, RuntimePolicy, ServiceKind
from discordbot.composition.runtime import require_clean_shutdown
from discordbot.operations.adapters.configuration import load_settings
from discordbot.operations.adapters.filesystem import ReleaseStore
from discordbot.platform.errors import AppError
from discordbot.platform.tasks import TaskSpec, CancellationBehavior
from discordbot.platform.telemetry import build_json_handler


async def run_process(config, settings):
    if config.service is ServiceKind.DISCORD_BOT:
        from discordbot.composition.production_discord import assemble
    else:
        from discordbot.composition.production_watch import assemble
    runtime, feature, listeners, telemetry, probe = assemble(config, settings)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    closing = False
    def stop():
        nonlocal closing
        if closing:
            return
        closing = True
        runtime.health.stop_accepting()
        stopped.set()
        if config.service is ServiceKind.DISCORD_BOT:
            async def close_gateway():
                try:
                    if feature.deferred is not None:
                        await feature.deferred.stop()
                finally:
                    await feature.bot.close()
            runtime.supervisor.start(TaskSpec("gateway-stop", "operations", "signal", "signal", 20,
                cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), close_gateway)
    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop))
    try:
        await runtime.start()
        await probe.start()
        await listeners.start()
        await telemetry.start()
        if config.service is ServiceKind.DISCORD_BOT:
            # Main owns the long-lived Gateway await; never a raw background task.
            if not stopped.is_set():
                await feature.bot.connect(reconnect=True)
        else:
            await stopped.wait()
    finally:
        runtime.health.stop_accepting()
        try:
            async with asyncio.timeout(10):
                await listeners.stop()
                await probe.stop()
                await telemetry.stop()
        finally:
            try:
                report = await runtime.shutdown()
            finally:
                telemetry.flush()
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            require_clean_shutdown(report)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DiscordBot V2 process")
    parser.add_argument("service", choices=("discord-bot", "watch-web"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    args = parser.parse_args(argv)
    handler = build_json_handler()
    logger = logging.getLogger("discordbot")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        settings = load_settings(args.config, args.credentials, args.service)
        actual = args.release.resolve(strict=True)
        store = ReleaseStore(settings.release_root)
        manifest = store.validate(actual.name)
        # The executable's own source must belong to the stated release. Never
        # report a newly switched symlink identity from an old running process.
        if Path(__file__).resolve().parents[4] != actual or store.path(actual.name) != actual:
            raise ValueError("executable release mismatch")
        config = PlatformConfig(ServiceKind(args.service), Environment(settings.environment), manifest["release"],
            ResourceLimits(**dict(settings.limits)), RuntimePolicy(60, 20))
        asyncio.run(run_process(config, settings))
        return 0
    except (AppError, OSError, ValueError):
        logger.error("process.failed")
        return 1
    finally:
        logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
