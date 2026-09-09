"""watch-web process owner; never imports Discord or shares state with its process."""

import asyncio
from dataclasses import asdict

from discordbot.platform.clock import Clock, IdGenerator
from discordbot.platform.errors import AppError, CapacityError, ConflictError, ExternalTemporaryError, ShutdownError, ValidationError
from discordbot.platform.health import HealthRegistry, HealthStatus
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor
from discordbot.platform.telemetry import TelemetryEmitter
from discordbot.watch.application.session import Peer, WatchSession
from discordbot.watch.domain.policy import ClosedSession, Intent, Invite, InvalidCapability, WatchLimits, display, video_id
from discordbot.watch.ports.runtime import Capability, Metadata, Socket, Writer


class WatchService:
    def __init__(self, writer: Writer, capability: Capability, metadata: Metadata, limits: WatchLimits,
                 clock: Clock, ids: IdGenerator, telemetry: TelemetryEmitter) -> None:
        self.writer, self.capability, self.metadata, self.limits = writer, capability, metadata, limits
        self.clock, self.ids, self.telemetry = clock, ids, telemetry
        self.epoch = ids.new_id()
        self.supervisor = TaskSupervisor(capacity=96, history_capacity=128, clock=clock)
        self.health = HealthRegistry(capabilities=("repository", "stale-cleanup", "session-runtime"),
            required=("repository", "stale-cleanup", "session-runtime"), clock=clock)
        self.sessions: dict[str, WatchSession] = {}
        self._creating = 0
        self._connecting = 0
        self._gate = asyncio.Lock()
        self._started = False
        self._stopped = False
        self._lease_until = 0.0
        self._maintenance: asyncio.Task[None] | None = None

    def now(self) -> float:
        return self.clock.now().timestamp()

    def require(self) -> None:
        if not self.ready():
            raise ShutdownError("Watch runtime unavailable")

    def ready(self) -> bool:
        return self.health.snapshot().ready and self.now() < self._lease_until

    async def start(self) -> None:
        if self._started:
            return
        if self._stopped:
            raise ShutdownError("Watch runtime stopped")
        try:
            lease_at = self.now()
            await self.writer.start(self.epoch, lease_at)
            self._lease_until = lease_at+10
            for name in ("repository", "stale-cleanup", "session-runtime"):
                self.health.update(name, HealthStatus.OK)
            self._started = True
            self.health.start_accepting()
        except BaseException:
            self.health.update("repository", HealthStatus.DOWN)
            raise

    def schedule(self) -> None:
        if self._started and not self._stopped and (self._maintenance is None or self._maintenance.done()):
            identity = self.ids.new_id()
            self._maintenance = self.supervisor.start(TaskSpec(name="watch-maintenance", owner="watch-web",
                work_id=identity, correlation_id=identity, deadline_seconds=60,
                cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), self._tick)
            self._maintenance.add_done_callback(lambda _: self.schedule())

    async def _tick(self) -> None:
        await asyncio.sleep(1)
        await self.sweep()

    async def sweep(self) -> None:
        try:
            lease_at = self.now()
            await self.writer.heartbeat(self.epoch, lease_at)
            self._lease_until = lease_at+10
            checks = []
            for sid, actor in tuple(self.sessions.items()):
                if not actor.task.done():
                    identity = self.ids.new_id()
                    checks.append(self.supervisor.start(TaskSpec(name="session-expiry", owner="watch-web",
                        work_id=identity, correlation_id=identity, deadline_seconds=6,
                        cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN),
                        lambda target=actor: target.call("tick")))
            if checks:
                outcomes = await asyncio.gather(*checks, return_exceptions=True)
                if any(isinstance(outcome, BaseException) for outcome in outcomes):
                    raise ConflictError("Watch expiry check failed")
            for sid, actor in tuple(self.sessions.items()):
                if actor.task.done() and not actor.durable_closed:
                    await self.writer.close(self.epoch, sid, self.now())
                    actor.durable_closed = True
                if actor.durable_closed:
                    self.sessions.pop(sid, None)
            self.health.update("repository", HealthStatus.OK)
        except AppError:
            self.health.update("repository", HealthStatus.DOWN)
            for actor in self.sessions.values():
                for peer in actor.peers.values():
                    peer.stop(4001)
            self.telemetry.emit("watch.maintenance", component="watch", result="failed")

    async def create(self, guild: int, user: int, operation: str, issued: int) -> Invite:
        self.require()
        if type(issued) is not int or abs(self.now()-issued) > 60:
            raise ValidationError("Watch create timestamp outside retry window")
        token, sid = self.capability.mint(guild, user, operation, issued)
        if self._creating >= self.limits.sessions:
            raise CapacityError("Watch create admission full")
        self._creating += 1
        try:
            async with self._gate:
                self.require()
                if sid in self.sessions:
                    actor = self.sessions[sid]
                    if actor.closed:
                        raise ClosedSession("Watch duplicate terminal create")
                    return Invite(sid, token, actor.intent.expires, actor.published)
                if len(self.sessions) >= self.limits.sessions:
                    raise CapacityError("Watch session capacity")
                try:
                    intent = await self.writer.create(self.epoch, Intent(sid, guild, user, self.now(),
                        self.now()+self.limits.lifetime_seconds), self.now())
                    self.sessions[sid] = WatchSession(intent, self.writer, self.epoch, self.clock, self.ids, self.limits, self.supervisor, self.require)
                except BaseException:
                    await self.writer.close(self.epoch, sid, self.now())
                    raise
                return Invite(sid, token, intent.expires)
        finally:
            self._creating -= 1

    def resolve(self, token: str) -> WatchSession:
        self.require()
        actor = self.sessions.get(self.capability.digest(token))
        if actor is None or actor.closed or actor.intent.expires <= self.now():
            raise InvalidCapability("Watch capability not active")
        return actor

    async def connect(self, token: str, socket: Socket) -> tuple[WatchSession, Peer]:
        actor = self.resolve(token)
        if sum(len(a.peers) for a in self.sessions.values()) + self._connecting >= self.limits.total_clients:
            raise CapacityError("Watch total connection capacity")
        self._connecting += 1
        try:
            peer = await actor.call("connect", socket)
            return actor, peer
        finally:
            self._connecting -= 1

    async def close(self, sid: str) -> None:
        self.require()
        async with self._gate:
            actor = self.sessions.get(sid)
            if actor is not None and not actor.task.done():
                await actor.call("close")
            else:
                await self.writer.close(self.epoch, sid, self.now())
            self.sessions.pop(sid, None)

    async def abort(self, guild: int, user: int, operation: str, issued: int) -> None:
        self.require()
        if type(issued) is not int or issued < 0 or issued > self.now()+60:
            raise ValidationError("invalid Watch abort timestamp")
        _, sid = self.capability.mint(guild, user, operation, issued)
        async with self._gate:
            actor = self.sessions.get(sid)
            if actor is not None and not actor.task.done():
                await actor.call("close")
            await self.writer.abort(self.epoch, Intent(sid, guild, user, self.now(),
                self.now()+self.limits.lifetime_seconds), self.now())
            self.sessions.pop(sid, None)

    async def add(self, token: str, url: str, by: str) -> str:
        actor = self.resolve(token)
        identity = video_id(url)
        by = display(by, 50, "임시유저")
        title = "알 수 없는 유튜브 비디오"
        try:
            title = await self.metadata.title(identity)
        except ExternalTemporaryError:
            self.telemetry.emit("watch.metadata", component="watch", result="unavailable")
        await actor.call("add", url.strip(), display(title, 200, "알 수 없는 유튜브 비디오"), by)
        return title

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.health.stop_accepting()
        if self._maintenance:
            self._maintenance.cancel()
        try:
            async with asyncio.timeout(5):
                for actor in tuple(self.sessions.values()):
                    if not actor.task.done():
                        try:
                            await actor.call("close")
                        except AppError:
                            self.telemetry.emit("watch.shutdown", component="watch", result="uncertain_close")
        except TimeoutError:
            self.telemetry.emit("watch.shutdown", component="watch", result="deadline")
        finally:
            await self.supervisor.shutdown(grace_seconds=1)
            self.sessions.clear()
            try:
                await self.writer.release(self.epoch)
            finally:
                await self.metadata.close()
                self.health.stop_liveness()
