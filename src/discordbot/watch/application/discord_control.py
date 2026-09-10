"""Discord-side orchestration. No session dictionary, repository, or web owner."""

import asyncio

from discordbot.platform.clock import Clock, IdGenerator
from discordbot.platform.errors import AppError, AuthorizationError, CapacityError, ExternalTemporaryError
from discordbot.platform.health import HealthRegistry, HealthStatus
from discordbot.platform.tasks import CancellationBehavior, TaskSpec, TaskSupervisor
from discordbot.platform.telemetry import TelemetryEmitter
from discordbot.watch.ports.discord import AdminMessages, Interaction
from discordbot.watch.ports.runtime import Control


class DiscordWatch:
    def __init__(self, control: Control, messages: AdminMessages, master: int, clock: Clock,
                 ids: IdGenerator, telemetry: TelemetryEmitter) -> None:
        self.control, self.messages, self.master, self.clock = control, messages, master, clock
        self.ids, self.telemetry = ids, telemetry
        self.health = HealthRegistry(capabilities=("loopback",), required=("loopback",), clock=clock)
        self.supervisor = TaskSupervisor(capacity=12, history_capacity=64, clock=clock)
        self._operations: dict[str, float] = {}  # bounded interaction dedupe receipts, no session state
        self._active = 0
        self._stopped = False
        self._maintenance = None

    async def refresh(self) -> None:
        try:
            status = await self.control.call("status", {})
            ready = status.get("ready") is True
            self.health.update("loopback", HealthStatus.OK if ready else HealthStatus.DOWN)
            self.health.start_accepting()
        except AppError:
            self.health.update("loopback", HealthStatus.DOWN)

    def schedule(self) -> None:
        if not self._stopped and (self._maintenance is None or self._maintenance.done()):
            identity = self.ids.new_id()
            self._maintenance = self.supervisor.start(TaskSpec(name="watch-control-cleanup", owner="discord-bot",
                work_id=identity, correlation_id=identity, deadline_seconds=60,
                cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), self._tick)
            self._maintenance.add_done_callback(lambda _: self.schedule())

    async def _tick(self) -> None:
        await asyncio.sleep(5)
        await self.refresh()
        if self.health.snapshot().ready:
            await self.cleanup()

    async def cleanup(self) -> None:
        result = await self.control.call("cleanup", {})
        for row in result.get("items", [])[:8]:
            try:
                for channel, message in ((row["channel"], row["message"]), (row["admin_channel"], row["admin_message"])):
                    if channel and message:
                        async with asyncio.timeout(2):
                            await self.messages.delete(channel, message)
                await self.control.call("ack", {"session_id": row["session_id"]})
            except (AppError, TimeoutError):
                self.telemetry.emit("watch.cleanup", component="watch", result="pending")

    async def request(self, interaction: Interaction) -> None:
        now = self.clock.monotonic()
        self._operations = {key: expiry for key, expiry in self._operations.items() if expiry > now}
        if interaction.operation in self._operations:
            return
        if self._stopped or self._active >= 8 or len(self._operations) >= 256:
            raise CapacityError("Discord Watch admission unavailable")
        self._operations[interaction.operation] = now+120
        self._active += 1
        identity = self.ids.new_id()
        try:
            task = self.supervisor.start(TaskSpec(name="watch-command", owner="discord-bot", work_id=identity,
                correlation_id=identity, deadline_seconds=60,
                cancellation_behavior=CancellationBehavior.DRAIN_UNTIL_DEADLINE), lambda: self._request(interaction))
            await task
        finally:
            self._active -= 1

    async def _request(self, interaction: Interaction) -> None:
        data = {"guild": interaction.guild, "user": interaction.user,
            "operation": interaction.operation, "issued": interaction.issued}
        admin = None
        attempted = False
        try:
            await interaction.acknowledge()
            attempted = True
            created = await self.control.call("create", data)
            if created["published"]:
                return
            sid = created["session_id"]
            admin = await self.messages.create(sid, interaction.guild, interaction.user)
            await self.control.call("bind", {"session_id": sid, "channel": admin[0], "message": admin[1], "admin": True})
            channel, message = await interaction.invite(created["capability"])
            await self.control.call("bind", {"session_id": sid, "channel": channel, "message": message, "admin": False})
            self.health.update("loopback", HealthStatus.OK)
        except BaseException as error:
            if attempted:
                await self._compensate(data)
            try:
                async with asyncio.timeout(2):
                    await interaction.retract()
                    if admin:
                        await self.messages.delete(*admin)
            except Exception:
                self.telemetry.emit("watch.invite_cleanup", component="watch", result="pending")
            self.telemetry.emit("watch.invite", component="watch", result="failed")
            if isinstance(error, asyncio.CancelledError):
                raise
            if not isinstance(error, Exception):
                raise
            await interaction.failure()

    async def _compensate(self, data: dict[str, object]) -> None:
        try:
            async with asyncio.timeout(2):
                for _ in range(3):
                    try:
                        await self.control.call("abort", data)
                        return
                    except AppError:
                        self.health.update("loopback", HealthStatus.DOWN)
        except TimeoutError:
            self.health.update("loopback", HealthStatus.DOWN)
        self.telemetry.emit("watch.compensation", component="watch", result="pending_expiry")

    async def master_close(self, user: int, session_id: str) -> None:
        if user != self.master:
            raise AuthorizationError("Watch master control denied", safe_message="이 버튼을 사용할 권한이 없습니다.")
        async def close_and_clean() -> None:
            await self.control.call("close", {"session_id": session_id})
            await self.cleanup()
        identity = self.ids.new_id()
        await self.supervisor.start(TaskSpec(name="watch-master-close", owner="discord-bot",
            work_id=identity, correlation_id=identity, deadline_seconds=8,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), close_and_clean)

    async def stop(self) -> None:
        self._stopped = True
        self.health.stop_accepting()
        await self.supervisor.shutdown(grace_seconds=2)
        self._operations.clear()
        self.health.stop_liveness()
