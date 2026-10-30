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

from discordbot.operations.adapters.filesystem import ExclusiveLock, atomic_json, read_json
from discordbot.operations.adapters.manual import RequestInbox
from discordbot.operations.application.manual import ManualOperations
from discordbot.platform.errors import AppError, ShutdownError, ValidationError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.tasks import CancellationBehavior, TaskSpec

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


class PanelStore:
    """A pre-send marker prevents restart loops from creating duplicate panels."""
    def __init__(self, state: Path, channel: int) -> None:
        self.state, self.channel = state, channel
        self.path, self.lock = state / "operations-panel.json", state / ".operations-panel.lock"

    def read(self) -> dict[str, Any] | None:
        try:
            value = read_json(self.path, 1024, reject_duplicates=True)
        except FileNotFoundError:
            return None
        if (set(value) != {"version", "channel", "message", "nonce", "state"} or type(value["version"]) is not int or value["version"] != 1
                or type(value["channel"]) is not int or value["channel"] != self.channel
                or not isinstance(value["nonce"], str) or re.fullmatch(r"[a-f0-9]{24}", value["nonce"]) is None
                or value["state"] not in {"publishing", "published"}
                or (value["state"] == "published" and (type(value["message"]) is not int or not 0 < value["message"] < 2**63))
                or (value["state"] == "publishing" and value["message"] is not None)):
            raise ValidationError("invalid persisted operations panel")
        return value

    def claim(self) -> tuple[dict[str, Any], bool]:
        with ExclusiveLock(self.lock).acquire():
            old = self.read()
            if old is not None:
                return old, False
            row = {"version": 1, "channel": self.channel, "message": None,
                   "nonce": uuid4().hex[:24], "state": "publishing"}
            atomic_json(self.path, row)
            return row, True

    def published(self, nonce: str, message: int) -> None:
        if type(message) is not int or not 0 < message < 2**63:
            raise ValidationError("invalid published panel identity")
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if row is None or row["nonce"] != nonce or row["state"] != "publishing":
                raise ValidationError("panel publication changed")
            atomic_json(self.path, {**row, "message": message, "state": "published"})

    def replace_missing(self, expected: dict[str, Any]) -> dict[str, Any]:
        """Reset only an unchanged published marker after confirmed Unknown Message."""
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if row != expected or row is None or row["state"] != "published":
                raise ValidationError("panel changed during missing-message recovery")
            replacement = {**row, "message": None, "nonce": uuid4().hex[:24], "state": "publishing"}
            atomic_json(self.path, replacement)
            return replacement


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
    op, result = snapshot["request_operation"], snapshot["request_result"]
    current = "없음" if op is None else OPERATIONS[op] + " · " + RESULTS[result]
    outcome = snapshot["outcome"]
    last = "확인된 결과 없음" if outcome is None else OPERATIONS[outcome["operation"]] + " · " + RESULTS[outcome["result"]]
    recorded_at = "확인되지 않음" if outcome is None else outcome["timestamp"]
    stage = "확인되지 않음" if outcome is None else STAGE_LABELS[outcome["stage"]]
    description = ("봇: " + ("정상" if snapshot["ready"] else "준비·복구 중")
                   + "\n운영 실행기: " + ("사용 가능" if snapshot["consumer_enabled"] else "꺼짐·요청 불가")
                   + "\n요청 기록(시각 미상): " + current + "\n최근 작업 기록: " + last
                   + "\n결과 기록 시각(UTC): " + recorded_at + "\n결과 기록 단계: " + stage
                   + "\n접수는 완료가 아닙니다. 완료 알림은 실제 검증이 끝난 뒤 표시됩니다.")
    embed = discord.Embed(title="🛠️ 시스템 운영 제어판", description=description, color=0x3498DB)
    embed.add_field(name="실행 버전", value=snapshot["release"], inline=False)
    embed.set_footer(text="관리자 전용 · 실행 전 별도 확인 · 이 화면은 오류 알림과 별개입니다.")
    return embed


class OperationsPanel:
    name = "operations-panel"
    required = False

    def __init__(self, bot: Any, *, master: int, channel: int | None, state: Path, inbox: RequestInbox,
                 status: OperationalStatus, clock: Any, supervisor: Any, executor: BoundedExecutor) -> None:
        self.bot, self.channel, self.status = bot, channel, status
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

    def _view(self):
        import discord
        view = discord.ui.View(timeout=None)
        for action, label in [("refresh", "상태 새로고침"), ("update", "업데이트 요청"), ("restart", "재시작 요청")]:
            button = discord.ui.Button(label=label, custom_id="ops:v1:" + action,
                                       style=discord.ButtonStyle.secondary if action == "refresh" else discord.ButtonStyle.danger)
            async def callback(interaction, action=action):
                await self.interact(interaction, action)
            button.callback = callback
            view.add_item(button)
        return view

    def _set_controls(self, snapshot: dict[str, Any]) -> None:
        blocked = not snapshot["consumer_enabled"] or not snapshot["ready"] or snapshot["pending"]
        for item in self.view.children:
            if item.custom_id in {"ops:v1:update", "ops:v1:restart"}:
                item.disabled = blocked

    async def start(self) -> None:
        if self.started or self.channel is None:
            return
        self.started = True
        try:
            if type(self.channel) is not int or not 0 < self.channel < 2**63:
                raise ValueError("invalid operations channel")
            row = await self.executor.run(self.store.read)
            self.message_id = row["message"] if row is not None and row["state"] == "published" else None
            self.view = self._view()
            self.bot.add_view(self.view, message_id=self.message_id)
            self.closed = False
            self.bot.add_listener(self.ready, "on_ready")
        except Exception:
            # Optional controls must not take down music/Discord on a bad path.
            self.failures += 1
            await self.stop()

    async def _work(self, action: str, factory):
        if self.closed:
            raise ValidationError("operations panel closed")
        task = self.supervisor.start(TaskSpec("operations-panel", "operations", action, uuid4().hex, 8,
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

    def _require_live_owner(self) -> None:
        task = asyncio.current_task()
        if self.closed or task is not None and task.cancelling():
            raise asyncio.CancelledError

    async def _publish(self) -> None:
        import discord
        async with self.publish_lock:
            snapshot = await self.status.snapshot()
            self._set_controls(snapshot)
            row, created = await self.executor.run_retained(self.store.claim)
            self._require_live_owner()
            channel = self.bot.get_channel(self.channel) or await self.bot.fetch_channel(self.channel)
            if row["state"] == "published":
                self.message_id = row["message"]
                try:
                    await channel.get_partial_message(self.message_id).edit(embed=status_embed(snapshot), view=self.view)
                    return
                except discord.NotFound as error:
                    if error.code != 10008:
                        raise  # A missing channel/other resource is not this proof.
                    self.message_id = None
                    row = await self.executor.run_retained(self.store.replace_missing, row)
                    self._require_live_owner()
                    created = True
            if not created:
                self.uncertain_publications += 1
                return  # Do not blindly repeat a send whose result may have been lost.
            message = await channel.send(embed=status_embed(snapshot), view=self.view,
                                         allowed_mentions=discord.AllowedMentions.none(), nonce=row["nonce"])
            await self.executor.run_retained(self.store.published, row["nonce"], message.id)
            self._require_live_owner()
            self.message_id = message.id

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
        if action not in {"refresh", "update", "restart", "confirm", "cancel"}:
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
        if action == "refresh":
            self._set_controls(snapshot)
            await interaction.message.edit(embed=status_embed(snapshot), view=self.view)
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
                "operations_panel_publication_uncertain": float(self.uncertain_publications)}

    async def stop(self) -> None:
        self.closed = True
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
