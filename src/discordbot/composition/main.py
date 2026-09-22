"""Explicit service entrypoint: synchronous guardian, private application worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from discordbot.composition.config import Environment, PlatformConfig, ResourceLimits, ServiceKind
from discordbot.composition.guardian import WorkerControl, supervise
from discordbot.composition.runtime import require_clean_shutdown
from discordbot.operations.adapters.configuration import load_settings
from discordbot.operations.adapters.filesystem import ReleaseStore
from discordbot.platform.errors import AppError, ShutdownError
from discordbot.platform.telemetry import build_json_handler


async def run_process(config, settings, control: WorkerControl | None = None):
    if config.service is ServiceKind.DISCORD_BOT:
        from discordbot.composition.production_discord import assemble
    else:
        from discordbot.composition.production_watch import assemble
    runtime, feature, listeners, telemetry, probe = assemble(config, settings)
    if control is not None:
        runtime.shutdown_epoch = control.stopping
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    application = asyncio.current_task()
    closing = False
    gateway = None

    def begin():
        epoch = control.stopping() if control is not None else loop.time()
        return runtime.begin_shutdown(epoch + config.runtime.shutdown_grace_seconds)

    def stop(*, cancel_application: bool = True):
        nonlocal closing, gateway
        if closing:
            return
        closing = True
        begin()
        stopped.set()
        if config.service is ServiceKind.DISCORD_BOT:
            async def close_gateway():
                try:
                    if feature.deferred is not None:
                        await feature.deferred.stop()
                finally:
                    await feature.bot.close()
            gateway = runtime.lifecycle.start(close_gateway(), name="gateway-stop")
        if cancel_application and application is not None:
            application.cancel()

    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop))
    try:
        await runtime.start()
        await probe.start()
        await listeners.start()
        await telemetry.start()
        if control is not None:
            control.send(b"S")
        if config.service is ServiceKind.DISCORD_BOT:
            if not stopped.is_set():
                await feature.bot.connect(reconnect=True)
        else:
            await stopped.wait()
    except asyncio.CancelledError:
        if not closing and (control is None or control.epoch is None):
            raise
        stop(cancel_application=False)
    finally:
        deadline = begin()
        closing = True
        errors = []
        try:
            if gateway is not None:
                await runtime.lifecycle.observe(gateway, deadline=deadline)
            for name, component in (("listeners", listeners), ("probe", probe), ("telemetry", telemetry)):
                await runtime.lifecycle.run(component.stop(), name=name + "-stop", deadline=deadline)
        except (Exception, asyncio.CancelledError) as exc:
            errors.append(type(exc).__name__)
            runtime._cleanup_failed = True
        try:
            report = await runtime.shutdown()
            require_clean_shutdown(report)
            if errors:
                raise ShutdownError("entrypoint cleanup failed")
        except (Exception, asyncio.CancelledError):
            if control is not None:
                control.send(b"A")
            raise
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            telemetry.flush()


def worker_main(argv: list[str], control: WorkerControl) -> int:
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
        if Path(__file__).resolve().parents[4] != actual or store.path(actual.name) != actual:
            raise ValueError("executable release mismatch")
        config = PlatformConfig(ServiceKind(args.service), Environment(settings.environment), manifest["release"],
            ResourceLimits(**dict(settings.limits)), control.policy.runtime())
        from discordbot.composition.worker import run_managed
        return run_managed(lambda channel: run_process(config, settings, channel), control)
    except (AppError, OSError, ValueError):
        control.stopping()
        control.send(b"F")
        logger.error("process.failed")
        return 1
    finally:
        logger.removeHandler(handler)
        handler.close()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    source = str(Path(__file__).resolve().parents[2])
    bootstrap = "import sys; sys.path.insert(0, sys.argv.pop(1)); from discordbot.composition.worker import main; raise SystemExit(main())"
    return supervise(lambda fd: [sys.executable, "-I", "-B", "-c", bootstrap, source, str(fd), *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
