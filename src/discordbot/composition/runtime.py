"""Process-neutral startup and shutdown orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from discordbot.composition.config import PlatformConfig
from discordbot.platform.clock import Clock, SystemClock
from discordbot.platform.errors import ConflictError, ShutdownError, StartupError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.health import HealthRegistry, HealthStatus
from discordbot.platform.tasks import LifecycleTasks, ShutdownReport, TaskObservation, TaskResult, TaskSupervisor
from discordbot.platform.telemetry import (
    MetricRegistry,
    TelemetryBuffer,
    TelemetryEmitter,
)


class ManagedResource(Protocol):
    name: str
    required: bool

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class RuntimeState(StrEnum):
    NEW = "new"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RuntimeShutdownReport:
    tasks: ShutdownReport
    resource_errors: tuple[str, ...]


class ProcessRuntime:
    """Owns only platform lifecycle; feature adapters are injected later."""

    def __init__(
        self,
        *,
        config: PlatformConfig,
        resources: tuple[ManagedResource, ...] = (),
        clock: Clock | None = None,
    ) -> None:
        names = tuple(resource.name for resource in resources)
        if len(set(names)) != len(names):
            raise ValueError("resource names must be unique")
        self.config = config
        self.clock = clock or SystemClock()
        self.resources = resources
        self.telemetry_buffer = TelemetryBuffer(config.limits.telemetry_queue_capacity)
        self.telemetry = TelemetryEmitter(
            buffer=self.telemetry_buffer,
            clock=self.clock,
            service=config.service.value,
            environment=config.environment.value,
            release=config.release,
        )
        self.metrics = MetricRegistry(config.limits.metrics_series_capacity)
        capabilities = ("platform", *names)
        required = ("platform", *(resource.name for resource in resources if resource.required))
        self.health = HealthRegistry(
            capabilities=capabilities,
            required=required,
            clock=self.clock,
        )
        self.supervisor = TaskSupervisor(
            capacity=config.limits.task_capacity,
            history_capacity=config.limits.task_capacity * 4,
            clock=self.clock,
            observer=self._observe_task,
        )
        self.executor = BoundedExecutor(
            workers=config.limits.executor_workers,
            queue_capacity=config.limits.executor_queue_capacity,
            name=f"{config.service.value}-blocking",
        )
        self.state = RuntimeState.NEW
        self._started_resources: list[ManagedResource] = []
        self.lifecycle = LifecycleTasks()
        self._shutdown_report: RuntimeShutdownReport | None = None
        self._deadline: float | None = None
        self._cleanup_failed = False
        self.shutdown_epoch: Callable[[], float] | None = None
        self._shutdown_owner = LifecycleTasks(capacity=1)
        self._shutdown_task: asyncio.Task[RuntimeShutdownReport] | None = None

    def begin_shutdown(self, deadline: float | None = None) -> float:
        proposed = deadline if deadline is not None else (
            asyncio.get_running_loop().time() + self.config.runtime.shutdown_grace_seconds)
        if self.shutdown_epoch is not None:
            proposed = min(proposed, self.shutdown_epoch() + self.config.runtime.shutdown_grace_seconds)
        self._deadline = min(self._deadline, proposed) if self._deadline is not None else proposed
        self.health.stop_accepting()
        self.supervisor.stop_accepting()
        return self._deadline

    def _observe_task(self, observation: TaskObservation) -> None:
        self.metrics.increment(
            "task_result_total",
            labels={
                "result": observation.result.value,
                "criticality": observation.spec.criticality.value,
            },
        )
        if not observation.spec.emit_routine_events and observation.result in {
            TaskResult.STARTED, TaskResult.SUCCEEDED,
        }:
            return
        self.telemetry.emit(
            f"task.{observation.result.value}",
            component="task_supervisor",
            result=observation.result.value,
            fields={
                "task_name": observation.spec.name,
                "owner_type": observation.spec.owner,
                "attempt": observation.attempt,
                "age_seconds": observation.age_seconds,
                "error_type": observation.error_type,
            },
        )

    async def start(self) -> None:
        if self.state is not RuntimeState.NEW:
            raise ConflictError(f"cannot start runtime in state {self.state.value}")
        self.state = RuntimeState.STARTING
        self.telemetry.emit("runtime.starting", component="composition", result="started")
        try:
            deadline = asyncio.get_running_loop().time() + self.config.runtime.startup_timeout_seconds
            self.health.update("platform", HealthStatus.OK)
            for resource in self.resources:
                await self.lifecycle.run(resource.start(), name="resource-start", deadline=deadline)
                self._started_resources.append(resource)
                self.health.update(resource.name, HealthStatus.OK)
        except asyncio.CancelledError:
            self.state = RuntimeState.FAILED
            await self._rollback_startup()
            self.health.update("platform", HealthStatus.DOWN, detail="CancelledError")
            self.telemetry.emit(
                "runtime.startup_cancelled",
                component="composition",
                result="cancelled",
            )
            raise
        except Exception as exc:
            self.state = RuntimeState.FAILED
            await self._rollback_startup()
            self.health.update("platform", HealthStatus.DOWN, detail=type(exc).__name__)
            self.telemetry.emit(
                "runtime.startup_failed",
                component="composition",
                result="failed",
                fields={"error_type": type(exc).__name__},
            )
            raise StartupError(
                "runtime startup failed",
                context={"service": self.config.service.value, "error_type": type(exc).__name__},
            ) from exc
        self.health.start_accepting()
        self.state = RuntimeState.RUNNING
        self.telemetry.emit("runtime.started", component="composition", result="ok")

    async def _rollback_startup(self) -> None:
        deadline = self.begin_shutdown()
        # A resistant start still owns its dependencies. Do not roll them back
        # underneath it, or start a second cleanup owner after timeout.
        if self.lifecycle.pending:
            self._cleanup_failed = True
            return
        errors = await self._stop_resources(deadline)
        self._cleanup_failed = bool(errors)

    async def _stop_resources(self, deadline: float) -> list[str]:
        errors: list[str] = []
        while self._started_resources:
            resource = self._started_resources[-1]
            try:
                await self.lifecycle.run(resource.stop(), name="resource-stop", deadline=deadline)
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(f"{resource.name}:{type(exc).__name__}")
                self.health.update(resource.name, HealthStatus.DOWN, detail=type(exc).__name__)
                # Failure cannot prove the owner's handles/work are released.
                # Retain this resource and all dependencies for outer escalation.
                break
            self._started_resources.pop()
        return errors

    async def shutdown(self) -> RuntimeShutdownReport:
        if self._shutdown_task is None:
            self._shutdown_task = self._shutdown_owner.start(self._shutdown(), name="runtime-shutdown")
        # Caller cancellation cannot detach or transfer the single cleanup owner.
        return await asyncio.shield(self._shutdown_task)

    async def _shutdown(self) -> RuntimeShutdownReport:
        if self._shutdown_report is not None:
            return self._shutdown_report
        if self.state not in {RuntimeState.RUNNING, RuntimeState.FAILED}:
            raise ConflictError(f"cannot stop runtime in state {self.state.value}")

        self.state = RuntimeState.STOPPING
        deadline = self.begin_shutdown()
        errors: list[str] = []
        task_report = await self.supervisor.shutdown(
            grace_seconds=max(0, deadline - asyncio.get_running_loop().time())
        )
        if not task_report.remaining and not self.lifecycle.pending and not self._cleanup_failed:
            # A cancelled awaiter may leave finite blocking work behind. Give it
            # the remaining common grace before deciding dependencies are unsafe.
            while self.executor.admitted and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(min(.01, max(0, deadline - asyncio.get_running_loop().time())))
        if task_report.remaining or self.lifecycle.pending or self._cleanup_failed or self.executor.admitted:
            errors.append("outstanding_owners")
        else:
            errors.extend(await self._stop_resources(deadline))
        try:
            await self.executor.close(
                grace_seconds=max(0, deadline - asyncio.get_running_loop().time())
            )
        except Exception as exc:
            errors.append(f"executor:{type(exc).__name__}")
        self.health.update(
            "platform",
            HealthStatus.DOWN if errors else HealthStatus.OK,
            detail=",".join(errors) or None,
        )
        self.health.stop_liveness()
        self.state = RuntimeState.FAILED if errors or task_report.remaining else RuntimeState.STOPPED
        self.telemetry.emit(
            "runtime.stopped",
            component="composition",
            result="degraded" if errors else "ok",
            fields={"error_count": len(errors)},
        )
        self._shutdown_report = RuntimeShutdownReport(tasks=task_report, resource_errors=tuple(errors))
        return self._shutdown_report


def require_clean_shutdown(report: RuntimeShutdownReport) -> None:
    if report.tasks.remaining or report.resource_errors:
        raise ShutdownError(
            "runtime did not shut down cleanly",
            context={
                "remaining_tasks": report.tasks.remaining,
                "resource_error_count": len(report.resource_errors),
            },
        )
