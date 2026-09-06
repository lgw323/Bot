"""Immutable inputs and safe aggregate results for data operations."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from discordbot.platform.errors import ConfigurationError, DeadlineExceededError, ValidationError


class DatabaseDeadlineError(DeadlineExceededError):
    """A timed-out mutation may have crossed its commit point; never blind-retry."""

    retryable = False


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    path: Path = field(repr=False)
    queue_capacity: int = 8
    busy_timeout_seconds: float = 0.1
    startup_timeout_seconds: float = 10.0
    shutdown_grace_seconds: float = 2.0
    page_limit: int = 100
    max_backup_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ConfigurationError("database path must be absolute")
        for value, low, high in (
            (self.queue_capacity, 0, 64), (self.page_limit, 1, 1000),
            (self.max_backup_bytes, 1024, 256 * 1024 * 1024),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ConfigurationError("database capacity is invalid")
        for value, ceiling in (
            (self.busy_timeout_seconds, 1), (self.startup_timeout_seconds, 60),
            (self.shutdown_grace_seconds, 10),
        ):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= ceiling:
                raise ConfigurationError("database timeout is invalid")


@dataclass(frozen=True, slots=True)
class DatabaseRequest:
    deadline: float
    correlation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if (type(self.deadline) not in (int, float) or not math.isfinite(self.deadline)
                or self.deadline - time.monotonic() > 86400
                or not isinstance(self.correlation_id, str) or not self.correlation_id.strip()):
            raise ValidationError("database request metadata is invalid")

    @classmethod
    def within(cls, seconds: float, correlation_id: str = "data-operation") -> DatabaseRequest:
        if not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValidationError("database request budget is invalid")
        return cls(time.monotonic() + seconds, correlation_id)


class DatabaseState(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    EMPTY = "zero_byte"
    CORRUPT = "corrupt"
    WRONG_SCHEMA = "wrong_schema"
    INVALID_DATA = "invalid_data"
    INVALID_LEDGER = "invalid_ledger"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    state: DatabaseState
    schema_variant: str = "unknown"
    migration_version: int = 0
    counts: tuple[tuple[str, int], ...] = ()
    # An aggregate reconciliation digest is kept internal, never a row fixture.
    data_checksum: str = field(default="", repr=False)
    warnings: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class DatabaseObservation:
    lane: str
    phase: str
    result: str
    correlation_id: str = field(repr=False)
    queue_seconds: float = 0.0
    execution_seconds: float = 0.0


def require_page(limit: int, offset: int, maximum: int) -> None:
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= maximum or offset < 0:
        raise ValidationError("invalid repository page")
