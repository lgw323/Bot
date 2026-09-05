import asyncio

import pytest

from discordbot.platform.clock import SystemClock
from discordbot.platform.context import current_correlation
from discordbot.platform.errors import (
    CapacityError,
    ConflictError,
    DeadlineExceededError,
    ExternalTemporaryError,
)
from discordbot.platform.tasks import (
    CancellationBehavior,
    RestartMode,
    RestartPolicy,
    ShutdownPhase,
    TaskCriticality,
    TaskResult,
    TaskSpec,
    TaskSupervisor,
)


def _spec(
    name: str = "worker",
    *,
    deadline: float = 1.0,
    cancellation: CancellationBehavior = CancellationBehavior.DRAIN_UNTIL_DEADLINE,
    restart: RestartPolicy = RestartPolicy(),
) -> TaskSpec:
    return TaskSpec(
        name=name,
        owner="summary",
        work_id="job-7",
        correlation_id="correlation-9",
        deadline_seconds=deadline,
        criticality=TaskCriticality.NORMAL,
        cancellation_behavior=cancellation,
        restart_policy=restart,
        shutdown_phase=ShutdownPhase.WORK,
    )


@pytest.mark.asyncio
async def test_supervisor_owns_metadata_context_and_success_observation() -> None:
    observations = []
    supervisor = TaskSupervisor(
        capacity=2,
        history_capacity=8,
        clock=SystemClock(),
        observer=observations.append,
    )

    async def work() -> str:
        context = current_correlation()
        assert context is not None
        assert context.correlation_id == "correlation-9"
        await asyncio.sleep(0)
        return "done"

    task = supervisor.start(_spec(), work)
    snapshot = supervisor.snapshot()
    assert task.get_name() == "summary:job-7:worker"
    assert snapshot.active[0].spec.work_id == "job-7"
    assert snapshot.active[0].deadline_at > snapshot.active[0].started_at

    assert await task == "done"
    await asyncio.sleep(0)
    results = [observation.result for observation in observations]
    assert results == [TaskResult.STARTED, TaskResult.SUCCEEDED]
    assert supervisor.snapshot().active == ()


@pytest.mark.asyncio
async def test_supervisor_rejects_capacity_without_creating_coroutine() -> None:
    supervisor = TaskSupervisor(
        capacity=1,
        history_capacity=4,
        clock=SystemClock(),
    )
    release = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    first = supervisor.start(_spec("first"), blocked)
    with pytest.raises(CapacityError):
        supervisor.start(_spec("second"), blocked)

    release.set()
    await first
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_task_exception_is_observed_and_remains_visible_to_awaiter() -> None:
    supervisor = TaskSupervisor(
        capacity=1,
        history_capacity=4,
        clock=SystemClock(),
    )

    async def failing() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await supervisor.start(_spec(), failing)
    await asyncio.sleep(0)

    terminal = supervisor.snapshot().observations[-1]
    assert terminal.result is TaskResult.FAILED
    assert terminal.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_deadline_is_typed_and_observed() -> None:
    supervisor = TaskSupervisor(
        capacity=1,
        history_capacity=4,
        clock=SystemClock(),
    )

    async def stalled() -> None:
        await asyncio.Event().wait()

    with pytest.raises(DeadlineExceededError):
        await supervisor.start(_spec(deadline=0.01), stalled)
    await asyncio.sleep(0)

    assert supervisor.snapshot().observations[-1].result is TaskResult.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_transient_restart_is_bounded_and_observed() -> None:
    supervisor = TaskSupervisor(
        capacity=1,
        history_capacity=8,
        clock=SystemClock(),
    )
    attempts = 0

    async def transient_then_success() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ExternalTemporaryError("temporary")
        return "recovered"

    result = await supervisor.start(
        _spec(
            restart=RestartPolicy(
                mode=RestartMode.ON_TRANSIENT_ERROR,
                max_restarts=1,
            )
        ),
        transient_then_success,
    )
    await asyncio.sleep(0)

    assert result == "recovered"
    assert attempts == 2
    assert [item.result for item in supervisor.snapshot().observations] == [
        TaskResult.STARTED,
        TaskResult.RETRYING,
        TaskResult.SUCCEEDED,
    ]


@pytest.mark.asyncio
async def test_shutdown_stops_admission_drains_then_cancels_and_reaps() -> None:
    supervisor = TaskSupervisor(
        capacity=2,
        history_capacity=8,
        clock=SystemClock(),
    )
    cancellation_seen = asyncio.Event()

    async def long_running() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancellation_seen.set()

    task = supervisor.start(
        _spec(cancellation=CancellationBehavior.CANCEL_ON_SHUTDOWN),
        long_running,
    )
    await asyncio.sleep(0)
    report = await supervisor.shutdown(grace_seconds=0.1)

    assert report.cancelled == 1
    assert report.remaining == 0
    assert cancellation_seen.is_set()
    assert task.cancelled()
    assert supervisor.snapshot().observations[-1].result is TaskResult.CANCELLED
    with pytest.raises(ConflictError):
        supervisor.start(_spec("late"), long_running)


def test_restart_and_task_metadata_are_bounded_and_validated() -> None:
    with pytest.raises(ValueError, match="between 0 and 3"):
        RestartPolicy(mode=RestartMode.ON_TRANSIENT_ERROR, max_restarts=4)
    with pytest.raises(ValueError, match="requires at least one"):
        RestartPolicy(mode=RestartMode.ON_TRANSIENT_ERROR, max_restarts=0)
    with pytest.raises(ValueError, match="work_id"):
        TaskSpec(
            name="worker",
            owner="summary",
            work_id="",
            correlation_id="correlation",
            deadline_seconds=1,
        )


def test_start_without_event_loop_fails_before_coroutine_construction() -> None:
    supervisor = TaskSupervisor(
        capacity=1,
        history_capacity=4,
        clock=SystemClock(),
    )
    factory_called = False

    async def work() -> None:
        nonlocal factory_called
        factory_called = True

    with pytest.raises(RuntimeError, match="running event loop"):
        supervisor.start(_spec(), work)
    assert factory_called is False
    assert supervisor.snapshot().active == ()
