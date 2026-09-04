from datetime import UTC, datetime, timedelta

import pytest

from discordbot.platform.errors import ValidationError
from discordbot.platform.health import HealthRegistry, HealthStatus


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 9, 4, tzinfo=UTC)
        self.elapsed = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.elapsed

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
        self.current += timedelta(seconds=seconds)


def test_health_distinguishes_liveness_readiness_and_dependencies() -> None:
    clock = FakeClock()
    health = HealthRegistry(
        capabilities=("platform", "discord_gateway", "sqlite"),
        required=("platform", "discord_gateway", "sqlite"),
        clock=clock,
    )

    assert health.live_payload() == {"live": True}
    assert health.ready_payload() == {"ready": False, "accepting_work": False}

    health.update("platform", HealthStatus.OK)
    health.update("discord_gateway", HealthStatus.OK)
    health.update("sqlite", HealthStatus.DEGRADED, detail="read-only")
    health.start_accepting()
    assert health.ready_payload()["ready"] is False

    clock.advance(1)
    health.update("sqlite", HealthStatus.OK)
    assert health.ready_payload() == {"ready": True, "accepting_work": True}
    assert health.dependency_payload()["sqlite"]["checked_at"] == clock.now().isoformat()

    health.stop_accepting()
    assert health.live_payload() == {"live": True}
    assert health.ready_payload()["ready"] is False
    health.stop_liveness()
    assert health.live_payload() == {"live": False}


def test_health_rejects_undeclared_unbounded_capabilities() -> None:
    health = HealthRegistry(
        capabilities=("platform",),
        required=("platform",),
        clock=FakeClock(),
    )

    with pytest.raises(ValidationError, match="unknown capability"):
        health.update("dynamic-user-1", HealthStatus.OK)
