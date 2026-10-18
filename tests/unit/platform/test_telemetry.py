import io
import json
import logging
from datetime import UTC, datetime

import pytest

from discordbot.platform.errors import CapacityError
from discordbot.platform.telemetry import (
    MetricRegistry,
    TelemetryBuffer,
    TelemetryEvent,
    build_json_handler,
)


def _event(name: str) -> TelemetryEvent:
    return TelemetryEvent(
        timestamp=datetime(2026, 9, 4, tzinfo=UTC),
        event=name,
        component="test",
        service="discord-bot",
        environment="test",
        release="unit",
        result="ok",
    )


def test_telemetry_buffer_has_explicit_drop_behavior() -> None:
    buffer = TelemetryBuffer(capacity=2)

    assert buffer.emit(_event("one")) is True
    assert buffer.emit(_event("two")) is True
    assert buffer.emit(_event("three")) is False
    assert buffer.dropped_count == 1
    assert [event.event for event in buffer.drain(limit=1)] == ["one"]
    assert [event.event for event in buffer.drain()] == ["two"]


def test_metrics_reject_unbounded_new_label_series() -> None:
    metrics = MetricRegistry(series_capacity=1)

    assert metrics.increment("task_started_total", labels={"owner": "summary"}) == 1
    assert metrics.increment("task_started_total", labels={"owner": "summary"}) == 2
    with pytest.raises(CapacityError):
        metrics.increment("task_started_total", labels={"owner": "music"})
    assert metrics.dropped_series == 1


def test_json_logging_is_explicit_and_redacts_sensitive_fields() -> None:
    stream = io.StringIO()
    handler = build_json_handler(stream)
    logger = logging.getLogger("discordbot.test.telemetry")
    previous_handlers = list(logger.handlers)
    previous_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            "ignored positional message",
            extra={
                "event": "dependency.failed token=abc123",
                "fields": {
                    "owner": "summary",
                    "authorization": "Bearer abc123",
                    "nested": {"watch_url": "https://example.invalid/private"},
                },
            },
        )
    finally:
        logger.handlers = previous_handlers
        logger.propagate = previous_propagate

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "dependency.failed token=[REDACTED]"
    assert payload["owner"] == "summary"
    assert payload["authorization"] == "[REDACTED]"
    assert payload["nested"]["watch_url"] == "[REDACTED]"
    assert "abc123" not in stream.getvalue()
