import asyncio
import threading

import pytest

from discordbot.platform.errors import CapacityError, ConflictError
from discordbot.platform.executors import BoundedExecutor


@pytest.mark.asyncio
async def test_executor_rejects_work_beyond_running_and_queue_capacity() -> None:
    executor = BoundedExecutor(workers=1, queue_capacity=0, name="test-bounded")
    started = threading.Event()
    release = threading.Event()

    def blocking_work() -> str:
        started.set()
        release.wait(timeout=2)
        return "done"

    first = asyncio.create_task(executor.run(blocking_work))
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0)
    assert started.is_set()

    with pytest.raises(CapacityError):
        await executor.run(lambda: "overflow")

    release.set()
    assert await first == "done"
    assert executor.admitted == 0
    await executor.close()

    with pytest.raises(ConflictError):
        await executor.run(lambda: "closed")


@pytest.mark.asyncio
async def test_cancelling_awaiter_does_not_release_running_thread_capacity() -> None:
    executor = BoundedExecutor(workers=1, queue_capacity=0, name="test-cancel")
    started = threading.Event()
    release = threading.Event()

    def blocking_work() -> None:
        started.set()
        release.wait(timeout=2)

    task = asyncio.create_task(executor.run(blocking_work))
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0)
    assert started.is_set()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert executor.admitted == 1
    with pytest.raises(CapacityError):
        await executor.run(lambda: None)

    release.set()
    for _ in range(100):
        if executor.admitted == 0:
            break
        await asyncio.sleep(0.001)
    assert executor.admitted == 0
    await executor.close()


@pytest.mark.asyncio
async def test_retained_file_operation_transfers_result_after_cancellation() -> None:
    executor = BoundedExecutor(workers=1, queue_capacity=0, name="retained-file")
    started, release = threading.Event(), threading.Event()
    def operation():
        started.set()
        release.wait(2)
        return "owned-result"
    task = asyncio.create_task(executor.run_retained(operation))
    try:
        for _ in range(200):
            if started.is_set(): break
            await asyncio.sleep(.001)
        assert started.is_set()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and executor.admitted == 1
        release.set()
        assert await task == "owned-result"
        assert executor.admitted == 0
    finally:
        release.set()
        await executor.close(grace_seconds=2)
