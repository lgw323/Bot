"""Correlation context propagated across supervised asynchronous work."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be blank")


_CURRENT_CORRELATION: ContextVar[CorrelationContext | None] = ContextVar(
    "discordbot_correlation",
    default=None,
)


def current_correlation() -> CorrelationContext | None:
    return _CURRENT_CORRELATION.get()


@contextmanager
def correlation_scope(context: CorrelationContext) -> Iterator[None]:
    token = _CURRENT_CORRELATION.set(context)
    try:
        yield
    finally:
        _CURRENT_CORRELATION.reset(token)
