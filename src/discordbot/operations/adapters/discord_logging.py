"""Optional existing-channel notifications; bounded, redacted, lifecycle owned."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import logging
import math
import re
import threading
from typing import Any
from uuid import uuid4

from discordbot.platform.diagnostics import EXCEPTION_TYPES
from discordbot.storage.adapters.probe_diagnostics import safe_probe_fields
from discordbot.platform.errors import AppError, ErrorCode
from discordbot.platform.tasks import CancellationBehavior, TaskSpec

logger = logging.getLogger(__name__)
_delivering = ContextVar('discord_log_delivery', default=False)
EVENTS = frozenset({'database.probe_failed', 'database.probe_contention', 'database.probe_recovered',
    'music.command_failed', 'music.work_failed', 'music.ui_failed', 'music.decoder_failed',
    'music.smoke_failed', 'task.failed', 'task.deadline_exceeded', 'runtime.failed',
    'process.failed', 'runtime.shutdown_failed', 'summary.request', 'summary.response',
    'summary.preload', 'watch.invite', 'watch.maintenance', 'watch.shutdown', 'watch.metadata'})
STAGES = frozenset('connect enqueue lookup started ended result tts leave close control prepare start retry '
    'prefetch autoplay reconnect disconnect speech restore action pcm_decode live_smoke probe shutdown empty join-tts '
    'request message_request selection'.split())
STATES = frozenset('idle preparing starting playing paused retry disconnected tts tts_starting connecting'.split())
DISPOSITIONS = frozenset('bounded_busy hard deadline_pending recovery_expired'.split())
ERRORS = frozenset(code.value for code in ErrorCode)
# Feature emitters use typed result codes as well as the common failed result.
# Admit only known operational outcomes; expected user rejection/cancellation and
# cleanup-pending observations do not become new error notifications.
FAILURE_RESULTS = {
    'summary.request': ERRORS - {'validation', 'authorization', 'not_found', 'conflict', 'cancellation'},
    'summary.response': frozenset({'delivery_failed'}),
    'watch.shutdown': frozenset({'deadline', 'uncertain_close'}),
    'watch.metadata': frozenset({'unavailable'}),
}
RESULTS = ERRORS | frozenset({'failed', 'success', 'delivery_failed', 'deadline', 'uncertain_close', 'unavailable'})
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
    dedup_key: str = ""


def diagnostic_fields(fields: dict[str, Any]) -> dict[str, str | int | bool]:
    """Revalidate exported fields; private text is never a fallback."""
    safe = safe_probe_fields(fields)
    safe.pop('operation', None)  # Also handles non-database events.
    choices = {'stage': STAGES, 'state_before': STATES, 'state_after': STATES, 'result': RESULTS,
        'exception_type': EXCEPTION_TYPES | {'unexpected'}, 'cause_type': EXCEPTION_TYPES | {'unexpected'},
        'probe_disposition': DISPOSITIONS,
        'reason': frozenset('executable_not_found process_start_failure process_io_failure child_nonzero '
            'provider_rejected auth_required no_audio_format download_failed http_forbidden timeout '
            'invalid_output empty_output cache_read_failure cache_write_failure cache_publish_failure '
            'output_limit js_runtime_missing http_rate_limited http_server_error http_rejected transport_error'.split())}
    for key, allowed in choices.items():
        value = fields.get(key)
        if isinstance(value, str) and value in allowed:
            safe[key] = value
    for key in ('voice_connected', 'probe_recovery_safe'):
        if type(fields.get(key)) is bool:
            safe[key] = fields[key]
    for key in ('healthy_probes', 'read_admitted', 'write_admitted'):
        value = fields.get(key)
        if type(value) is int and 0 <= value <= 100000:
            safe[key] = value
    value = fields.get('child_exit_code')
    if type(value) is int and -255 <= value <= 255:
        safe['child_exit_code'] = value
    value = fields.get('http_status')
    if type(value) is int and 100 <= value <= 599:
        safe['http_status'] = value
    for key in ('work_id', 'incident_id'):
        value = fields.get(key)
        if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value):
            safe[key] = value
    return safe


def notice(record: logging.LogRecord) -> Notice | None:
    """Export bounded diagnostics without messages, arguments, traceback or IDs."""
    if record.name == __name__ or _delivering.get():
        return None
    fields = getattr(record, 'fields', {})
    fields = fields if isinstance(fields, dict) else {}
    event = fields.get('event', record.msg)
    result = fields.get('result')
    project = record.name == 'discordbot' or record.name.startswith('discordbot.')
    recovered = project and event == 'database.probe_recovered' and result == 'success'
    feature_failure = (project and isinstance(event, str) and isinstance(result, str)
        and result in FAILURE_RESULTS.get(event, ()))
    structured_failure = project and (result in ('failed', 'deadline_exceeded') or feature_failure)
    if record.levelno < logging.WARNING and not structured_failure and not recovered:
        return None
    if record.levelno < logging.ERROR and not project:
        return None
    if record.levelno < logging.ERROR and isinstance(record.msg, str) and any(word in record.msg for word in TRANSIENT):
        return None
    source = record.name if (project and re.fullmatch(r'[a-zA-Z_.]{1,100}', record.name)) else 'external'
    event = event if isinstance(event, str) and event in EVENTS else 'application.log'
    error = fields.get('error_code')
    if not isinstance(error, str) or error not in ERRORS:
        # A typed result is the code when the emitter did not supply one. Do not
        # invent a cause for generic delivery/cleanup failure observations.
        error = (result if feature_failure and result in ERRORS else
            'deadline_exceeded' if project and event == 'watch.shutdown' and result == 'deadline'
            else 'unspecified')
    safe = diagnostic_fields(fields) if project else {}
    disposition = safe.get('probe_disposition')
    recovery = ('recovered' if recovered else 'pending' if disposition in {'bounded_busy', 'deadline_pending'}
        else 'latched; operator review required' if disposition in {'hard', 'recovery_expired'} else 'unconfirmed')
    is_error = not recovered and (record.levelno >= logging.ERROR or structured_failure and disposition != 'bounded_busy')
    stamp = datetime.fromtimestamp(record.created, timezone.utc)
    supplied_time = fields.get('timestamp')
    if project and isinstance(supplied_time, str) and len(supplied_time) <= 40:
        try:
            parsed = datetime.fromisoformat(supplied_time)
            if parsed.tzinfo is not None:
                stamp = parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    feature = event.split('.')[0] if event != 'application.log' else 'application'
    lines = [f'Time: {stamp.isoformat(timespec="seconds")}', f'Feature: {feature}',
        f'Module: {source}', f'Event: {event}', f'Code: {error}', f'Recovery: {recovery}']
    lines.extend(f'{key}: {value}' for key, value in safe.items())
    stable = [source, event, error, recovery] + [f'{key}={value}' for key, value in sorted(safe.items())
        if key not in {'work_id', 'incident_id', 'read_admitted', 'write_admitted'}]
    title = 'DB 회복 확인' if recovered else '시스템 오류 (System Error)' if is_error else '시스템 경고 (System Warning)'
    return Notice(title, '```text\n' + '\n'.join(lines) + '\n```',
        0x2ECC71 if recovered else 0xFF0000 if is_error else 0xF1C40F, dedup_key='|'.join(stable))


class NotificationHandler(logging.Handler):
    def __init__(self, owner: DiscordLogging) -> None:
        super().__init__(logging.INFO)
        self.owner = owner

    def emit(self, record: logging.LogRecord) -> None:
        try:
            item = notice(record)
            if item is not None:
                self.owner.enqueue(item)
        except Exception:
            # Optional diagnostics must never replace the caller's exception or
            # abort command completion. Do not call handleError/re-log: both may
            # expose the original private record or recurse into this handler.
            with self.owner.lock:
                self.owner.format_failures += 1
                self.owner.dropped += 1


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
        self.format_failures = 0

    def enqueue(self, item: Notice, *, priority: bool = False) -> None:
        with self.lock:
            if self.closed:
                return
            now = self.clock.monotonic()
            key = item.dedup_key or item.title + item.description
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
                await channel.send(content=item.description, embed=discord.Embed(title=item.title, color=item.color),
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
                'discord_log_format_failures': self.format_failures,
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
