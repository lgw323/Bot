"""Injectable time and identifier sources."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class Uuid4Generator:
    def new_id(self) -> str:
        return str(uuid.uuid4())
