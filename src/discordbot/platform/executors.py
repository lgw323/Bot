"""Bounded access to blocking work for Raspberry Pi-safe resource control."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, TypeVar

from discordbot.platform.errors import CapacityError, ConflictError

T = TypeVar("T")


class BoundedExecutor:
    """Reject work beyond the configured running-plus-waiting ceiling."""

    def __init__(self, *, workers: int, queue_capacity: int, name: str) -> None:
        if workers < 1:
            raise ValueError("workers must be positive")
        if queue_capacity < 0:
            raise ValueError("queue_capacity must be non-negative")
        if not name.strip():
            raise ValueError("name must not be blank")
        self._capacity = workers + queue_capacity
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self._admitted = 0
        self._closed = False
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def admitted(self) -> int:
        with self._lock:
            return self._admitted

    async def run(self, function: Callable[..., T], /, *args: object) -> T:
        with self._lock:
            if self._closed:
                raise ConflictError("executor is closed")
            if self._admitted >= self._capacity:
                raise CapacityError(
                    "executor capacity exhausted",
                    context={"capacity": self._capacity},
                )
            self._admitted += 1
        try:
            concurrent_future = self._executor.submit(partial(function, *args))
        except BaseException:
            with self._lock:
                self._admitted -= 1
            raise

        def release_admission(_: object) -> None:
            with self._lock:
                self._admitted -= 1

        concurrent_future.add_done_callback(release_admission)
        return await asyncio.wrap_future(concurrent_future)

    async def close(self, *, grace_seconds: float = 0.0) -> None:
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        with self._lock:
            self._closed = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace_seconds
        while self.admitted and loop.time() < deadline:
            await asyncio.sleep(min(0.01, max(0.0, deadline - loop.time())))
        admitted = self.admitted
        if admitted:
            raise ConflictError(
                "executor still owns admitted work",
                context={"admitted": admitted},
            )
        self._executor.shutdown(wait=True, cancel_futures=True)
