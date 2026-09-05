import asyncio

import pytest

from discordbot.composition.config import (
    Environment,
    PlatformConfig,
    ResourceLimits,
    RuntimePolicy,
    ServiceKind,
)
from discordbot.composition.discord_app import build_discord_runtime
from discordbot.composition.runtime import RuntimeState, require_clean_shutdown
from discordbot.composition.watch_app import build_watch_runtime
from discordbot.platform.errors import ConfigurationError, StartupError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec


class FakeResource:
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        required: bool = True,
        fail_start: bool = False,
        fail_stop: bool = False,
    ) -> None:
        self.name = name
        self.required = required
        self._events = events
        self._fail_start = fail_start
        self._fail_stop = fail_stop

    async def start(self) -> None:
        self._events.append(f"start:{self.name}")
        if self._fail_start:
            raise RuntimeError("start failed")

    async def stop(self) -> None:
        self._events.append(f"stop:{self.name}")
        if self._fail_stop:
            raise RuntimeError("stop failed")


def _config(service: ServiceKind) -> PlatformConfig:
    return PlatformConfig(
        service=service,
        environment=Environment.TEST,
        release="unit",
        limits=ResourceLimits(
            task_capacity=4,
            telemetry_queue_capacity=32,
            metrics_series_capacity=16,
            executor_workers=1,
            executor_queue_capacity=1,
        ),
        runtime=RuntimePolicy(
            startup_timeout_seconds=1,
            shutdown_grace_seconds=0.1,
        ),
    )


@pytest.mark.asyncio
async def test_discord_runtime_starts_in_order_and_shuts_down_in_reverse() -> None:
    events: list[str] = []
    resources = (
        FakeResource("sqlite", events),
        FakeResource("discord_gateway", events),
    )
    runtime = build_discord_runtime(_config(ServiceKind.DISCORD_BOT), resources=resources)

    assert runtime.state is RuntimeState.NEW
    await runtime.start()
    assert runtime.state is RuntimeState.RUNNING
    assert runtime.health.ready_payload()["ready"] is True

    cancelled = asyncio.Event()

    async def background() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    runtime.supervisor.start(
        TaskSpec(
            name="background",
            owner="platform",
            work_id="job-1",
            correlation_id="request-1",
            deadline_seconds=60,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN,
        ),
        background,
    )
    await asyncio.sleep(0)

    report = await runtime.shutdown()
    require_clean_shutdown(report)

    assert cancelled.is_set()
    assert report.tasks.remaining == 0
    assert runtime.state is RuntimeState.STOPPED
    assert runtime.health.live_payload() == {"live": False}
    assert events == [
        "start:sqlite",
        "start:discord_gateway",
        "stop:discord_gateway",
        "stop:sqlite",
    ]


@pytest.mark.asyncio
async def test_startup_failure_rolls_back_started_resources() -> None:
    events: list[str] = []
    runtime = build_watch_runtime(
        _config(ServiceKind.WATCH_WEB),
        resources=(
            FakeResource("sqlite", events),
            FakeResource("http_server", events, fail_start=True),
        ),
    )

    with pytest.raises(StartupError):
        await runtime.start()
    assert runtime.state is RuntimeState.FAILED
    assert runtime.health.ready_payload()["ready"] is False
    assert events == ["start:sqlite", "start:http_server", "stop:sqlite"]

    report = await runtime.shutdown()
    require_clean_shutdown(report)
    assert runtime.state is RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_discord_and_watch_have_independent_composition_roots() -> None:
    discord = build_discord_runtime(_config(ServiceKind.DISCORD_BOT))
    watch = build_watch_runtime(_config(ServiceKind.WATCH_WEB))

    assert discord is not watch
    assert discord.supervisor is not watch.supervisor
    assert discord.config.service is ServiceKind.DISCORD_BOT
    assert watch.config.service is ServiceKind.WATCH_WEB

    await discord.start()
    await watch.start()
    require_clean_shutdown(await discord.shutdown())
    require_clean_shutdown(await watch.shutdown())


def test_composition_rejects_wrong_service_config() -> None:
    with pytest.raises(ConfigurationError, match="discord composition"):
        build_discord_runtime(_config(ServiceKind.WATCH_WEB))
    with pytest.raises(ConfigurationError, match="watch composition"):
        build_watch_runtime(_config(ServiceKind.DISCORD_BOT))
