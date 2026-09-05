"""Bounded ownership and lifecycle supervision for asynchronous work."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any, Generic, TypeVar

from discordbot.platform.clock import Clock
from discordbot.platform.context import CorrelationContext, correlation_scope
from discordbot.platform.errors import (
    AppError,
    CapacityError,
    ConflictError,
    DeadlineExceededError,
)

T = TypeVar("T")


class TaskCriticality(StrEnum):
    OPTIONAL = "optional"
    NORMAL = "normal"
    CRITICAL = "critical"


class CancellationBehavior(StrEnum):
    CANCEL_ON_SHUTDOWN = "cancel_on_shutdown"
    DRAIN_UNTIL_DEADLINE = "drain_until_deadline"


class RestartMode(StrEnum):
    NEVER = "never"
    ON_TRANSIENT_ERROR = "on_transient_error"


class ShutdownPhase(IntEnum):
    ADMISSION = 10
    WORK = 20
    FLUSH = 30


class TaskResult(StrEnum):
    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"


@dataclass(frozen=True, slots=True)
class RestartPolicy:
    mode: RestartMode = RestartMode.NEVER
    max_restarts: int = 0
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.max_restarts <= 3:
            raise ValueError("max_restarts must be between 0 and 3")
        if not 0.0 <= self.backoff_seconds <= 60.0:
            raise ValueError("backoff_seconds must be between 0 and 60")
        if self.mode is RestartMode.NEVER and self.max_restarts != 0:
            raise ValueError("never restart policy cannot have restarts")
        if self.mode is RestartMode.ON_TRANSIENT_ERROR and self.max_restarts < 1:
            raise ValueError("transient restart policy requires at least one restart")


@dataclass(frozen=True, slots=True)
class TaskSpec:
    name: str
    owner: str
    work_id: str
    correlation_id: str
    deadline_seconds: float
    criticality: TaskCriticality = TaskCriticality.NORMAL
    cancellation_behavior: CancellationBehavior = CancellationBehavior.DRAIN_UNTIL_DEADLINE
    restart_policy: RestartPolicy = RestartPolicy()
    shutdown_phase: ShutdownPhase = ShutdownPhase.WORK

    def __post_init__(self) -> None:
        for field_name in ("name", "owner", "work_id", "correlation_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be blank")
        if not 0 < self.deadline_seconds <= 86_400:
            raise ValueError("deadline_seconds must be between 0 and 86400")


@dataclass(frozen=True, slots=True)
class TaskObservation:
    spec: TaskSpec
    result: TaskResult
    observed_at: float
    attempt: int
    age_seconds: float
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ActiveTask:
    spec: TaskSpec
    started_at: float
    deadline_at: float
    age_seconds: float


@dataclass(frozen=True, slots=True)
class SupervisorSnapshot:
    accepting_work: bool
    capacity: int
    active: tuple[ActiveTask, ...]
    observations: tuple[TaskObservation, ...]
    dropped_observations: int
    observer_failures: int


@dataclass(frozen=True, slots=True)
class ShutdownReport:
    completed: int
    cancelled: int
    remaining: int


@dataclass(slots=True)
class _RunningTask(Generic[T]):
    spec: TaskSpec
    started_at: float
    task: asyncio.Task[T]
    attempt: int = 1


ObservationSink = Callable[[TaskObservation], None]
WorkFactory = Callable[[], Awaitable[T]]


class TaskSupervisor:
    """The sole V2 gateway for creating and observing background tasks."""

    def __init__(
        self,
        *,
        capacity: int,
        history_capacity: int,
        clock: Clock,
        observer: ObservationSink | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if history_capacity < 1:
            raise ValueError("history_capacity must be positive")
        self._capacity = capacity
        self._history_capacity = history_capacity
        self._clock = clock
        self._observer = observer
        self._accepting_work = True
        self._active: dict[asyncio.Task[Any], _RunningTask[Any]] = {}
        self._observations: deque[TaskObservation] = deque()
        self._dropped_observations = 0
        self._observer_failures = 0

    def start(self, spec: TaskSpec, work_factory: WorkFactory[T]) -> asyncio.Task[T]:
        if not self._accepting_work:
            raise ConflictError("task supervisor is not accepting work")
        if len(self._active) >= self._capacity:
            raise CapacityError(
                "task supervisor capacity exhausted",
                context={"capacity": self._capacity},
            )

        loop = asyncio.get_running_loop()
        started_at = self._clock.monotonic()
        task = loop.create_task(
            self._run(spec, work_factory),
            name=f"{spec.owner}:{spec.work_id}:{spec.name}",
        )
        running = _RunningTask(spec=spec, started_at=started_at, task=task)
        self._active[task] = running
        self._record(running, TaskResult.STARTED)
        task.add_done_callback(self._observe_completion)
        return task

    async def _run(self, spec: TaskSpec, work_factory: WorkFactory[T]) -> T:
        attempt = 1
        with correlation_scope(CorrelationContext(spec.correlation_id)):
            try:
                async with asyncio.timeout(spec.deadline_seconds):
                    while True:
                        try:
                            return await work_factory()
                        except AppError as exc:
                            policy = spec.restart_policy
                            if (
                                not exc.retryable
                                or policy.mode is RestartMode.NEVER
                                or attempt > policy.max_restarts
                            ):
                                raise
                            attempt += 1
                            running = self._active.get(asyncio.current_task())
                            if running is not None:
                                running.attempt = attempt
                                self._record(
                                    running,
                                    TaskResult.RETRYING,
                                    error_type=type(exc).__name__,
                                )
                            if policy.backoff_seconds:
                                await asyncio.sleep(policy.backoff_seconds)
            except TimeoutError as exc:
                raise DeadlineExceededError(
                    f"task {spec.name} exceeded {spec.deadline_seconds} seconds",
                    context={"owner": spec.owner, "task": spec.name},
                ) from exc

    def _observe_completion(self, task: asyncio.Task[Any]) -> None:
        running = self._active.pop(task, None)
        if running is None:
            return
        error_type: str | None = None
        if task.cancelled():
            result = TaskResult.CANCELLED
        else:
            exception = task.exception()
            if exception is None:
                result = TaskResult.SUCCEEDED
            elif isinstance(exception, DeadlineExceededError):
                result = TaskResult.DEADLINE_EXCEEDED
                error_type = type(exception).__name__
            else:
                result = TaskResult.FAILED
                error_type = type(exception).__name__
        self._record(running, result, error_type=error_type)

    def _record(
        self,
        running: _RunningTask[Any],
        result: TaskResult,
        *,
        error_type: str | None = None,
    ) -> None:
        now = self._clock.monotonic()
        observation = TaskObservation(
            spec=running.spec,
            result=result,
            observed_at=now,
            attempt=running.attempt,
            age_seconds=max(0.0, now - running.started_at),
            error_type=error_type,
        )
        if len(self._observations) >= self._history_capacity:
            self._observations.popleft()
            self._dropped_observations += 1
        self._observations.append(observation)
        if self._observer is not None:
            try:
                self._observer(observation)
            except Exception:
                # Observation failure is itself retained as a bounded counter;
                # it must never hide or alter the task's outcome.
                self._observer_failures += 1

    def stop_accepting(self) -> None:
        self._accepting_work = False

    def snapshot(self) -> SupervisorSnapshot:
        now = self._clock.monotonic()
        active = tuple(
            ActiveTask(
                spec=running.spec,
                started_at=running.started_at,
                deadline_at=running.started_at + running.spec.deadline_seconds,
                age_seconds=max(0.0, now - running.started_at),
            )
            for running in self._active.values()
        )
        return SupervisorSnapshot(
            accepting_work=self._accepting_work,
            capacity=self._capacity,
            active=active,
            observations=tuple(self._observations),
            dropped_observations=self._dropped_observations,
            observer_failures=self._observer_failures,
        )

    async def shutdown(self, *, grace_seconds: float) -> ShutdownReport:
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        self.stop_accepting()
        if not self._active:
            return ShutdownReport(completed=0, cancelled=0, remaining=0)

        initial_tasks = tuple(self._active)
        immediate = sorted(
            (
                running
                for running in self._active.values()
                if running.spec.cancellation_behavior is CancellationBehavior.CANCEL_ON_SHUTDOWN
            ),
            key=lambda running: running.spec.shutdown_phase,
        )
        for running in immediate:
            running.task.cancel()

        _, pending = await asyncio.wait(initial_tasks, timeout=grace_seconds)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        # done callbacks are scheduled by the event loop; yield once so the
        # returned report and snapshot reflect every observed terminal state.
        await asyncio.sleep(0)
        cancelled = sum(task.cancelled() for task in initial_tasks)
        return ShutdownReport(
            completed=len(initial_tasks) - cancelled,
            cancelled=cancelled,
            remaining=len(self._active),
        )
