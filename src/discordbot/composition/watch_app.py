"""Watch process composition boundary; no HTTP server is opened here."""

from discordbot.composition.config import PlatformConfig, ServiceKind
from discordbot.composition.runtime import ManagedResource, ProcessRuntime
from discordbot.platform.clock import Clock
from discordbot.platform.errors import ConfigurationError


def build_watch_runtime(
    config: PlatformConfig,
    *,
    resources: tuple[ManagedResource, ...] = (),
    clock: Clock | None = None,
) -> ProcessRuntime:
    if config.service is not ServiceKind.WATCH_WEB:
        raise ConfigurationError("watch composition requires watch-web service config")
    return ProcessRuntime(config=config, resources=resources, clock=clock)
