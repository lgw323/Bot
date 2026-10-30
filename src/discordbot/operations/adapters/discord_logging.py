"""Optional existing-channel notifications; bounded, redacted, lifecycle owned."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import logging
import math
import re
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from discordbot.platform.diagnostics import EXCEPTION_TYPES, exception_fields, safe_exception_fields
from discordbot.platform.diagnostic_locations import PUBLIC_FRAME_PATHS
from discordbot.platform.context import current_correlation
from discordbot.storage.adapters.probe_diagnostics import safe_probe_fields
from discordbot.platform.errors import AppError, ErrorCode
from discordbot.platform.tasks import CancellationBehavior, TaskSpec
from discordbot.operations.adapters.operation_notifications import (
    OperationNotifications, operation_key, result_message, startup_description,
)

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
EXTERNAL_SOURCES = frozenset({'discord.client', 'discord.gateway', 'discord.http',
    'discord.voice_client', 'discord.voice_state', 'aiohttp.client', 'aiohttp.connector'})
PROJECT_SOURCES = frozenset(path[:-3].replace('/', '.').removesuffix('.__init__')
    for path in PUBLIC_FRAME_PATHS if path.startswith('discordbot/')) | {'discordbot', 'discordbot.events', 'discordbot.watch.web'}


@dataclass(frozen=True, slots=True)
class Notice:
    title: str
    description: str
    color: int
    attempts: int = 0
    nonce: str = field(default_factory=lambda: uuid4().hex[:24])
    dedup_key: str = ""
    receipt: str = ""  # Validated operational outcome key, never an interaction payload.


def diagnostic_fields(fields: dict[str, Any]) -> dict[str, object]:
    """Revalidate exported fields; private text is never a fallback."""
    safe = {key:value for key,value in safe_probe_fields(fields).items()
            if type(value) in (str, int, bool)}
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
        if type(value) is str and value in allowed:
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
    value = fields.get('retry_delay_seconds')
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400:
        safe['retry_delay_seconds'] = round(value, 2)
    if fields.get('reconnect_scheduled') is True:
        safe['reconnect_scheduled'] = True
    for key in ('work_id', 'incident_id'):
        value = fields.get(key)
        if type(value) is str and re.fullmatch(r'[a-f0-9]{32}', value):
            safe[key] = value
    safe.update(safe_exception_fields(fields))
    return safe


def _utf16_size(value: str) -> int:
    return len(value.encode('utf-16-le')) // 2


def _summary(error: str, safe: dict[str, object], recovered: bool) -> str:
    """Fixed explanatory templates, never interpolated exception text."""
    if recovered:
        return 'DB 회복을 확인했습니다. 현재 작업 가능 상태를 확인하세요.'
    if safe.get('probe_disposition') == 'bounded_busy':
        return 'DB가 일시적으로 사용 중입니다. 제한된 복구 확인을 기다리고 있습니다.'
    status = safe.get('http_status')
    if status == 429:
        return '외부 서비스가 요청을 제한했습니다(HTTP 429). 재시도 대기 상태를 확인하세요.'
    if type(status) is int and status >= 500:
        return f'외부 서비스가 HTTP {status} 응답을 반환했습니다. 제공자 상태를 확인하세요. 세부 원인은 미확정입니다.'
    if type(status) is int and status >= 400:
        return f'외부 서비스가 HTTP {status} 응답을 반환했습니다. 요청·접근 조건을 확인하세요.'
    if error == 'deadline_exceeded' or safe.get('exception_type') in {'TimeoutError', 'ServerTimeoutError', 'SocketTimeoutError', 'ConnectionTimeoutError'}:
        return '작업 또는 외부 응답 대기 시간이 초과됐습니다. 지연의 세부 원인은 미확정입니다.'
    if error in {'database_unavailable', 'data_integrity'}:
        return 'DB 작업을 완료하지 못했습니다. 단계·SQLite 분류와 복구 상태를 확인하세요.'
    if error == 'capacity':
        return '처리 용량이 부족합니다. 대기 작업과 자원 사용량을 확인하세요.'
    if error in {'external_temporary', 'external_permanent'}:
        return '외부 연동을 완료하지 못했습니다. 연결 상태와 아래 분류를 확인하세요. 세부 원인은 미확정입니다.'
    return '작업을 완료하지 못했습니다. 오류 코드와 공개 코드 위치를 함께 확인하세요. 세부 원인은 미확정입니다.'


def _bounded_block(core: list[str], details: list[str]) -> str:
    """Keep identity and useful leading details; clip whole lines before the fence."""
    opening, closing = '```text\n', '\n```'
    marker = '… 상세 일부 생략 (Discord 길이 제한)'
    lines = list(core)
    for index, line in enumerate(details):
        trial = opening + '\n'.join([*lines, line]) + closing
        reserve = _utf16_size('\n' + marker) if index + 1 < len(details) else 0
        if _utf16_size(trial) + reserve > 2000:
            lines.append(marker)
            break
        lines.append(line)
    return opening + '\n'.join(lines) + closing


def notice(record: logging.LogRecord) -> Notice | None:
    """Export safe classified evidence, never raw messages, arguments or traceback text."""
    name = record.name if type(record.name) is str else 'external'
    if name == __name__ or _delivering.get():
        return None
    fields = getattr(record, 'fields', {})
    fields = fields if isinstance(fields, dict) else {}
    event = fields.get('event', record.msg)
    result = fields.get('result')
    event = event if type(event) is str else None
    result = result if type(result) is str else None
    project = name == 'discordbot' or name.startswith('discordbot.')
    recovered = project and event == 'database.probe_recovered' and result == 'success'
    feature_failure = (project and type(event) is str and type(result) is str
        and result in FAILURE_RESULTS.get(event, ()))
    structured_failure = project and (result in ('failed', 'deadline_exceeded') or feature_failure)
    if record.levelno < logging.WARNING and not structured_failure and not recovered:
        return None
    if record.levelno < logging.ERROR and not project:
        return None
    if record.levelno < logging.ERROR and type(record.msg) is str and any(word in record.msg for word in TRANSIENT):
        return None
    source = name if name in PROJECT_SOURCES | EXTERNAL_SOURCES else 'discordbot' if project else 'external'
    event = event if type(event) is str and event in EVENTS else 'application.log'
    error = fields.get('error_code')
    if type(error) is not str or error not in ERRORS:
        # A typed result is the code when the emitter did not supply one. Do not
        # invent a cause for generic delivery/cleanup failure observations.
        error = (result if feature_failure and result in ERRORS else
            'deadline_exceeded' if project and event == 'watch.shutdown' and result == 'deadline'
            else 'unspecified')
    safe = diagnostic_fields(fields) if project else {}
    info = record.exc_info
    if type(info) is tuple and len(info) == 3 and isinstance(info[1], BaseException):
        # Third-party discord.client errors do not use our structured emitters.
        # Capture only allowlisted categories/public frames from the actual error.
        safe.update(safe_exception_fields(exception_fields(info[1])))
    if (source == 'discord.client' and type(record.msg) is str and record.msg == 'Attempting a reconnect in %.2fs'
            and type(record.args) is tuple and len(record.args) == 1):
        # Exact pinned SDK template only. Never format/interpolate library text.
        retry = diagnostic_fields({'retry_delay_seconds': record.args[0]})
        if 'retry_delay_seconds' in retry:
            safe.update(retry, reconnect_scheduled=True)
    if 'correlation_id' not in safe:
        context = current_correlation()
        if context is not None:
            safe.update(safe_exception_fields({'correlation_id': context.correlation_id}))
    if error == 'unspecified' and type(safe.get('http_status')) is int and safe['http_status'] >= 400:
        error = 'external_temporary' if safe['http_status'] == 429 or safe['http_status'] >= 500 else 'external_permanent'
    disposition = safe.get('probe_disposition')
    recovery = ('recovered' if recovered else 'pending' if disposition in {'bounded_busy', 'deadline_pending'} or safe.get('reconnect_scheduled')
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
    feature = event.split('.')[0] if event != 'application.log' else source.split('.')[0] if source in EXTERNAL_SOURCES else 'application'
    lines = [f'Summary: {_summary(error, safe, recovered)}',
        f'Severity: {"RECOVERED" if recovered else "ERROR" if is_error else "WARNING"}',
        f'Time: {stamp.isoformat(timespec="seconds")}', f'Feature: {feature}',
        f'Module: {source}', f'Event: {event}', f'Code: {error}', f'Recovery: {recovery}',
        f'Correlation: {safe.get("correlation_id", "미제공") }']
    details = [f'{key}: {value}' for key, value in safe.items()
        if key not in {'stack_frames', 'exception_chain', 'chain_relations', 'correlation_id'}]
    if 'exception_chain' in safe:
        chain, links = safe['exception_chain'], safe.get('chain_relations', ())
        path = chain[0]
        for index, kind in enumerate(chain[1:]):
            relation = links[index] if index < len(links) else 'relation_unconfirmed'
            path += f' --{relation}--> {kind}'
        details.append('exception_chain: ' + path)
    if 'stack_frames' in safe:
        details.append('Stack (공개 코드 위치, 소스·로컬값 제외):')
        details.extend('  at ' + value for value in safe['stack_frames'])
    if safe.get('trace_limited'):
        details.append('Trace: 일부 위치·원인은 비공개/상한 때문에 생략됨. 전체 traceback이 아닙니다.')
    stable = [source, event, error, recovery] + [f'{key}={value}' for key, value in sorted(safe.items())
        if key not in {'work_id', 'incident_id', 'correlation_id', 'retry_delay_seconds', 'read_admitted', 'write_admitted'}]
    title = 'DB 회복 확인' if recovered else '시스템 오류 (System Error)' if is_error else '시스템 경고 (System Warning)'
    return Notice(title, _bounded_block(lines, details),
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

    def __init__(self, bot: Any, channel: int, clock: Any, supervisor: Any, *,
                 state: Path | None = None, executor: Any | None = None, release: str = 'unknown') -> None:
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
        if (state is None) != (executor is None):
            raise ValueError('operational notices require both state and bounded executor')
        self.operations = OperationNotifications(state, executor) if state is not None else None
        self.release = release
        self.disconnected_at: float | None = None
        self.reconnects = self.uncertain = self.suppressed = self.storage_failures = self.retries = 0
        self.next_operation_poll = 0.0

    def enqueue(self, item: Notice, *, priority: bool = False) -> bool:
        with self.lock:
            if self.closed:
                return False
            now = self.clock.monotonic()
            key = item.dedup_key or item.title + item.description
            if key in self.recent and now - self.recent[key] < 60:
                self.suppressed += 1
                return False
            if len(self.queue) >= 32:
                self.dropped += 1
                if not priority:
                    return False
                displaced = self.queue.pop()
                if self.operations is not None and displaced.receipt == self.operations.queued:
                    self.operations.queued = None
            self.recent[key] = now
            self.recent.move_to_end(key)
            if len(self.recent) > 128:
                self.recent.popitem(last=False)
            if priority:
                self.queue.appendleft(item)
            else:
                self.queue.append(item)
            return True

    def _now(self) -> datetime:
        return self.clock.now() if hasattr(self.clock, 'now') else datetime.now(timezone.utc)

    async def poll_operations(self) -> None:
        if self.operations is None or self.closed or self.clock.monotonic() < self.next_operation_poll:
            return
        self.next_operation_poll = self.clock.monotonic() + 5
        try:
            async with asyncio.timeout(2):
                row = await self.operations.snapshot(self._now())
            if row is not None:
                key = operation_key(row)
                title, text, color = result_message(row)
                item = Notice(title, text, color, nonce=hashlib.sha256(key.encode()).hexdigest()[:24],
                              dedup_key='operation:' + key, receipt=key)
                if self.enqueue(item):
                    self.operations.admitted(row)
        except Exception:
            # Optional, bounded metadata cannot replace the caller's failure or
            # leak raw corrupt data/paths to another logging handler.
            self.storage_failures += 1
            self.next_operation_poll = self.clock.monotonic() + 60

    async def ready(self) -> None:
        if self.closed:
            return
        if not self.announced:
            await self.poll_operations()
            self.announced = True
            row = self.operations.current if self.operations is not None else None
            self.enqueue(Notice('🚀 봇 Discord 연결 확인',
                startup_description(self.release, row, self._now()), 0x3498DB,
                dedup_key='lifecycle:first-connection'), priority=True)
        elif self.disconnected_at is not None:
            elapsed = min(7 * 86400, max(0, int(self.clock.monotonic() - self.disconnected_at)))
            self.reconnects += 1
            self.enqueue(Notice('🟢 Discord 연결 회복',
                f'관측된 연결 중단 약 {elapsed}초 후 연결이 회복되었습니다.\n'
                '연결 중단 원인은 확인되지 않았습니다. 전체 서비스 준비 상태는 별도 확인이 필요합니다.',
                0x2ECC71, dedup_key='lifecycle:reconnected'), priority=True)
        self.disconnected_at = None

    async def disconnected(self) -> None:
        if not self.closed and self.announced and self.disconnected_at is None:
            self.disconnected_at = self.clock.monotonic()

    async def resumed(self) -> None:
        await self.ready()  # Shared state prevents resumed+ready double announcements.

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        self.closed = False
        logging.getLogger().addHandler(self.handler)
        self.bot.add_listener(self.ready, 'on_ready')
        self.bot.add_listener(self.disconnected, 'on_disconnect')
        self.bot.add_listener(self.resumed, 'on_resumed')
        self.schedule()

    def schedule(self) -> None:
        if self.closed:
            return
        async def sample() -> None:
            await asyncio.sleep(1)
            await self.poll_operations()
            await self.deliver_one()
        try:
            self.task = self.supervisor.start(TaskSpec('discord-log-delivery', 'operations', 'notify', 'logging', 15,
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
        self.bot.remove_listener(self.disconnected, 'on_disconnect')
        self.bot.remove_listener(self.resumed, 'on_resumed')
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
        if item.receipt:
            if self.operations is None:
                self.dropped += 1
                return
            try:
                async with asyncio.timeout(2):
                    await self.operations.claim(item.receipt)
            except asyncio.CancelledError:
                self.dropped += 1
                raise
            except Exception:
                self.storage_failures += 1
                self.dropped += 1
                self.operations.queued = None
                self.next_operation_poll = self.clock.monotonic() + 60
                return
        context = _delivering.set(True)
        sent = False
        try:
            async with asyncio.timeout(5):
                channel = self.bot.get_channel(self.channel) or await self.bot.fetch_channel(self.channel)
                await channel.send(content=item.description, embed=discord.Embed(title=item.title, color=item.color),
                    allowed_mentions=discord.AllowedMentions.none(), nonce=item.nonce)
            sent = True
            self.delivered += 1
            if item.receipt:
                try:
                    async with asyncio.timeout(2):
                        await self.operations.delivered(item.receipt)
                except Exception:
                    # Message success is known in this process, while persisted
                    # delivery certainty is not. Never send it again blindly.
                    self.storage_failures += 1
        except asyncio.CancelledError:
            if not sent:
                self.uncertain += 1
                self.failures += 1
                self.dropped += 1
            raise
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
                        self.retries += 1
            if item.receipt and (retry or isinstance(exc, discord.HTTPException) and exc.status < 500):
                try:
                    async with asyncio.timeout(2):
                        await self.operations.rejected(item.receipt)
                except Exception:
                    self.storage_failures += 1
            if not scheduled:
                self.dropped += 1
                if not retry and (not isinstance(exc, discord.HTTPException) or exc.status >= 500):
                    self.uncertain += 1
            logger.warning('discord.log_delivery_failed', extra={'fields': {'result': 'failed',
                'error_code': 'discord_unavailable', 'retry_scheduled': scheduled}})
        finally:
            _delivering.reset(context)

    def gauges(self) -> dict[str, float]:
        with self.lock:
            return {'discord_log_queue_depth': len(self.queue), 'discord_log_dropped': self.dropped,
                'discord_log_failures': self.failures, 'discord_log_delivered': self.delivered,
                'discord_log_format_failures': self.format_failures,
                'discord_log_suppressed': self.suppressed,
                'discord_log_retries': self.retries,
                'discord_log_uncertain': self.uncertain + (self.operations.uncertain if self.operations is not None else 0),
                'discord_log_storage_failures': self.storage_failures,
                'discord_log_reconnects': self.reconnects,
                'discord_log_worker_enabled': float(not self.closed)}

    async def stop(self) -> None:
        self.closed = True
        logging.getLogger().removeHandler(self.handler)
        self.bot.remove_listener(self.ready, 'on_ready')
        self.bot.remove_listener(self.disconnected, 'on_disconnect')
        self.bot.remove_listener(self.resumed, 'on_resumed')
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        with self.lock:
            self.dropped += len(self.queue)
            self.queue.clear()
            self.recent.clear()
        self.handler.close()
