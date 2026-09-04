"""Liveness, readiness, and named capability health state."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from discordbot.platform.clock import Clock
from discordbot.platform.errors import ValidationError


class HealthStatus(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class CapabilityHealth:
    name: str
    status: HealthStatus
    checked_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    live: bool
    ready: bool
    accepting_work: bool
    capabilities: Mapping[str, CapabilityHealth]


class HealthRegistry:
    """A bounded registry: capabilities must be declared at composition time."""

    def __init__(
        self,
        *,
        capabilities: tuple[str, ...],
        required: tuple[str, ...],
        clock: Clock,
    ) -> None:
        if not capabilities or any(not name.strip() for name in capabilities):
            raise ValueError("at least one non-blank capability is required")
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("capability names must be unique")
        if not set(required).issubset(capabilities):
            raise ValueError("required capabilities must be declared")
        self._clock = clock
        self._required = frozenset(required)
        self._capabilities = {
            name: CapabilityHealth(name, HealthStatus.UNKNOWN, clock.now())
            for name in capabilities
        }
        self._live = True
        self._accepting_work = False
        self._lock = threading.Lock()

    def update(
        self,
        name: str,
        status: HealthStatus,
        *,
        detail: str | None = None,
    ) -> CapabilityHealth:
        with self._lock:
            if name not in self._capabilities:
                raise ValidationError(
                    f"unknown capability: {name}",
                    context={"capability": name},
                )
            current = CapabilityHealth(name, status, self._clock.now(), detail)
            self._capabilities[name] = current
            return current

    def start_accepting(self) -> None:
        with self._lock:
            self._accepting_work = True

    def stop_accepting(self) -> None:
        with self._lock:
            self._accepting_work = False

    def stop_liveness(self) -> None:
        with self._lock:
            self._live = False
            self._accepting_work = False

    def snapshot(self) -> HealthSnapshot:
        with self._lock:
            capabilities = dict(self._capabilities)
            ready = (
                self._live
                and self._accepting_work
                and all(capabilities[name].status is HealthStatus.OK for name in self._required)
            )
            return HealthSnapshot(
                live=self._live,
                ready=ready,
                accepting_work=self._accepting_work,
                capabilities=MappingProxyType(capabilities),
            )

    def live_payload(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {"live": snapshot.live}

    def ready_payload(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {
            "ready": snapshot.ready,
            "accepting_work": snapshot.accepting_work,
        }

    def dependency_payload(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {
            name: {
                "status": health.status.value,
                "checked_at": health.checked_at.isoformat(),
                "detail": health.detail,
            }
            for name, health in snapshot.capabilities.items()
        }
