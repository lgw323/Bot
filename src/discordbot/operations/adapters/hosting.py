"""Local health/metrics and explicit server lifecycle. Framework owns request tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

from discordbot.platform.errors import ShutdownError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor


def metrics_text(metrics: Any, gauges: dict[str, float]) -> str:
    rows = []
    for (name, labels), value in metrics.snapshot().items():
        if not re.fullmatch(r"[a-zA-Z_:][a-zA-Z0-9_:]*", name):
            continue
        encoded = ",".join(f'{key}={json.dumps(label)}' for key, label in labels
                           if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", key))
        rows.append(f"{name}" + ("{" + encoded + "}" if encoded else "") + f" {value}")
    rows.extend(f"{key} {float(value)}" for key, value in gauges.items()
                if re.fullmatch(r"[a-zA-Z_:][a-zA-Z0-9_:]*", key))
    return "\n".join(rows) + "\n"


def health_app(runtime: Any, readiness: Callable[[], bool], gauges: Callable[[], dict[str, float]]):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, PlainTextResponse
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health/live")
    async def live():
        return {"live": runtime.health.snapshot().live, "release": runtime.config.release,
                "service": runtime.config.service.value}

    @app.get("/health/ready")
    async def ready():
        available = runtime.health.snapshot().ready and readiness()
        return JSONResponse({"ready": available, "release": runtime.config.release,
                             "service": runtime.config.service.value}, status_code=200 if available else 503)

    @app.get("/metrics")
    async def metrics():
        return PlainTextResponse(metrics_text(runtime.metrics, gauges()), media_type="text/plain; version=0.0.4")

    return app


class Servers:
    """Uvicorn sockets with an externally owned process lifetime, not serve() tasks.

    on_tick maintenance is renewed through bounded supervisor work. Explicit
    startup/shutdown avoids Uvicorn taking over SIGTERM or enforcing task TTL on
    the process lifetime. Private lifecycle API is pinned and tested in staging.
    """
    name = "listeners"
    required = True

    def __init__(self, servers: tuple[Any, ...], supervisor: TaskSupervisor) -> None:
        self.servers, self.supervisor = servers, supervisor
        self.started: list[Any] = []
        self.tick = None
        self.closed = False

    async def start(self) -> None:
        try:
            for server in self.servers:
                if not server.config.loaded:
                    server.config.load()
                server.lifespan = server.config.lifespan_class(server.config)
                await server.startup()
                if not server.started:
                    raise ShutdownError("listener startup failed")
                self.started.append(server)
            self.schedule()
        except BaseException:
            await self.stop()
            raise

    def schedule(self) -> None:
        if self.closed:
            return
        async def tick():
            await asyncio.sleep(1)
            for server in self.started:
                if await server.on_tick(0):
                    raise ShutdownError("listener requested shutdown")
        self.tick = self.supervisor.start(TaskSpec("server-maintenance", "listeners", "tick", "listeners", 5,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN, emit_routine_events=False), tick)
        def done(task):
            if not task.cancelled() and task.exception() is None:
                self.schedule()
        self.tick.add_done_callback(done)

    def ready(self) -> bool:
        return (not self.closed and len(self.started) == len(self.servers)
                and all(s.started and not s.should_exit for s in self.started)
                and self.tick is not None and not self.tick.done())

    async def stop(self) -> None:
        self.closed = True
        if self.tick:
            self.tick.cancel()
            await asyncio.gather(self.tick, return_exceptions=True)
        for server in reversed(self.started):
            server.should_exit = True
            await server.shutdown()
        self.started.clear()


def server(app: Any, port: int):
    import uvicorn
    return uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_config=None,
        proxy_headers=False, lifespan="off", limit_concurrency=16, backlog=16, timeout_keep_alive=2,
        timeout_graceful_shutdown=5))


class Gateway:
    name = "gateway"
    required = True

    def __init__(self, bot: Any, token: str) -> None:
        self.bot, self.token = bot, token

    async def start(self) -> None:
        # login validates the secret, but connect is explicitly awaited by main.
        await self.bot.login(self.token)

    async def stop(self) -> None:
        await self.bot.close()


class DeferredMusic:
    """Voice restoration waits for Gateway guild/channel caches before starting."""
    name = "music"
    required = True

    def __init__(self, music: Any, bot: Any, supervisor: TaskSupervisor) -> None:
        self.music, self.bot, self.supervisor = music, bot, supervisor
        self.work = None
        self.started = False
        self.failed = False

    async def start(self) -> None:
        self.bot.add_listener(self.ready, "on_ready")

    async def ready(self) -> None:
        if self.started or self.work is not None:
            return
        async def initialize():
            try:
                await self.music.start()
                await self.bot.tree.sync()
                self.started = True
            except BaseException:
                self.failed = True
                raise
        self.work = self.supervisor.start(TaskSpec("music-initialize", "music", "startup", "startup", 60,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), initialize)

    async def stop(self) -> None:
        self.bot.remove_listener(self.ready, "on_ready")
        if self.work and not self.work.done():
            self.work.cancel()
            await asyncio.gather(self.work, return_exceptions=True)
        await self.music.stop()
        if self.music.error == "shutdown_checkpoint_failed":
            raise ShutdownError("Music checkpoint failed")


class TelemetryDrain:
    name = "telemetry"
    required = True

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.closed = False
        self.task = None

    def flush(self) -> None:
        logger = logging.getLogger("discordbot.events")
        for item in self.runtime.telemetry_buffer.drain(128):
            logger.info(item.event, extra={"fields": item.as_dict()})

    async def start(self) -> None:
        self.schedule()

    def schedule(self) -> None:
        if self.closed:
            return
        async def drain():
            await asyncio.sleep(1)
            self.flush()
        self.task = self.runtime.supervisor.start(TaskSpec("telemetry-drain", "operations", "drain", "telemetry", 5,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN, emit_routine_events=False), drain)
        self.task.add_done_callback(lambda task: self.schedule() if not task.cancelled() and task.exception() is None else None)

    async def stop(self) -> None:
        self.closed = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.flush()
