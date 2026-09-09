"""One bounded mailbox owns each session's ordering and all state mutations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from discordbot.platform.clock import Clock, IdGenerator
from discordbot.platform.errors import AppError, CapacityError, DeadlineExceededError, InternalError, ShutdownError
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor
from discordbot.watch.domain.policy import ClosedSession, Intent, Rate, WatchLimits, protocol
from discordbot.watch.ports.runtime import Socket, Writer


class Peer:
    def __init__(self, socket: Socket, identity: str, limits: WatchLimits, supervisor: TaskSupervisor) -> None:
        self.socket, self.id, self.supervisor = socket, identity, supervisor
        self.queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue(limits.outbound)
        self.name: str | None = None
        self.rate = Rate(limits.rate_per_second)
        self.code = 1000
        self.failed = False
        self.task = supervisor.start(TaskSpec(name="peer-send", owner="watch-web", work_id=identity,
            correlation_id=identity, deadline_seconds=limits.lifetime_seconds,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), self._send)

    def offer(self, message: dict[str, object]) -> None:
        if self.failed:
            return
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.stop(4008)

    def stop(self, code: int) -> None:
        if self.failed:
            return
        self.code, self.failed = code, True
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    async def _send(self) -> None:
        try:
            while not self.failed:
                message = await self.queue.get()
                if message is None:
                    break
                async with asyncio.timeout(1):
                    await self.socket.send(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.code, self.failed = 4008, True
        finally:
            self.failed = True
            while not self.queue.empty():
                self.queue.get_nowait()
            try:
                async with asyncio.timeout(1):
                    await self.socket.close(self.code)
            except Exception:
                # Failed socket closure is terminal; never retry or log peer data.
                self.failed = True


@dataclass(slots=True, repr=False)
class Command:
    operation: str
    arguments: tuple[Any, ...]
    deadline: float
    future: asyncio.Future[Any]


class WatchSession:
    def __init__(self, intent: Intent, writer: Writer, epoch: str, clock: Clock,
                 ids: IdGenerator, limits: WatchLimits, supervisor: TaskSupervisor, admit: Callable[[], None]) -> None:
        self.intent, self.writer, self.epoch, self.clock = intent, writer, epoch, clock
        self.limits, self.supervisor, self.ids = limits, supervisor, ids
        self.admit = admit
        self.mailbox: asyncio.Queue[Command] = asyncio.Queue(limits.mailbox)
        self.peers: dict[str, Peer] = {}
        self.revision = 0
        self.published = False
        self.closed = self.durable_closed = False
        self.empty_at: float | None = intent.created + 30 + 5
        self.playback: dict[str, object] = {"state": "paused", "time": 0.0}
        self.rate = Rate(limits.rate_per_second * limits.clients_per_session)
        identity = ids.new_id()
        self.task = supervisor.start(TaskSpec(name="session-mailbox", owner="watch-web", work_id=identity,
            correlation_id=identity, deadline_seconds=limits.lifetime_seconds + 5,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), self._run)

    def now(self) -> float:
        return self.clock.now().timestamp()

    async def call(self, operation: str, *arguments: Any) -> Any:
        if self.task.done() or (self.closed and operation not in {"close", "tick", "leave"}):
            raise ClosedSession("Watch session terminal")
        future = asyncio.get_running_loop().create_future()
        command = Command(operation, arguments, self.clock.monotonic()+5, future)
        try:
            self.mailbox.put_nowait(command)
        except asyncio.QueueFull:
            raise CapacityError("Watch mailbox full") from None
        try:
            async with asyncio.timeout(5):
                return await future
        except TimeoutError:
            raise DeadlineExceededError("Watch mailbox deadline") from None

    def broadcast(self, value: dict[str, object], exclude: str | None = None) -> None:
        self.revision += 1
        event = dict(value, revision=self.revision)
        for identity, peer in tuple(self.peers.items()):
            if identity != exclude:
                peer.offer(event)

    async def _close(self) -> None:
        if not self.closed:
            self.closed = True  # terminal before any awaited durable close
            self.broadcast({"type": "session_closed"})
            for peer in self.peers.values():
                peer.stop(4001)
            self.peers.clear()
        if not self.durable_closed:
            await self.writer.close(self.epoch, self.intent.session_id, self.now())
            self.durable_closed = True

    async def _apply(self, operation: str, args: tuple[Any, ...]) -> Any:
        now = self.now()
        if operation in {"close", "tick"}:
            if operation == "close" or self.closed or now >= self.intent.expires or self.empty_at is not None and now >= self.empty_at:
                await self._close()
            # Reap failed peers even when a transport disconnect is delayed.
            for identity, peer in tuple(self.peers.items()):
                if peer.failed:
                    await self._apply("leave", (identity,))
            return None
        if operation == "leave":
            identity = args[0]
            peer = self.peers.pop(identity, None)
            if peer:
                peer.stop(1000)
                if peer.name is not None:
                    self.broadcast({"type": "user_left", "username": peer.name, "message": f"👈 {peer.name}님이 시청방에서 퇴장하셨습니다."})
                    self.broadcast({"type": "user_list", "users": [p.name for p in self.peers.values() if p.name is not None]})
                if not self.peers:
                    self.empty_at = max(now, self.intent.created+30) + 5
            return None
        if self.closed or now >= self.intent.expires or self.empty_at is not None and now >= self.empty_at:
            await self._close()
            raise ClosedSession("Watch session expired")
        self.admit()
        sid = self.intent.session_id
        if operation == "connect":
            if len(self.peers) >= self.limits.clients_per_session:
                raise CapacityError("Watch session connection cap")
            socket = args[0]
            peer = Peer(socket, self.ids.new_id(), self.limits, self.supervisor)
            self.peers[peer.id] = peer
            self.empty_at = None
            return peer
        if operation == "message":
            identity, raw = args
            peer = self.peers.get(identity)
            if peer is None or peer.failed:
                raise ClosedSession("Watch peer closed")
            peer.rate.take(self.clock.monotonic())
            self.rate.take(self.clock.monotonic())
            value = protocol(raw)
            kind = value["type"]
            if kind == "join":
                if peer.name is not None:
                    return None
                peer.name = str(value["username"])
                self.broadcast({"type": "user_joined", "username": peer.name,
                    "message": f"👉 {peer.name}님이 시청방에 입장하셨습니다."}, exclude=identity)
                self.broadcast({"type": "user_list", "users": [p.name for p in self.peers.values() if p.name is not None]})
                self.broadcast({"type": "sync_request"}, exclude=identity)
            else:
                if kind == "chat":
                    value["username"] = peer.name or str(value.get("username", "임시유저"))
                if kind in {"state_change", "seek", "sync_response"}:
                    self.playback.update({key: field for key, field in value.items() if key != "type"})
                self.broadcast(value, exclude=identity)
            return None
        self.rate.take(self.clock.monotonic())
        if operation == "playlist":
            return await self.writer.playlist(self.epoch, sid, now)
        if operation == "add":
            url, title, by = args
            await self.writer.add(self.epoch, sid, url, title, by, now, self.limits.playlist)
            self.broadcast({"type": "playlist_change", "message": f"{by}님이 새 비디오를 추가했습니다."})
        elif operation == "remove":
            await self.writer.remove(self.epoch, sid, args[0], now)
            self.broadcast({"type": "playlist_change", "message": "비디오가 대기열에서 제거되었습니다."})
        elif operation == "bind":
            await self.writer.bind(self.epoch, sid, *args, now)
            if not args[2]:
                self.published = True
        else:
            raise InternalError("unknown Watch operation")

    async def _run(self) -> None:
        try:
            while not self.durable_closed:
                command = await self.mailbox.get()
                if command.future.cancelled():
                    continue
                try:
                    remaining = command.deadline-self.clock.monotonic()
                    if remaining <= 0:
                        raise DeadlineExceededError("Watch queued command expired")
                    async with asyncio.timeout(remaining):
                        result = await self._apply(command.operation, command.arguments)
                except TimeoutError:
                    error: AppError = DeadlineExceededError("Watch command deadline")
                    if not command.future.done():
                        command.future.set_exception(error)
                except AppError as error:
                    if not command.future.done():
                        command.future.set_exception(error)
                except asyncio.CancelledError:
                    if not command.future.done():
                        command.future.set_exception(ShutdownError("Watch actor stopping"))
                    raise
                except Exception:
                    if not command.future.done():
                        command.future.set_exception(InternalError("Watch command failed"))
                else:
                    if not command.future.done():
                        command.future.set_result(result)
                    elif isinstance(result, Peer):
                        await self._apply("leave", (result.id,))
                # Fair scheduling also lets fast sockets drain when many pure
                # broadcast commands were already queued in this mailbox.
                await asyncio.sleep(0)
        finally:
            self.closed = True
            for peer in self.peers.values():
                peer.stop(4001)
            self.peers.clear()
            while not self.mailbox.empty():
                command = self.mailbox.get_nowait()
                if not command.future.done():
                    command.future.set_exception(ClosedSession("Watch session closed"))
