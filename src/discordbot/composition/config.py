"""Typed immutable platform configuration with explicit environment loading."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from discordbot.platform.errors import ConfigurationError


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class ServiceKind(StrEnum):
    DISCORD_BOT = "discord-bot"
    WATCH_WEB = "watch-web"


def _validate_range(name: str, value: int | float, minimum: float, maximum: float) -> None:
    if isinstance(value, bool) or not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}",
            context={"field": name, "minimum": minimum, "maximum": maximum},
        )


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Hard platform ceilings sized conservatively for Raspberry Pi 5."""

    task_capacity: int = 64
    telemetry_queue_capacity: int = 512
    metrics_series_capacity: int = 256
    executor_workers: int = 2
    executor_queue_capacity: int = 8

    def __post_init__(self) -> None:
        _validate_range("task_capacity", self.task_capacity, 1, 256)
        _validate_range("telemetry_queue_capacity", self.telemetry_queue_capacity, 1, 8192)
        _validate_range("metrics_series_capacity", self.metrics_series_capacity, 1, 4096)
        _validate_range("executor_workers", self.executor_workers, 1, 4)
        _validate_range("executor_queue_capacity", self.executor_queue_capacity, 0, 64)


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    startup_timeout_seconds: float = 10.0
    shutdown_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_range("startup_timeout_seconds", self.startup_timeout_seconds, 0.1, 60.0)
        _validate_range("shutdown_grace_seconds", self.shutdown_grace_seconds, 0.1, 60.0)


@dataclass(frozen=True, slots=True)
class PlatformConfig:
    service: ServiceKind
    environment: Environment
    release: str
    limits: ResourceLimits = ResourceLimits()
    runtime: RuntimePolicy = RuntimePolicy()

    def __post_init__(self) -> None:
        release = self.release.strip()
        if not release:
            raise ConfigurationError("APP_RELEASE must not be blank")
        if self.environment is Environment.PRODUCTION and release.casefold() in {"dev", "unknown"}:
            raise ConfigurationError("production APP_RELEASE must identify an immutable release")


def _read_int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw = environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer", context={"field": key}) from exc


def _read_float(environ: Mapping[str, str], key: str, default: float) -> float:
    raw = environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number", context={"field": key}) from exc


def load_config(environ: Mapping[str, str], *, service: ServiceKind) -> PlatformConfig:
    """Parse a supplied environment mapping; importing the module reads nothing."""

    try:
        environment = Environment(environ.get("APP_ENV", Environment.DEVELOPMENT.value))
    except ValueError as exc:
        raise ConfigurationError(
            "APP_ENV has an unsupported value",
            context={"field": "APP_ENV"},
        ) from exc

    defaults = ResourceLimits()
    policy_defaults = RuntimePolicy()
    return PlatformConfig(
        service=service,
        environment=environment,
        release=environ.get("APP_RELEASE", "dev"),
        limits=ResourceLimits(
            task_capacity=_read_int(environ, "PLATFORM_TASK_CAPACITY", defaults.task_capacity),
            telemetry_queue_capacity=_read_int(
                environ,
                "PLATFORM_TELEMETRY_CAPACITY",
                defaults.telemetry_queue_capacity,
            ),
            metrics_series_capacity=_read_int(
                environ,
                "PLATFORM_METRIC_SERIES_CAPACITY",
                defaults.metrics_series_capacity,
            ),
            executor_workers=_read_int(
                environ,
                "PLATFORM_EXECUTOR_WORKERS",
                defaults.executor_workers,
            ),
            executor_queue_capacity=_read_int(
                environ,
                "PLATFORM_EXECUTOR_QUEUE_CAPACITY",
                defaults.executor_queue_capacity,
            ),
        ),
        runtime=RuntimePolicy(
            startup_timeout_seconds=_read_float(
                environ,
                "PLATFORM_STARTUP_TIMEOUT_SECONDS",
                policy_defaults.startup_timeout_seconds,
            ),
            shutdown_grace_seconds=_read_float(
                environ,
                "PLATFORM_SHUTDOWN_GRACE_SECONDS",
                policy_defaults.shutdown_grace_seconds,
            ),
        ),
    )
