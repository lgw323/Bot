from dataclasses import FrozenInstanceError

import pytest

from discordbot.composition.config import (
    Environment,
    PlatformConfig,
    ResourceLimits,
    ServiceKind,
    load_config,
)
from discordbot.platform.errors import ConfigurationError


def test_config_is_typed_immutable_and_uses_pi_bounded_defaults() -> None:
    config = load_config({}, service=ServiceKind.DISCORD_BOT)

    assert config == PlatformConfig(
        service=ServiceKind.DISCORD_BOT,
        environment=Environment.DEVELOPMENT,
        release="dev",
    )
    assert config.limits.executor_workers == 2
    assert config.limits.executor_queue_capacity == 8
    assert config.limits.task_capacity == 64
    with pytest.raises(FrozenInstanceError):
        config.release = "changed"  # type: ignore[misc]


def test_config_parses_explicit_process_environment() -> None:
    config = load_config(
        {
            "APP_ENV": "staging",
            "APP_RELEASE": "2026.09.04+abc123",
            "PLATFORM_TASK_CAPACITY": "24",
            "PLATFORM_TELEMETRY_CAPACITY": "128",
            "PLATFORM_METRIC_SERIES_CAPACITY": "64",
            "PLATFORM_EXECUTOR_WORKERS": "1",
            "PLATFORM_EXECUTOR_QUEUE_CAPACITY": "3",
            "PLATFORM_STARTUP_TIMEOUT_SECONDS": "4.5",
            "PLATFORM_SHUTDOWN_GRACE_SECONDS": "8",
        },
        service=ServiceKind.WATCH_WEB,
    )

    assert config.service is ServiceKind.WATCH_WEB
    assert config.environment is Environment.STAGING
    assert config.limits == ResourceLimits(
        task_capacity=24,
        telemetry_queue_capacity=128,
        metrics_series_capacity=64,
        executor_workers=1,
        executor_queue_capacity=3,
    )
    assert config.runtime.startup_timeout_seconds == 4.5


@pytest.mark.parametrize(
    ("environment", "expected_fragment"),
    [
        ({"APP_ENV": "invalid"}, "APP_ENV"),
        ({"PLATFORM_TASK_CAPACITY": "many"}, "PLATFORM_TASK_CAPACITY"),
        ({"PLATFORM_EXECUTOR_WORKERS": "5"}, "executor_workers"),
        (
            {"APP_ENV": "production", "APP_RELEASE": "unknown"},
            "production APP_RELEASE",
        ),
    ],
)
def test_invalid_config_fails_fast(
    environment: dict[str, str],
    expected_fragment: str,
) -> None:
    with pytest.raises(ConfigurationError, match=expected_fragment):
        load_config(environment, service=ServiceKind.DISCORD_BOT)


def test_direct_config_construction_rejects_wrong_runtime_types() -> None:
    with pytest.raises(ConfigurationError, match="integer"):
        ResourceLimits(task_capacity=1.5)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="ServiceKind"):
        PlatformConfig(  # type: ignore[arg-type]
            service="discord-bot",
            environment=Environment.TEST,
            release="unit",
        )
