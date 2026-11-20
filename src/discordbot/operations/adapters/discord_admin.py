"""Optional administrator panel. Discord can enqueue, never execute, operations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable
from uuid import uuid4

from discordbot.operations.adapters.manual import RequestInbox
from discordbot.operations.application.manual import ManualOperations
from discordbot.platform.errors import AppError, ShutdownError, ValidationError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.tasks import CancellationBehavior, TaskSpec
from discordbot.operations.adapters.panel_store import PanelStore

RESULTS = {"pending": "접수 기록·실행 미확인", "in_progress": "시작 기록·완료 미확인 (운영 확인 필요)", "ok": "완료", "failed": "실패",
           "ok_cleanup_failed": "작업 완료·정리 확인 필요"}
OPERATIONS = {"update": "업데이트", "restart": "재시작"}
STAGE_LABELS = {"accepted": "접수", "build": "빌드", "preflight": "사전 검사", "test": "검사",
                "compatibility": "호환성 검사", "backup": "백업", "publish": "배포 준비", "stop": "서비스 중지",
                "activate": "버전 전환", "start": "시작", "readiness": "준비 확인", "smoke": "기능 확인",
                "audit": "결과 기록", "retention": "보존본 정리", "complete": "완료 확인",
                "unchanged": "변경 없음", "checkpoint": "상태 보존", "interrupted": "중단 확인", "unknown": "미확인"}
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,199}\Z")
HEX = re.compile(r"[a-f0-9]{32}\Z")
CALLBACK_CAPACITY = 32


class SystemdManualConsumer:
    """Read only fixed timer state; this adapter has no start/enable capability."""
    def __init__(self, executor: BoundedExecutor) -> None:
        self.executor = executor

    def _enabled(self) -> bool:
        try:
            p = subprocess.run(["systemctl", "show", "discordbot-manual.timer",
                                "--property=ActiveState,UnitFileState"], capture_output=True,
                               text=True, timeout=2, stdin=subprocess.DEVNULL)
            values = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
            return p.returncode == 0 and values == {"ActiveState": "active", "UnitFileState": "enabled"}
        except (OSError, subprocess.TimeoutExpired):
            return False

    async def enabled(self) -> bool:
        return await self.executor.run(self._enabled)


class OperationalStatus:
    def __init__(self, inbox: RequestInbox, availability: Any, release: str, readiness: Callable[[], bool],
                 result_reader: Callable[[Path], dict[str, object] | None] | None = None) -> None:
        if not isinstance(release, str) or IDENTIFIER.fullmatch(release) is None:
            raise ValueError("invalid public release identity")
        self.inbox, self.availability, self.release = inbox, availability, release
        self.readiness, self.result_reader = readiness, result_reader

    async def snapshot(self) -> dict[str, Any]:
        request = await self.inbox.snapshot()
        enabled = await self.availability.enabled()
        ready = self.readiness()
        if type(enabled) is not bool or type(ready) is not bool:
            raise ValidationError("invalid operations readiness")
        result = None
        if self.result_reader is not None:
            raw = await self.inbox.executor.run(self.result_reader, self.inbox.state)
            if raw is not None:
                # Even a faulty injected reader cannot publish arbitrary strings.
                if (not isinstance(raw, dict) or raw.get("operation") not in OPERATIONS
                        or raw.get("result") not in {"in_progress", "ok", "failed", "ok_cleanup_failed"}
                        or not isinstance(raw.get("id"), str) or HEX.fullmatch(raw["id"]) is None
                        or not isinstance(raw.get("stage"), str) or raw["stage"] not in STAGE_LABELS
                        or raw["result"] == "ok" and (raw["stage"] not in {"complete", "unchanged"}
                            or raw["stage"] == "unchanged" and raw["operation"] != "update")
                        or raw["result"] == "ok_cleanup_failed" and (raw["operation"], raw["stage"]) != ("update", "retention")):
                    raise ValidationError("invalid public operation result")
                try:
                    stamp = raw.get("timestamp")
                    if not isinstance(stamp, str) or not 1 <= len(stamp) <= 40:
                        raise ValueError
                    parsed = datetime.fromisoformat(stamp)
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        raise ValueError
                    normalized = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                except (ValueError, OverflowError):
                    raise ValidationError("invalid public operation timestamp") from None
                result = {key: raw[key] for key in ("id", "operation", "result", "stage")}
                result["timestamp"] = normalized
        pending = request["result"] in {"pending", "in_progress"} or result is not None and result["result"] == "in_progress"
        stable = [self.release, ready, enabled, request["revision"], result]
        return {"release": self.release, "ready": ready, "consumer_enabled": enabled,
                "request_operation": request["operation"], "request_result": request["result"],
                "inbox_revision": request["revision"], "outcome": result, "pending": pending,
                "revision": hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()}


@dataclass(frozen=True, slots=True)
class Confirmation:
    operation: str
    user: int
    panel: int
    release: str
    revision: str
    inbox_revision: str
    expires: float


def status_embed(snapshot: dict[str, Any]):
    import discord
    from discordbot.operations.adapters.notice_cards import display_release, stage_label
    op, result = snapshot["request_operation"], snapshot["request_result"]
    outcome = snapshot["outcome"]
    lines = ["기본 준비 검사: " + ("통과" if snapshot["ready"] else "미통과"),
             "수동 실행 타이머: " + ("켜짐 · 제어 권한 별도 확인" if snapshot["consumer_enabled"] else "꺼짐 · 요청 불가")]
    if op is not None:
        lines.append("요청 기록: " + OPERATIONS[op] + " · " + RESULTS[result])
    if outcome is not None:
        lines.extend(["최근 작업 기록: " + OPERATIONS[outcome["operation"]] + " · " + RESULTS[outcome["result"]],
                      "결과 기록 단계: " + stage_label(outcome["stage"]),
                      "결과 기록 시각(UTC): " + outcome["timestamp"]])
    elif op is None:
        lines.append("운영 기록 없음")
    if snapshot["pending"]:
        lines.append("접수·시작 기록만으로 현재 실행 여부나 완료를 확정하지 않습니다.")
    embed = discord.Embed(title="🛠️ 시스템 운영 제어판", description='\n'.join(lines), color=0x3498DB)
    embed.add_field(name="검사 범위", value="Discord 연결·음악 초기화/복원·DB probe·상태 서버·런타임 검사.\n"
                    "외부 API·음성 재생·웹 기능 전체의 성공 확인은 별도입니다.", inline=False)
    embed.add_field(name="실행 버전", value=display_release(snapshot["release"]), inline=False)
    embed.set_footer(text="관리자 전용 · 실행 전 별도 확인 · 이 화면은 오류 알림과 별개입니다.")
    return embed


class OperationsPanel:
    name = "operations-panel"
    required = False

    def __init__(self, bot: Any, *, master: int, channel: int | None, state: Path, inbox: RequestInbox,
                 status: OperationalStatus, clock: Any, supervisor: Any, executor: BoundedExecutor,
                 services: Any | None = None, money_status: Any | None = None) -> None:
        self.bot, self.channel, self.status = bot, channel, status
        self.services = services
        self.money_status = money_status  # Default None: no file, DB or HTTP reader.
        self.selected_service = "bot"
        self.operations = ManualOperations(master, inbox)
        self.clock, self.supervisor, self.executor = clock, supervisor, executor
        self.store = None if channel is None else PanelStore(state, channel)
        self.view = None
        self.message_id: int | None = None
        self.confirmations: dict[str, Confirmation] = {}
        self.confirm_views: dict[str, Any] = {}
        self.tasks: set[Any] = set()
        self.callbacks: set[Any] = set()
        self.closed, self.started = True, False
        self.failures = self.denied = self.stale = self.uncertain_publications = 0
        self.response_uncertain = 0
        self.callback_overflow = 0
        self.startup_cleanup_complete = True
        self.publish_lock = asyncio.Lock()
        self.bump_task = None
        self.refresh_timer: asyncio.TimerHandle | None = None
        self.latest_notice_id = 0
        self.follow_retries = 0
        self.notice_first: float | None = None
        self.notice_last = self.next_bump = 0.0
        self.notice_revision = self.bumped_revision = 0
        self.moves = self.retirement_failures = self.reconciled = 0
        self.refreshes = self.link_failures = self.service_failures = 0
        self._bound_generation: str | None = None
        self._bound_guild: int | None = None
        self._link_cache = None
        self._link_retry_after = 0.0

    def notice_delivered(self, message_id: int) -> None:
        """Follow a confirmed alert once after a burst, ordered by Discord snowflake."""
        if self.closed or type(message_id) is not int or not self.latest_notice_id < message_id < 2**63:
            return
        self.latest_notice_id = message_id
        self.follow_retries = 0
        now = self.clock.monotonic()
        self.notice_revision += 1
        self.notice_first = now if self.notice_first is None else self.notice_first
        self.notice_last = now
        self._schedule_follow()

    def _schedule_follow(self) -> None:
        if self.closed or self.bump_task is not None and not self.bump_task.done():
            return
        try:
            task = self.supervisor.start(TaskSpec('panel-follow-notices', 'operations', 'panel-refresh',
                uuid4().hex, 150, cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN,
                emit_routine_events=False), self._follow_notices)
        except AppError:
            self.failures += 1
            return
        self.bump_task = task
        self.tasks.add(task)
        def done(t):
            self.tasks.discard(t)
            if t.cancelled():
                return
            if t.exception() is not None:
                self.failures += 1
                return
            if not self.closed and self.notice_revision != self.bumped_revision:
                self._schedule_follow()
        task.add_done_callback(done)

    async def _follow_notices(self) -> None:
        while not self.closed and self.notice_first is not None:
            due = max(min(self.notice_last + 10, self.notice_first + 60), self.next_bump)
            delay = due - self.clock.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
                continue
            revision = self.notice_revision
            self.next_bump = self.clock.monotonic() + 60
            self.notice_first = None
            try:
                await self._refresh_panel(after_notice=self.latest_notice_id)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._rate_backoff(error)
                self.failures += 1
                if self.follow_retries == 0 and self.notice_revision == revision:
                    self.follow_retries += 1
                    self.notice_first = self.clock.monotonic()
                    return  # The completion callback schedules one spaced retry.
            self.bumped_revision = revision
            return

    async def _snapshot(self):
        if self.services is None:
            return await self.status.snapshot()
        from discordbot.operations.adapters.service_status import validate_observations, unknown_observations
        try:
            async with asyncio.timeout(5):
                rows = validate_observations(await self.services.snapshot())
            snapshot = {'observations': rows, 'provider_failed': False}
        except asyncio.CancelledError:
            raise
        except Exception:
            self.service_failures += 1
            snapshot = {'observations': unknown_observations(), 'provider_failed': True}
        return snapshot

    def _primary_service(self) -> str:
        from discordbot.operations.adapters.service_status import PRIMARY_SERVICE_KEYS
        if type(self.selected_service) is not str or self.selected_service not in PRIMARY_SERVICE_KEYS:
            self.selected_service = 'bot'
        return self.selected_service

    def _service_embed(self, snapshot):
        import discord
        from discordbot.operations.adapters.notice_cards import display_release
        from discordbot.operations.adapters.service_status import TIMERS
        rows = {row.key: row for row in snapshot['observations']}
        selected = rows[self._primary_service()]
        try:
            now = self.clock.now() if hasattr(self.clock, 'now') else datetime.now(timezone.utc)
            if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError
        except Exception:
            now = None

        def display(row):
            age = None if now is None or row.observed_at is None else (now.astimezone(timezone.utc) - row.observed_at).total_seconds()
            fresh = age is not None and 0 <= age <= 60 and not snapshot['provider_failed']
            freshness = ('관측 시각 미확인 · 현재 상태 미확인' if age is None else
                         '미래 관측 시각 · 현재 상태 미확인' if age < 0 else
                         f'<t:{int(row.observed_at.timestamp())}:R> · 최근 관측' if fresh else f'{int(age)}초 전 · 오래된 관측, 현재 상태 미확인')
            return {'fresh': fresh, 'freshness': freshness,
                    'state': row.state if fresh else '현재 미확인 · 이전 관측: ' + row.state,
                    'health': row.health if fresh else '현재 미확인 · 이전 관측: ' + row.health,
                    'stamp': '미제공' if row.observed_at is None else row.observed_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'version': display_release(row.version) if row.version is not None else '미제공',
                    'failed': fresh and (row.state == '실패' or row.health == '미통과')}

        primary = display(selected)
        description = f'선택한 서비스: {selected.label}\n프로세스: {primary["state"]}\n검사: {primary["health"]}'
        if snapshot['provider_failed']:
            description = f'선택한 서비스: {selected.label}\n상태 수집 실패 · 현재 상태 미확인'
        watch = rows['watch'] if selected.key == 'bot' else None
        component = display(watch) if watch is not None else None
        failed = primary['failed'] or component is not None and component['failed']
        incomplete = (not primary['fresh'] or selected.state == '미확인' or selected.health == '미확인') or component is not None and (
            not component['fresh'] or watch.state == '미확인' or watch.health == '미확인')
        color = 0xFF0000 if failed else 0x95A5A6 if incomplete else 0x3498DB
        embed = discord.Embed(title='🛠️ 서비스 상태 제어판', description=description, color=color)
        embed.add_field(name='검사 범위', value=selected.health_scope, inline=False)
        embed.add_field(name='관측 시각(UTC)', value=primary['stamp'], inline=False)
        embed.add_field(name='표시 시점의 관측 최신성', value=primary['freshness'], inline=False)
        version_label = '실행 버전 · 출처' if primary['fresh'] else '이전 관측 버전 · 출처'
        embed.add_field(name=version_label, value=primary['version'] + '\n' + selected.version_provenance, inline=False)
        embed.add_field(name='최근 작업 기록', value=selected.recent_job, inline=False)
        if selected.key in TIMERS:
            enabled = {True: '활성', False: '비활성', None: '미확인'}[selected.enabled] if primary['fresh'] else '미확인'
            embed.add_field(name='부팅 시 자동 시작', value=enabled, inline=True)
            for label, stamp in (('마지막 예약 실행', selected.last_trigger), ('다음 예약', selected.next_run)):
                usable = primary['fresh'] and stamp is not None and (stamp >= now if label == '다음 예약' else stamp <= now)
                when = f'<t:{int(stamp.timestamp())}:F> (<t:{int(stamp.timestamp())}:R>)' if usable else '미확인'
                embed.add_field(name=label, value=when, inline=True)
        if component is not None:
            embed.add_field(name='Watch · Bot 구성 요소', value=(
                f'프로세스: {component["state"]}\n검사: {component["health"]}\n'
                f'검사 범위: {watch.health_scope}\n관측 시각(UTC): {component["stamp"]}\n'
                f'표시 시점의 관측 최신성: {component["freshness"]}\n'
                f'버전 · 출처: {component["version"]} · {watch.version_provenance}'), inline=False)
        embed.set_footer(text='읽기 전용 · 표시 시점의 관측 · Bot 중단 시 갱신 불가 · 선택은 공유 표시만 변경 · 실행 비활성화')
        return embed

    def _generation_embed(self, snapshot, row):
        embed = status_embed(snapshot) if self.services is None else self._service_embed(snapshot)
        embed.set_footer(text=embed.footer.text + ' · 패널: ' + row['nonce'])
        return embed

    def _invalidate_link(self) -> None:
        self._link_cache = None

    def _rate_backoff(self, error) -> None:
        import discord
        if isinstance(error, discord.RateLimited) or isinstance(error, discord.HTTPException) and error.status == 429:
            delay = getattr(error, 'retry_after', 5)
            delay = max(5, delay) if type(delay) in (int, float) and 0 <= delay <= 60 else 5
            self._link_retry_after = self.clock.monotonic() + delay
            self.next_bump = max(self.next_bump, self._link_retry_after)

    async def _channel(self, *, sending: bool):
        channel = self.bot.get_channel(self.channel) or await self.bot.fetch_channel(self.channel)
        self._require_live_owner()
        user = getattr(getattr(self.bot, 'user', None), 'id', None)
        guild = getattr(channel, 'guild', None)
        guild_id = getattr(guild, 'id', None)
        member = getattr(guild, 'me', None)
        if (type(user) is not int or not 0 < user < 2**63 or type(getattr(channel, 'id', None)) is not int or channel.id != self.channel
                or type(guild_id) is not int or not 0 < guild_id < 2**63
                or type(getattr(member, 'id', None)) is not int or member.id != user):
            raise ValidationError('panel channel identity unavailable')
        permissions = channel.permissions_for(member)
        required = ('view_channel', 'read_message_history', 'send_messages', 'embed_links') if sending else ('view_channel', 'read_message_history')
        if not all(getattr(permissions, key, False) is True for key in required):
            raise ValidationError('panel permission unavailable')
        return channel

    def _own_panel(self, message, *, generation: str | None = None, guild_id: int | None = None) -> bool:
        import discord
        user = getattr(getattr(self.bot, 'user', None), 'id', None)
        channel = getattr(message, 'channel', None)
        guild = getattr(channel, 'guild', None)
        message_guild = getattr(message, 'guild', None)
        actual_guild = getattr(guild, 'id', None)
        if (type(user) is not int or type(getattr(getattr(message, 'author', None), 'id', None)) is not int
                or message.author.id != user or type(getattr(channel, 'id', None)) is not int
                or channel.id != self.channel or type(actual_guild) is not int
                or not 0 < actual_guild < 2**63 or getattr(message_guild, 'id', None) != actual_guild
                or guild_id is not None and actual_guild != guild_id):
            return False
        embeds = getattr(message, 'embeds', ())
        if len(embeds) != 1:
            return False
        children = [child for group in getattr(message, 'components', ()) for child in getattr(group, 'children', ())]
        ids = {getattr(child, 'custom_id', None) for child in children}
        legacy = (embeds[0].title == '🛠️ 시스템 운영 제어판' and len(children) == 3
            and all(getattr(child, 'type', None) == discord.ComponentType.button for child in children)
            and ids == {'ops:v1:refresh', 'ops:v1:update', 'ops:v1:restart'})
        unified = False
        if self.services is not None and embeds[0].title == '🛠️ 서비스 상태 제어판' and len(children) == 5:
            from discordbot.operations.adapters.service_status import PRIMARY_SERVICE_KEYS, LEGACY_MENUS
            selectors = [child for child in children if getattr(child, 'custom_id', None) == 'ops:v2:service']
            buttons = [child for child in children if getattr(child, 'custom_id', None) != 'ops:v2:service']
            options = getattr(selectors[0], 'options', ()) if len(selectors) == 1 else ()
            values = tuple(getattr(option, 'value', None) for option in options) if type(options) in (list, tuple) else ()
            menu_known = (all(type(value) is str for value in values)
                          and any(len(values) == len(menu) and set(values) == set(menu)
                                  for menu in (PRIMARY_SERVICE_KEYS, *LEGACY_MENUS)))
            unified = (ids == {'ops:v2:service', 'ops:v2:refresh', 'ops:v2:restart', 'ops:v2:update', 'ops:v2:backup'}
                and len(selectors) == 1 and getattr(selectors[0], 'type', None) == discord.ComponentType.select
                and menu_known
                and all(getattr(child, 'type', None) == discord.ComponentType.button for child in buttons)
                and all(getattr(child, 'disabled', None) is True for child in buttons if child.custom_id != 'ops:v2:refresh'))
        if not (legacy or unified):
            return False
        footer = embeds[0].footer.text
        return generation is None or type(footer) is str and footer.endswith(' · 패널: ' + generation)

    def _select_message(self, message: int | None, generation: str | None = None, guild: int | None = None) -> None:
        selected = (message, generation, guild)
        if selected == (self.message_id, self._bound_generation, self._bound_guild):
            return
        self._invalidate_link()
        for view in self.confirm_views.values():
            view.stop()
        self.confirmations.clear(); self.confirm_views.clear()
        if self.view is not None:
            self.view.stop()  # Remove only our previous SDK dispatch entry.
        self.view = self._view()
        self.message_id, self._bound_generation, self._bound_guild = selected
        if message is not None:
            try:
                self.bot.add_view(self.view, message_id=message)
                self._link_retry_after = 0.0
            except Exception:
                self.view.stop()
                self.message_id = self._bound_generation = self._bound_guild = None
                raise

    async def _same_marker(self, expected):
        current = await self.executor.run(self.store.read)
        self._require_live_owner()
        if current is None or any(current.get(key) != expected.get(key) for key in ('version', 'channel', 'state', 'message', 'nonce', 'previous')):
            self._select_message(None)
            raise ValidationError('current panel marker changed')
        return current

    async def _fetched_panel(self, channel, row, *, legacy: bool = False):
        async with asyncio.timeout(5):
            message = await channel.fetch_message(row['message'])
        self._require_live_owner()
        full = self._own_panel(message, generation=row['nonce'], guild_id=channel.guild.id)
        if (type(getattr(message, 'id', None)) is not int or message.id != row['message'] or
                not full and not (legacy and row['version'] == 1 and self._own_panel(message, guild_id=channel.guild.id))):
            self._select_message(None)
            raise ValidationError('current panel ownership unconfirmed')
        await self._same_marker(row)
        return message, full

    async def verified_link(self) -> str | None:
        """Read-only lookup of a fetched current panel; never send/edit/create here."""
        if self.closed or self.clock.monotonic() < self._link_retry_after:
            return None
        try:
            async with self.publish_lock:
                self._require_live_owner()
                row = await self.executor.run(self.store.read)
                if row is None or row['state'] != 'published':
                    self._select_message(None)
                    return None
                channel = await self._channel(sending=False)
                key = (row['version'], row['channel'], channel.guild.id, row['message'], row['nonce'])
                if self._link_cache is not None and self._link_cache[0] == key and self._link_cache[2] > self.clock.monotonic():
                    return self._link_cache[1]
                self._invalidate_link()
                message, _ = await self._fetched_panel(channel, row)
                if self.services is not None and message.embeds[0].title != '🛠️ 서비스 상태 제어판':
                    raise ValidationError('read-only panel migration not yet verified')
                self._select_message(message.id, row['nonce'], channel.guild.id)
                link = f'https://discord.com/channels/{channel.guild.id}/{self.channel}/{message.id}'
                self._link_cache = (key, link, self.clock.monotonic() + 30)
                return link
        except asyncio.CancelledError:
            self._invalidate_link()
            raise
        except Exception as error:
            self._invalidate_link()
            self._select_message(None)
            self._rate_backoff(error)
            self._link_retry_after = max(self._link_retry_after, self.clock.monotonic() + 5)
            self.link_failures += 1
            return None

    async def _reconcile(self, channel, row):
        matches = []
        count = 0
        async with asyncio.timeout(5):
            async for message in channel.history(limit=101, after=datetime.fromisoformat(row['created_at'])):
                count += 1
                if count > 100:
                    self.uncertain_publications += 1
                    raise ValidationError('uncertain panel history truncated')
                if self._own_panel(message, generation=row['nonce'], guild_id=channel.guild.id):
                    matches.append(message)
        self._require_live_owner()
        if len(matches) != 1:
            self.uncertain_publications += 1
            return None
        await self._same_marker(row)
        message = matches[0]
        await self.executor.run_retained(self.store.published, row['nonce'], message.id)
        self._require_live_owner()
        current = await self.executor.run(self.store.read)
        if current is None or current['state'] != 'published' or current['message'] != message.id or current['nonce'] != row['nonce']:
            raise ValidationError('reconciled panel marker changed')
        self._select_message(message.id, row['nonce'], channel.guild.id)
        self.reconciled += 1
        return current

    async def _refresh_panel(self, *, after_notice: int = 0) -> None:
        async with self.publish_lock, asyncio.timeout(20):
            await self._publish_locked(create_initial=False, after_notice=after_notice)

    def _schedule_periodic(self) -> None:
        if not self.closed and self.refresh_timer is None:
            self.refresh_timer = asyncio.get_running_loop().call_later(60, self._periodic_due)

    def _periodic_due(self) -> None:
        self.refresh_timer = None
        if self.closed:
            return
        if self.clock.monotonic() < self._link_retry_after:
            self._schedule_periodic()
            return

        async def refresh():
            try:
                await self._refresh_panel()
            except Exception as error:
                self._rate_backoff(error)
                self.failures += 1
            finally:
                self._schedule_periodic()
        try:
            task = self.supervisor.start(TaskSpec("operations-panel", "operations", "periodic-refresh",
                uuid4().hex, 25, cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN,
                emit_routine_events=False), refresh)
        except AppError:
            self.failures += 1
            self._schedule_periodic()
            return
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _discover_unstored(self, channel):
        """No missing-state duplicate: prove a bounded history is exhausted."""
        matches = []
        count = 0
        async with asyncio.timeout(5):
            async for message in channel.history(limit=101):
                count += 1
                if count > 100:
                    raise ValidationError('panel discovery history truncated')
                if self._own_panel(message, guild_id=channel.guild.id):
                    footer = message.embeds[0].footer.text
                    match = re.search(r' · 패널: ([a-f0-9]{24})\Z', footer) if type(footer) is str else None
                    if match is None:
                        raise ValidationError('legacy unstored panel generation unknown')
                    matches.append((message, match.group(1)))
        self._require_live_owner()
        if len(matches) > 1:
            raise ValidationError('multiple unstored active panels')
        if not matches:
            return None
        message, nonce = matches[0]
        row = await self.executor.run_retained(self.store.adopt_existing, nonce, message.id)
        self._require_live_owner()
        await self._same_marker(row)
        self._select_message(message.id, nonce, channel.guild.id)
        self.reconciled += 1
        return row

    def _view(self):
        import discord
        view = discord.ui.View(timeout=None)
        if self.services is not None:
            from discordbot.operations.adapters.service_status import PRIMARY_CHOICES
            self._primary_service()
            select = discord.ui.Select(custom_id='ops:v2:service', placeholder='서비스 선택',
                options=[discord.SelectOption(label=label, value=key, default=key == self.selected_service)
                         for key,label in PRIMARY_CHOICES], row=0)
            async def selected(interaction):
                await self.interact(interaction, 'select')
            select.callback = selected
            view.add_item(select)
            actions = [('refresh', '상태 새로고침'), ('restart', '재시작 · 비활성'),
                       ('update', '업데이트 · 비활성'), ('backup', '백업 · 비활성')]
            for action, label in actions:
                button = discord.ui.Button(label=label, custom_id='ops:v2:' + action, row=1,
                    style=discord.ButtonStyle.secondary, disabled=action != 'refresh')
                async def callback(interaction, action=action):
                    await self.interact(interaction, action)
                button.callback = callback
                view.add_item(button)
        else:
            for action, label in [('refresh', '상태 새로고침'), ('update', '업데이트 요청'), ('restart', '재시작 요청')]:
                button = discord.ui.Button(label=label, custom_id='ops:v1:' + action,
                    style=discord.ButtonStyle.secondary if action == 'refresh' else discord.ButtonStyle.danger,
                    disabled=action != 'refresh')  # Unknown authority always starts disabled.
                async def callback(interaction, action=action):
                    await self.interact(interaction, action)
                button.callback = callback
                view.add_item(button)
        return view

    def _set_controls(self, snapshot: dict[str, Any]) -> None:
        if self.services is not None:
            self._primary_service()
            for item in self.view.children:
                if item.custom_id in {'ops:v2:restart', 'ops:v2:update', 'ops:v2:backup'}:
                    item.disabled = True
                elif item.custom_id == 'ops:v2:service':
                    for option in item.options:
                        option.default = option.value == self.selected_service
            return
        blocked = not snapshot['consumer_enabled'] or not snapshot['ready'] or snapshot['pending']
        for item in self.view.children:
            if item.custom_id in {'ops:v1:update', 'ops:v1:restart'}:
                item.disabled = blocked

    async def start(self) -> None:
        if self.started or self.channel is None:
            return
        self.started = True
        try:
            if type(self.channel) is not int or not 0 < self.channel < 2**63:
                raise ValueError("invalid operations channel")
            await self.executor.run(self.store.read)  # Schema/path validation only.
            self.view = self._view()
            self.closed = False
            self.bot.add_listener(self.ready, "on_ready")
            # No stored ID authorizes or becomes a link before real ownership proof.
        except Exception:
            self.failures += 1
            await self.stop()

    async def _work(self, action: str, factory):
        if self.closed:
            raise ValidationError("operations panel closed")
        task = self.supervisor.start(TaskSpec("operations-panel", "operations", action, uuid4().hex, 20 if action == 'publish' else 8,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN, emit_routine_events=False), factory)
        self.tasks.add(task)
        try:
            return await task
        finally:
            self.tasks.discard(task)

    async def ready(self) -> None:
        if self.closed:
            return
        try:
            await self._work("publish", self._publish)
        except Exception:
            self.failures += 1
        finally:
            self._schedule_periodic()

    def _require_live_owner(self) -> None:
        task = asyncio.current_task()
        if self.closed or task is not None and task.cancelling():
            raise asyncio.CancelledError

    async def _publish(self) -> None:
        async with self.publish_lock:
            await self._publish_locked(create_initial=True)

    async def _publish_locked(self, *, create_initial: bool, snapshot=None, after_notice: int = 0) -> None:
        import discord
        self._require_live_owner()
        channel = await self._channel(sending=True)
        row = await self.executor.run(self.store.read)
        if row is None and not create_initial:
            return  # Alert follow-up never owns first creation.
        if row is None:
            await self._discover_unstored(channel)
        row, created = await self.executor.run_retained(self.store.claim)
        self._require_live_owner()
        if row['state'] == 'published':
            try:
                message, full = await self._fetched_panel(channel, row, legacy=True)
            except discord.NotFound as error:
                self._select_message(None)
                if error.code != 10008:
                    raise
                # A confirmed missing current message, sufficient permission and
                # unchanged marker are all required. No previous card is touched.
                row = await self.executor.run_retained(self.store.replace_missing, row)
                self._require_live_owner()
                created = True
            else:
                snapshot = await self._snapshot() if snapshot is None else snapshot
                self._require_live_owner()
                await self._same_marker(row)
                self._set_controls(snapshot)
                if after_notice > message.id:
                    if row.get('previous') is not None:
                        row = await self._retire_previous(channel, row)
                    # All checks and sampling precede the durable send claim.
                    previous = row
                    row = await self.executor.run_retained(self.store.rotate, previous)
                    self._require_live_owner()
                    self._select_message(None)
                    self._set_controls(snapshot)
                    created = True
                else:
                    await message.edit(embed=self._generation_embed(snapshot, row), view=self.view,
                                       allowed_mentions=discord.AllowedMentions.none())
                    self._require_live_owner()
                    if not full:
                        message, _ = await self._fetched_panel(channel, row)  # Verify legacy footer upgrade.
                    else:
                        await self._same_marker(row)
                    self._select_message(message.id, row['nonce'], channel.guild.id)
                    self._set_controls(snapshot)
                    self._invalidate_link()
                    self.refreshes += 1
                    if row.get('previous') is not None:
                        await self._retire_previous(channel, row)
                    return
        if not created:
            if row['version'] == 2:
                current = await self._reconcile(channel, row)
                if current is not None and current.get('previous') is not None:
                    await self._retire_previous(channel, current)
            else:
                self.uncertain_publications += 1
            return  # An uncertain send is never replayed blindly.
        snapshot = await self._snapshot() if snapshot is None else snapshot
        self._require_live_owner()
        self._set_controls(snapshot)
        try:
            message = await channel.send(embed=self._generation_embed(snapshot, row), view=self.view,
                allowed_mentions=discord.AllowedMentions.none(), nonce=row['nonce'])
        except (discord.RateLimited, discord.HTTPException) as error:
            if row.get('previous') is not None and (isinstance(error, discord.RateLimited)
                    or error.status in (400, 401, 403, 404, 429)):
                # Discord rejected the send. A timeout or 5xx must reconcile by nonce.
                await self.executor.run_retained(self.store.restore_rejected, row, previous)
                self._require_live_owner()
                self._select_message(previous['message'], previous['nonce'], channel.guild.id)
                self._set_controls(snapshot)
            raise
        self._require_live_owner()
        if (not self._own_panel(message, generation=row['nonce'], guild_id=channel.guild.id) or
                type(getattr(message, 'id', None)) is not int or not (row.get('previous') or 0) < message.id < 2**63):
            self.uncertain_publications += 1
            raise ValidationError('sent panel identity unconfirmed')
        await self.executor.run_retained(self.store.published, row['nonce'], message.id)
        self._require_live_owner()
        current = await self.executor.run(self.store.read)
        if current is None or current['state'] != 'published' or current['message'] != message.id or current['nonce'] != row['nonce']:
            raise ValidationError('published panel marker changed')
        self._select_message(message.id, row['nonce'], channel.guild.id)
        self._set_controls(snapshot)
        if current.get('previous') is not None:
            self.moves += 1
            await self._retire_previous(channel, current)

    async def _retire_previous(self, channel, row):
        import discord
        previous = row['previous']
        link = f"https://discord.com/channels/{channel.guild.id}/{self.channel}/{row['message']}"
        redirect = f"최신 제어판은 <#{self.channel}> 맨 아래에 있습니다. [다음 제어판 열기]({link})"
        try:
            try:
                message = await channel.fetch_message(previous)
            except discord.NotFound as error:
                if error.code != 10008:
                    raise
            else:
                await self._same_marker(row)
                if (message.id != previous or message.author.id != self.bot.user.id or
                        message.channel.id != self.channel or message.guild.id != channel.guild.id):
                    raise ValidationError("previous panel identity unconfirmed")
                embeds = message.embeds
                already_retired = (len(embeds) == 1 and embeds[0].title == "이전 제어판"
                                   and embeds[0].description == redirect and not message.components)
                if not already_retired:
                    if not self._own_panel(message, guild_id=channel.guild.id):
                        raise ValidationError("previous panel ownership unconfirmed")
                    await message.edit(embed=discord.Embed(title="이전 제어판", description=redirect),
                        view=None, allowed_mentions=discord.AllowedMentions.none())
            await self._same_marker(row)
            return await self.executor.run_retained(self.store.retired, previous)
        except Exception:
            self.retirement_failures += 1
            raise

    def _authorized(self, interaction: Any, *, confirmation: bool = False) -> bool:
        user = getattr(getattr(interaction, "user", None), "id", None)
        channel = getattr(interaction, "channel_id", None)
        message = getattr(getattr(interaction, "message", None), "id", None)
        return (not self.closed and self.operations.authorized(user) and type(channel) is int and channel == self.channel
                and self.message_id is not None and (confirmation or message == self.message_id))

    async def _reply(self, interaction: Any, text: str, **kwargs) -> bool:
        try:
            async with asyncio.timeout(3):
                if interaction.response.is_done():
                    await interaction.followup.send(text, ephemeral=True, **kwargs)
                else:
                    await interaction.response.send_message(text, ephemeral=True, **kwargs)
            return True
        except Exception:
            # A transport failure may mean Discord received the reply. Do not
            # blindly send it again, and never repeat a possibly accepted request.
            self.failures += 1
            self.response_uncertain += 1
            return False

    async def interact(self, interaction: Any, action: str, nonce: str | None = None) -> None:
        # Denied replies and initial ACKs also consume bounded resources. At
        # capacity do not start another transport or operation merely to reject
        # the request; the fixed-size metrics make that fail-closed loss visible.
        if len(self.callbacks) >= CALLBACK_CAPACITY:
            self.callback_overflow += 1
            return
        task = asyncio.current_task()
        self.callbacks.add(task)
        try:
            await self._dispatch(interaction, action, nonce)
        finally:
            self.callbacks.discard(task)

    async def _dispatch(self, interaction: Any, action: str, nonce: str | None) -> None:
        if not self._authorized(interaction, confirmation=action in {"confirm", "cancel"}):
            self.denied += 1
            await self._reply(interaction, "이 제어판을 사용할 권한이 없습니다.")
            return
        if self.services is not None and action not in {'refresh', 'select'}:
            self.denied += 1
            await self._reply(interaction, '읽기 전용 제어판입니다. 실행 요청을 받지 않습니다.')
            return
        allowed = {'refresh', 'select'} if self.services is not None else {'refresh', 'update', 'restart', 'confirm', 'cancel'}
        if action not in allowed:
            await self._reply(interaction, "지원하지 않는 운영 요청입니다.")
            return
        try:
            async with asyncio.timeout(2):
                await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            # No operation is admitted before a confirmed initial ACK. Retrying
            # the ACK itself could duplicate an uncertain Discord response.
            self.failures += 1
            self.response_uncertain += 1
            return
        try:
            await self._work(action, lambda: self._interact(interaction, action, nonce))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failures += 1
            await self._reply(interaction, "운영 상태를 확인하지 못했습니다. 작업을 다시 실행하지 말고 상태를 새로고침해 주세요.")

    async def _interact(self, interaction: Any, action: str, nonce: str | None) -> None:
        async with self.publish_lock:
            # The initial ACK is asynchronous: the current marker may change since
            # dispatch checked the message. Serialize authority and mutation.
            if not self._authorized(interaction, confirmation=action in {'confirm', 'cancel'}):
                self.denied += 1
                await self._reply(interaction, '이 제어판을 사용할 권한이 없습니다.')
                return
            await self._interact_locked(interaction, action, nonce)

    async def _interact_locked(self, interaction: Any, action: str, nonce: str | None) -> None:
        current = await self.executor.run(self.store.read)
        self._require_live_owner()
        if (current is None or current['state'] != 'published' or current['message'] != self.message_id
                or current['nonce'] != self._bound_generation):
            self._select_message(None)
            self.denied += 1
            await self._reply(interaction, '이 제어판을 사용할 권한이 없습니다.')
            return
        if self.services is not None:
            if action not in {'refresh', 'select'}:
                self.denied += 1
                await self._reply(interaction, '읽기 전용 제어판입니다. 실행 요청을 받지 않습니다.')
                return
            if action == 'select':
                from discordbot.operations.adapters.service_status import PRIMARY_SERVICE_KEYS
                data = getattr(interaction, 'data', None)
                values = data.get('values') if type(data) is dict else None
                if (type(values) is not list or len(values) != 1 or type(values[0]) is not str
                        or values[0] not in PRIMARY_SERVICE_KEYS):
                    await self._reply(interaction, '지원하지 않는 서비스 선택입니다.')
                    return
                self.selected_service = values[0]
            snapshot = await self._snapshot()
            self._require_live_owner()
            await self._publish_locked(create_initial=False, snapshot=snapshot)
            await self._reply(interaction, '선택한 서비스 상태를 새로고침했습니다. 선택은 공유 화면 표시에만 반영됩니다.')
            return
        if action in {"confirm", "cancel"}:
            ticket = self.confirmations.pop(nonce, None)
            view = self.confirm_views.pop(nonce, None)
            if view is not None:
                view.stop()
            if ticket is None or ticket.user != interaction.user.id or ticket.panel != self.message_id or ticket.expires <= self.clock.monotonic():
                self.stale += 1
                await self._reply(interaction, "확인이 만료되었거나 이미 처리되었습니다. 제어판에서 다시 확인해 주세요.")
                return
            if action == "cancel":
                await self._reply(interaction, "운영 요청을 취소했습니다.")
                return
            snapshot = await self.status.snapshot()
            self._require_live_owner()
            if (snapshot["revision"] != ticket.revision or snapshot["release"] != ticket.release
                    or not snapshot["consumer_enabled"] or not snapshot["ready"] or snapshot["pending"]):
                self.stale += 1
                await self._reply(interaction, "상태가 바뀌어 실행하지 않았습니다. 새로고침 후 다시 확인해 주세요.")
                return
            result = await self.operations.confirmed(interaction.user.id, ticket.operation, nonce, ticket.inbox_revision)
            self._require_live_owner()
            texts = {"accepted": "🔄 요청을 접수했습니다. 아직 실행 완료가 아닙니다.",
                     "already_running": "이미 처리 중이거나 처리한 요청입니다.", "stale": "상태가 바뀌어 접수하지 않았습니다.",
                     "forbidden": "이 제어판을 사용할 권한이 없습니다."}
            await self._reply(interaction, texts.get(result, "운영 요청을 접수하지 못했습니다. 상태를 확인해 주세요."))
            return
        snapshot = await self.status.snapshot()
        self._require_live_owner()
        if action == "refresh":
            await self._publish_locked(create_initial=False, snapshot=snapshot)
            await self._reply(interaction, "상태를 새로고침했습니다.")
            return
        if not snapshot["consumer_enabled"]:
            await self._reply(interaction, "운영 실행기가 꺼져 있어 요청을 받지 않습니다. 실행기 활성화는 별도 운영 승인이 필요합니다.")
            return
        if not snapshot["ready"] or snapshot["pending"]:
            await self._reply(interaction, "준비·처리 중인 작업이 있습니다. 완료 후 상태를 확인해 주세요.")
            return
        # One live confirmation at a time. A later click invalidates the old one.
        for v in self.confirm_views.values():
            v.stop()
        self.confirmations.clear(); self.confirm_views.clear()
        nonce = uuid4().hex
        self.confirmations[nonce] = Confirmation(action, interaction.user.id, self.message_id, snapshot["release"],
            snapshot["revision"], snapshot["inbox_revision"], self.clock.monotonic() + 60)
        view = self._confirmation_view(nonce)
        self.confirm_views[nonce] = view
        await self._reply(interaction, OPERATIONS[action] + "를 요청할까요? 접수 후 서비스가 잠시 끊길 수 있습니다. 확인은 60초 동안 유효합니다.", view=view)

    def _confirmation_view(self, nonce: str):
        import discord
        resource = self
        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
            async def on_timeout(self):
                resource.confirmations.pop(nonce, None); resource.confirm_views.pop(nonce, None)
        view = ConfirmView()
        for action, label in [("confirm", "확인하고 요청"), ("cancel", "취소")]:
            button = discord.ui.Button(label=label, custom_id="ops:v1:" + action + ":" + nonce,
                                       style=discord.ButtonStyle.danger if action == "confirm" else discord.ButtonStyle.secondary)
            async def callback(interaction, action=action):
                await self.interact(interaction, action, nonce)
            button.callback = callback
            view.add_item(button)
        return view

    def gauges(self) -> dict[str, float]:
        return {"operations_panel_enabled": float(not self.closed), "operations_panel_failures": float(self.failures),
                "operations_panel_denied": float(self.denied), "operations_panel_stale": float(self.stale),
                "operations_panel_response_uncertain": float(self.response_uncertain),
                "operations_panel_callback_depth": float(len(self.callbacks)),
                "operations_panel_callback_capacity": float(CALLBACK_CAPACITY),
                "operations_panel_callback_overflow": float(self.callback_overflow),
                "operations_panel_publication_uncertain": float(self.uncertain_publications),
                "operations_panel_moves": float(self.moves),
                "operations_panel_reconciled": float(self.reconciled),
                "operations_panel_retirement_failures": float(self.retirement_failures),
                "operations_panel_refreshes": float(self.refreshes),
                "operations_panel_link_failures": float(self.link_failures),
                "operations_panel_service_status_failures": float(self.service_failures)}

    async def stop(self) -> None:
        self.closed = True
        if self.refresh_timer is not None:
            self.refresh_timer.cancel()
            self.refresh_timer = None
        self._invalidate_link()
        self.message_id = self._bound_generation = self._bound_guild = None
        self.bot.remove_listener(self.ready, "on_ready")
        for view in [self.view, *self.confirm_views.values()]:
            if view is not None:
                view.stop()
        self.confirmations.clear(); self.confirm_views.clear()
        tasks = tuple((self.tasks | self.callbacks) - {asyncio.current_task()})
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=2)
            if pending:
                self.startup_cleanup_complete = False
                raise ShutdownError("operations panel cleanup incomplete")
        self.startup_cleanup_complete = True
