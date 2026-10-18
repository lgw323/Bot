"""Optional existing-channel notifications; bounded, redacted, lifecycle owned."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
import logging
import math
import re
import threading
from typing import Any
from uuid import uuid4

from discordbot.platform.errors import AppError, ErrorCode
from discordbot.platform.tasks import CancellationBehavior, TaskSpec

logger = logging.getLogger(__name__)
_delivering = ContextVar('discord_log_delivery', default=False)
EVENTS = frozenset({'database.probe_failed', 'database.probe_recovered', 'task.failed',
    'task.deadline_exceeded', 'runtime.failed', 'process.failed', 'runtime.shutdown_failed'})
ERRORS = frozenset(code.value for code in ErrorCode)
TRANSIENT = ('WSServerHandshakeError', 'ConnectionClosed', 'Invalid response status',
    'WebSocket closed with 1006', 'Disconnected from voice', 'Attempting a reconnect',
    'ClientConnectorError', 'gaierror', 'websockets.exceptions', 'discord.errors.ConnectionClosed')


@dataclass(frozen=True, slots=True)
class Notice:
    title: str
    description: str
    color: int
    attempts: int = 0
    nonce: str = field(default_factory=lambda: uuid4().hex[:24])


def notice(record: logging.LogRecord) -> Notice | None:
    """Never export raw messages, interpolation args, traceback, IDs, or URLs."""
    if record.name == __name__ or _delivering.get():
        return None  # Delivery diagnostics stay local; cannot feed back into this sink.
    fields = getattr(record, 'fields', {})
    fields = fields if isinstance(fields, dict) else {}
    event = fields.get('event', record.msg)
    structured_failure = (record.name.startswith('discordbot.') and fields.get('result') in ('failed', 'deadline_exceeded'))
    if record.levelno < logging.WARNING and not structured_failure:
        return None
    project = record.name == 'discordbot' or record.name.startswith('discordbot.')
    if record.levelno < logging.ERROR and not project:
        return None
    # Match only the format string; do not materialize possibly private args/traceback.
    if record.levelno < logging.ERROR and isinstance(record.msg, str) and any(word in record.msg for word in TRANSIENT):
        return None
    source = record.name if (project and re.fullmatch(r'[a-zA-Z_.]{1,100}', record.name)) else 'external'
    event = event if isinstance(event, str) and event in EVENTS else 'application.log'
    error = fields.get('error_code')
    error = error if isinstance(error, str) and error in ERRORS else 'unspecified'
    is_error = record.levelno >= logging.ERROR or structured_failure
    return Notice('🚨 시스템 오류 발생 (System Error)' if is_error else '⚠️ 시스템 경고 발생 (System Warning)',
        f'Module: {source}\nEvent: {event}\nCode: {error}\n세부 정보는 로컬 journal에서 확인하세요.',
        0xFF0000 if is_error else 0xF1C40F)


class NotificationHandler(logging.Handler):
    def __init__(self, owner: DiscordLogging) -> None:
        super().__init__(logging.INFO)
        self.owner = owner

    def emit(self, record: logging.LogRecord) -> None:
        item = notice(record)
        if item is not None:
            self.owner.enqueue(item)


class DiscordLogging:
    name = 'discord-logging'
    required = False

    def __init__(self, bot: Any, channel: int, clock: Any, supervisor: Any) -> None:
        self.bot, self.channel, self.clock, self.supervisor = bot, channel, clock, supervisor
        self.queue: deque[Notice] = deque()
        self.recent: OrderedDict[str, float] = OrderedDict()
        self.lock = threading.Lock()
        self.handler = NotificationHandler(self)
        self.task = None
        self.closed = True
        self.announced = False
        self.started = False
        self.next_send = 0.0
        self.dropped = self.failures = self.delivered = 0

    def enqueue(self, item: Notice, *, priority: bool = False) -> None:
        with self.lock:
            if self.closed:
                return
            now = self.clock.monotonic()
            key = item.title + item.description
            if key in self.recent and now - self.recent[key] < 60:
                return
            if len(self.queue) >= 32:
                self.dropped += 1
                if not priority:
                    return
                self.queue.pop()
            self.recent[key] = now
            self.recent.move_to_end(key)
            if len(self.recent) > 128:
                self.recent.popitem(last=False)
            if priority:
                self.queue.appendleft(item)
            else:
                self.queue.append(item)

    async def ready(self) -> None:
        if not self.announced and not self.closed:
            self.announced = True
            self.enqueue(Notice('🚀 봇 시스템 구동 시작', '봇이 Discord에 연결되었습니다.', 0x3498DB), priority=True)

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        self.closed = False
        logging.getLogger().addHandler(self.handler)
        self.bot.add_listener(self.ready, 'on_ready')
        self.schedule()

    def schedule(self) -> None:
        if self.closed:
            return
        async def sample() -> None:
            await asyncio.sleep(1)
            await self.deliver_one()
        try:
            self.task = self.supervisor.start(TaskSpec('discord-log-delivery', 'operations', 'notify', 'logging', 8,
                cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN, emit_routine_events=False), sample)
        except AppError:
            self.disable()
            return  # Optional notifications must not unwind the bot's core resources.
        def done(task: Any) -> None:
            if self.closed:
                return
            if not task.cancelled() and task.exception() is None:
                self.schedule()
            else:
                self.disable()
        self.task.add_done_callback(done)

    def disable(self) -> None:
        self.closed = True
        logging.getLogger().removeHandler(self.handler)
        self.bot.remove_listener(self.ready, 'on_ready')
        with self.lock:
            self.dropped += len(self.queue)
            self.queue.clear()
        logger.warning('discord.log_worker_unavailable')

    async def deliver_one(self) -> None:
        if self.closed or not self.bot.is_ready() or self.clock.monotonic() < self.next_send:
            return
        with self.lock:
            if not self.queue:
                return
            item = self.queue.popleft()
        import discord
        self.next_send = self.clock.monotonic() + 5
        context = _delivering.set(True)
        try:
            async with asyncio.timeout(5):
                channel = self.bot.get_channel(self.channel) or await self.bot.fetch_channel(self.channel)
                await channel.send(embed=discord.Embed(title=item.title, description=item.description, color=item.color),
                    allowed_mentions=discord.AllowedMentions.none(), nonce=item.nonce)
            self.delivered += 1
        except Exception as exc:
            self.failures += 1
            # Retry only an explicit rate-limit rejection, once and at most 30s
            # later. No additional application retry on timeouts/5xx. The pinned
            # SDK's internal retries use enforce_nonce with this stable nonce.
            retry = isinstance(exc, discord.RateLimited) or isinstance(exc, discord.HTTPException) and exc.status == 429
            delay = getattr(exc, 'retry_after', 5)
            scheduled = False
            if retry and item.attempts == 0 and type(delay) in (int, float) and math.isfinite(delay) and 0 <= delay <= 30:
                with self.lock:
                    if len(self.queue) < 32:
                        self.queue.appendleft(replace(item, attempts=1))
                        self.next_send = self.clock.monotonic() + max(5, delay)
                        scheduled = True
                    else:
                        self.dropped += 1
            logger.warning('discord.log_delivery_failed', extra={'fields': {'result': 'failed',
                'error_code': 'discord_unavailable', 'retry_scheduled': scheduled}})
        finally:
            _delivering.reset(context)

    def gauges(self) -> dict[str, float]:
        with self.lock:
            return {'discord_log_queue_depth': len(self.queue), 'discord_log_dropped': self.dropped,
                'discord_log_failures': self.failures, 'discord_log_delivered': self.delivered,
                'discord_log_worker_enabled': float(not self.closed)}

    async def stop(self) -> None:
        self.closed = True
        logging.getLogger().removeHandler(self.handler)
        self.bot.remove_listener(self.ready, 'on_ready')
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        with self.lock:
            self.dropped += len(self.queue)
            self.queue.clear()
            self.recent.clear()
        self.handler.close()
