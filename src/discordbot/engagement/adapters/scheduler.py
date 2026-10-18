"""One supervised periodic owner with injectable sleeps and bounded task leases."""

import asyncio
from collections.abc import Awaitable, Callable
import logging

from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.domain.policy import notification_poll_delay
from discordbot.engagement.ports.events import BirthdayDelivery
from discordbot.platform.errors import AppError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor

logger = logging.getLogger(__name__)


class BirthdayScheduler:
    def __init__(self, service: EngagementService, delivery: BirthdayDelivery, supervisor: TaskSupervisor,
                 *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.service = service
        self.delivery = delivery
        self.supervisor = supervisor
        self.sleep = sleep
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def tick(self) -> None:
        for guild, channel in self.service.config.birthday_channels:
            try:
                await self.service.notify_guild(guild, channel, self.delivery)
            except AppError as exc:
                logger.warning("birthday tick failed: %s", exc.code.value)

    def start(self) -> None:
        if self._running or not self.service.config.birthday_channels:
            return
        self._running = True
        try:
            self._launch()
        except BaseException:
            self._running = False
            raise

    def _launch(self) -> None:
        self._task = self.supervisor.start(TaskSpec(
            name="birthday-clock", owner="engagement", work_id="birthday", correlation_id="engagement-clock",
            deadline_seconds=7200, cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN,
        ), self._run)

    async def _run(self) -> None:
        # Renew a finite task lease once per hour, reserving at most two supervisor slots
        # during handover. Failures do not create unbounded restart loops.
        end = self.service.clock.monotonic() + 3600
        while self._running and self.service.clock.monotonic() < end:
            await self.tick()
            await self.sleep(notification_poll_delay(self.service.clock.now()))
        if self._running:
            self._launch()

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
