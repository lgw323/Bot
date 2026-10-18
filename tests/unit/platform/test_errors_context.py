from dataclasses import FrozenInstanceError

import pytest

from discordbot.platform.context import (
    CorrelationContext,
    correlation_scope,
    current_correlation,
)
from discordbot.platform.errors import CapacityError, ErrorCategory, ErrorCode


def test_typed_error_separates_safe_message_from_internal_context() -> None:
    error = CapacityError(
        "queue music_requests exceeded 4",
        context={"owner": "music", "capacity": 4},
    )

    assert error.code is ErrorCode.CAPACITY
    assert error.category is ErrorCategory.CAPACITY
    assert error.retryable is True
    assert "music_requests" not in error.safe_message
    assert error.to_log_fields()["context"] == {"owner": "music", "capacity": 4}
    with pytest.raises(TypeError):
        error.context["capacity"] = 8  # type: ignore[index]


def test_correlation_scope_is_nested_and_restored() -> None:
    outer = CorrelationContext("outer")
    inner = CorrelationContext("inner", causation_id="outer")

    assert current_correlation() is None
    with correlation_scope(outer):
        assert current_correlation() == outer
        with correlation_scope(inner):
            assert current_correlation() == inner
        assert current_correlation() == outer
    assert current_correlation() is None


def test_correlation_context_is_immutable_and_non_blank() -> None:
    context = CorrelationContext("request-1")
    with pytest.raises(FrozenInstanceError):
        context.correlation_id = "request-2"  # type: ignore[misc]
    with pytest.raises(ValueError, match="blank"):
        CorrelationContext("  ")
