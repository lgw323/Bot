"""Synthetic dependencies shared by V2 Summary contract/integration tests."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from discordbot.platform.errors import AuthorizationError
from discordbot.platform.tasks import TaskSupervisor
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.summary.application.capture import Capture
from discordbot.summary.application.service import SummaryService
from discordbot.summary.domain.models import Message, Scope, Summary, SummaryConfig, Topic


@dataclass
class Clock:
    tick: float = 1000.0

    def now(self):
        return datetime(2026, 9, 6, tzinfo=timezone.utc) + timedelta(seconds=self.tick - 1000)

    def monotonic(self):
        return self.tick


class IDs:
    counter = 0

    def new_id(self):
        self.counter += 1
        return f"synthetic-{self.counter}"


class Timers:
    def __init__(self):
        self.contexts = []
        self.durations = []

    def __call__(self, seconds):
        timer = asyncio.timeout(seconds)
        self.contexts.append(timer)
        self.durations.append(seconds)
        return timer

    def expire(self, index=0):
        self.contexts[index].reschedule(asyncio.get_running_loop().time())


def interaction(*, guild=100, channel=200, user=300, message=500):
    item = SimpleNamespace(guild=SimpleNamespace(id=guild) if guild else None,
        channel_id=channel, user=SimpleNamespace(id=user, display_name="합성 사용자"),
        message=SimpleNamespace(id=message), data={"values": []},
        response=SimpleNamespace(is_done=MagicMock(return_value=False), defer=AsyncMock(),
            send_message=AsyncMock(), send_modal=AsyncMock(), edit_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=message))))
    return item


def harness(*, config=None, topics=1):
    clock = Clock()
    config = config or SummaryConfig((Scope(100, 200), Scope(101, 201)))
    capture = Capture(config, clock)
    authorization = SimpleNamespace(require=AsyncMock())
    provider = SimpleNamespace(generate=AsyncMock(return_value=Summary("전체 요약",
        tuple(Topic(f"주제 {i}") for i in range(topics)), 12)), close=AsyncMock())
    supervisor = TaskSupervisor(capacity=5, history_capacity=32, clock=clock)
    buffer = TelemetryBuffer(128)
    telemetry = TelemetryEmitter(buffer=buffer, clock=clock, service="discord-bot", environment="test", release="test")
    timers = Timers()
    # This fixture supplies a complete synthetic capture directly; runtime tests
    # exercise the default required-preload gate with a fake history adapter.
    service = SummaryService(config, clock, IDs(), capture, authorization, provider, supervisor, telemetry,
                             timeout=timers, require_preload=False)
    for scope in config.sources:
        capture.add(Message(scope, 1, clock.now(), "합성 사용자", "합성 대화"))
    return SimpleNamespace(service=service, capture=capture, clock=clock, config=config,
        authorization=authorization, provider=provider, supervisor=supervisor, buffer=buffer, timers=timers)


async def settled():
    # Explicit loop turns only for completion callbacks, never a wall-clock race.
    for _ in range(4):
        await asyncio.sleep(0)
