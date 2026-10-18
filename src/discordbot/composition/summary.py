"""Explicit Summary assembly. Does not connect, sync commands or touch any DB."""

from discordbot.composition.config import PlatformConfig, ServiceKind
from discordbot.composition.runtime import ProcessRuntime
from discordbot.platform.clock import Clock, SystemClock
from discordbot.platform.errors import ConfigurationError
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.summary.adapters.gemini import GeminiProvider
from discordbot.summary.adapters.runtime import SummaryConfig, SummaryResource, create_summary_bot


def build_summary(config: PlatformConfig, summary_config: SummaryConfig, *, api_key: str,
                  model: str = "gemini-flash-latest", clock: Clock | None = None) -> tuple[ProcessRuntime, SummaryResource]:
    if config.service is not ServiceKind.DISCORD_BOT:
        raise ConfigurationError("Summary requires Discord process")
    clock = clock or SystemClock()
    telemetry = TelemetryEmitter(buffer=TelemetryBuffer(128), clock=clock,
        service="discord-bot", environment=config.environment, release=config.release)
    feature = SummaryResource(create_summary_bot(), summary_config, GeminiProvider(api_key, model), clock, telemetry, owns_bot=True)
    runtime = ProcessRuntime(config=config, resources=(feature,), clock=clock)
    feature.service.telemetry = runtime.telemetry
    return runtime, feature
