"""Watch process composition boundary; no HTTP server is opened here."""

from discordbot.composition.config import PlatformConfig, ServiceKind
from discordbot.composition.runtime import ManagedResource, ProcessRuntime
from discordbot.platform.clock import Clock
from discordbot.platform.errors import ConfigurationError
from discordbot.watch.adapters.web_runtime import WatchWebResource


def build_watch_runtime(
    config: PlatformConfig,
    *,
    resources: tuple[ManagedResource, ...] = (),
    clock: Clock | None = None,
    watch: WatchWebResource | None = None,
) -> ProcessRuntime:
    if config.service is not ServiceKind.WATCH_WEB:
        raise ConfigurationError("watch composition requires watch-web service config")
    return ProcessRuntime(config=config, resources=resources + ((watch,) if watch else ()), clock=clock)
