"""Explicit local composition; caller owns any later Discord login/cutover."""

from discordbot.composition.config import PlatformConfig, ServiceKind
from discordbot.composition.runtime import ProcessRuntime
from discordbot.engagement.adapters.discord_runtime import EngagementConfig, EngagementResource, create_engagement_bot
from discordbot.platform.clock import Clock, SystemClock, Uuid4Generator
from discordbot.platform.errors import ConfigurationError
from discordbot.platform.tasks import TaskSupervisor
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase


def build_engagement(config: PlatformConfig, database_config: DatabaseConfig,
                     engagement_config: EngagementConfig, *, clock: Clock | None = None) -> tuple[ProcessRuntime, EngagementResource]:
    if config.service is not ServiceKind.DISCORD_BOT:
        raise ConfigurationError("engagement requires Discord process")
    clock = clock or SystemClock()
    database = SqliteDatabase(database_config)
    # Dedicated scheduler ownership avoids a circular ProcessRuntime construction.
    supervisor = TaskSupervisor(capacity=2, history_capacity=8, clock=clock)
    feature = EngagementResource(create_engagement_bot(), database, engagement_config, clock,
                                 supervisor, Uuid4Generator().new_id())
    runtime = ProcessRuntime(config=config, resources=(database, feature), clock=clock)
    return runtime, feature
