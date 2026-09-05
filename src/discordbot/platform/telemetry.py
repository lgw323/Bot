"""Bounded structured telemetry without import-time logging mutation."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import IO, Mapping

from discordbot.platform.clock import Clock
from discordbot.platform.context import current_correlation
from discordbot.platform.errors import CapacityError

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "content",
    "cookie",
    "credential",
    "encryption_key",
    "api_key",
    "password",
    "secret",
    "token",
    "url",
)
_INLINE_SECRET = re.compile(
    r"(?i)\b(token|password|secret|authorization)\s*[:=]\s*([^\s,;]+)"
)


def _redact_value(key: str, value: object) -> object:
    normalized = key.casefold()
    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(inner_key): _redact_value(str(inner_key), inner_value) for inner_key, inner_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(key, item) for item in value]
    if isinstance(value, str):
        return _INLINE_SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return value


def sanitize_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Copy and redact structured fields before they enter a telemetry sink."""

    return {str(key): _redact_value(str(key), value) for key, value in fields.items()}


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    timestamp: datetime
    event: str
    component: str
    service: str
    environment: str
    release: str
    result: str
    correlation_id: str | None = None
    fields: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "component": self.component,
            "service": self.service,
            "environment": self.environment,
            "release": self.release,
            "result": self.result,
            "correlation_id": self.correlation_id,
        }
        payload.update(sanitize_fields(self.fields))
        return payload


class TelemetryBuffer:
    """A non-blocking bounded buffer; overload is explicit through dropped_count."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._events: deque[TelemetryEvent] = deque()
        self._dropped_count = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    def emit(self, event: TelemetryEvent) -> bool:
        with self._lock:
            if len(self._events) >= self._capacity:
                self._dropped_count += 1
                return False
            self._events.append(event)
            return True

    def drain(self, limit: int | None = None) -> tuple[TelemetryEvent, ...]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        with self._lock:
            count = len(self._events) if limit is None else min(limit, len(self._events))
            return tuple(self._events.popleft() for _ in range(count))

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


MetricKey = tuple[str, tuple[tuple[str, str], ...]]


class MetricRegistry:
    """In-memory counters with a hard cap on label cardinality."""

    def __init__(self, series_capacity: int) -> None:
        if series_capacity < 1:
            raise ValueError("series_capacity must be positive")
        self._series_capacity = series_capacity
        self._counters: dict[MetricKey, float] = {}
        self._dropped_series = 0
        self._lock = threading.Lock()

    @property
    def dropped_series(self) -> int:
        with self._lock:
            return self._dropped_series

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        if not name or any(character.isspace() for character in name):
            raise ValueError("metric name must be non-blank and contain no whitespace")
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            if key not in self._counters and len(self._counters) >= self._series_capacity:
                self._dropped_series += 1
                raise CapacityError(
                    "metric series capacity exhausted",
                    context={"capacity": self._series_capacity, "metric": name},
                )
            self._counters[key] = self._counters.get(key, 0.0) + amount
            return self._counters[key]

    def snapshot(self) -> dict[MetricKey, float]:
        with self._lock:
            return dict(self._counters)


class JsonEventFormatter(logging.Formatter):
    """JSON formatter that only adds explicitly supplied structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_correlation()
        supplied = getattr(record, "fields", {})
        if not isinstance(supplied, Mapping):
            supplied = {"invalid_fields": type(supplied).__name__}
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": str(getattr(record, "event", record.msg)),
            "correlation_id": context.correlation_id if context else None,
        }
        payload.update(sanitize_fields(supplied))
        payload["event"] = _redact_value("event_name", payload["event"])
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def build_json_handler(stream: IO[str] | None = None) -> logging.StreamHandler[IO[str]]:
    """Build, but do not register, a structured logging handler."""

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonEventFormatter())
    return handler


class TelemetryEmitter:
    """Creates consistently attributed events for one process."""

    def __init__(
        self,
        *,
        buffer: TelemetryBuffer,
        clock: Clock,
        service: str,
        environment: str,
        release: str,
    ) -> None:
        self._buffer = buffer
        self._clock = clock
        self._service = service
        self._environment = environment
        self._release = release

    def emit(
        self,
        event: str,
        *,
        component: str,
        result: str,
        fields: Mapping[str, object] | None = None,
    ) -> bool:
        correlation = current_correlation()
        return self._buffer.emit(
            TelemetryEvent(
                timestamp=self._clock.now(),
                event=event,
                component=component,
                service=self._service,
                environment=self._environment,
                release=self._release,
                result=result,
                correlation_id=correlation.correlation_id if correlation else None,
                fields=sanitize_fields(fields or {}),
            )
        )
