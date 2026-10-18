"""Discord process composition boundary; no Discord connection is opened here."""

from discordbot.composition.config import PlatformConfig, ServiceKind
from discordbot.composition.runtime import ManagedResource, ProcessRuntime
from discordbot.platform.clock import Clock
from discordbot.platform.errors import ConfigurationError
from discordbot.watch.adapters.discord_runtime import DiscordWatchResource
from discordbot.music.adapters.runtime import MusicResource


def build_discord_runtime(
    config: PlatformConfig,
    *,
    resources: tuple[ManagedResource, ...] = (),
    clock: Clock | None = None,
    watch: DiscordWatchResource | None = None,
    music: MusicResource | None = None,
) -> ProcessRuntime:
    if config.service is not ServiceKind.DISCORD_BOT:
        raise ConfigurationError("discord composition requires discord-bot service config")
    return ProcessRuntime(config=config, resources=resources + ((watch,) if watch else ()) + ((music,) if music else ()), clock=clock)
