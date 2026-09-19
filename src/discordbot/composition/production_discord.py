"""Full Discord composition, explicitly invoked only after file/config validation."""

from pathlib import Path
from discordbot.composition.live_validation import full_sweep_active

from discordbot.composition.runtime import ProcessRuntime
from discordbot.engagement.adapters.discord_runtime import EngagementConfig, EngagementResource, create_engagement_bot
from discordbot.music.adapters.runtime import MusicResource
from discordbot.music.adapters.sqlite_repository import SqliteMusicRepository
from discordbot.operations.adapters.hosting import DeferredMusic, Gateway, Servers, TelemetryDrain, health_app, server
from discordbot.operations.adapters.probe import Probe
from discordbot.platform.clock import SystemClock, Uuid4Generator
from discordbot.platform.tasks import TaskSupervisor
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
from discordbot.operations.adapters.cli import validate_candidate
from discordbot.summary.adapters.gemini import GeminiProvider
from discordbot.summary.adapters.runtime import Scope, SummaryConfig, SummaryResource
from discordbot.watch.adapters.discord_runtime import DiscordWatchResource


class DiscordFeatures:
    name = "discord-features"
    required = True

    def __init__(self, config, settings, database, clock):
        self.config, self.settings, self.database, self.clock = config, settings, database, clock
        self.bot = create_engagement_bot()
        self.runtime = None
        self.started = []
        self.music = self.deferred = self.summary = None

    async def start(self):
        s, r = self.settings, self.runtime
        await validate_candidate(s.database)
        engagement = EngagementResource(self.bot, self.database, EngagementConfig(s.master, s.main_channels), self.clock,
            TaskSupervisor(capacity=2, history_capacity=8, clock=self.clock), Uuid4Generator().new_id())
        self.summary = SummaryResource(self.bot, SummaryConfig(tuple(Scope(g, c) for g, c in s.main_channels)),
            GeminiProvider(s.secrets.gemini_key, s.gemini_model), self.clock, r.telemetry)
        watch = DiscordWatchResource(self.bot, s.public_origin, f"http://127.0.0.1:{s.control_port}",
            s.secrets.control_key, s.admin_channel, s.master, self.clock, r.telemetry)
        self.music = MusicResource(self.bot, SqliteMusicRepository(self.database), self.clock, r.executor,
            cache_path=s.cache / "music", snapshot_path=s.state / "music_state.json",
            channels=dict(s.music_channels), master=s.master,
            fail_fast=lambda: Path('/run/discordbot-live-smoke').is_file(),
            full_sweep=lambda: full_sweep_active(self.config.release))
        self.deferred = DeferredMusic(self.music, self.bot, r.supervisor)
        try:
            for resource in (engagement, self.summary, watch, Gateway(self.bot, s.secrets.discord_token), self.deferred):
                await resource.start()
                self.started.append(resource)
        except BaseException:
            await self.stop()
            raise

    def ready(self):
        return bool(self.bot.is_ready() and self.deferred and self.deferred.started
                    and not self.deferred.failed and not self.music.failed_restore
                    and not any(actor.smoke_failed for actor in self.music.actors.values()))

    def gauges(self):
        return {"music_actors": len(self.music.actors) if self.music else 0,
                "music_cache_bytes": self.music.cache.bytes if self.music else 0,
                "music_processes": len(self.music.processes.children) if self.music else 0,
                "summary_waiting": self.summary.service.waiting if self.summary else 0}

    async def stop(self):
        errors = []
        for resource in reversed(self.started):
            try:
                await resource.stop()
            except Exception as error:
                errors.append(type(error).__name__)
        self.started.clear()
        if errors:
            from discordbot.platform.errors import ShutdownError
            raise ShutdownError("Discord feature shutdown failed")


def assemble(config, settings):
    clock = SystemClock()
    database = SqliteDatabase(DatabaseConfig(settings.database))
    features = DiscordFeatures(config, settings, database, clock)
    runtime = ProcessRuntime(config=config, resources=(database, features), clock=clock)
    features.runtime = runtime
    probe = Probe(database, runtime, settings.backups / "latest.json")
    def ready(): return features.ready() and probe.ready() and listeners.ready()
    def gauges(): return {**features.gauges(), **probe.gauges()}
    listeners = Servers((server(health_app(runtime, ready, gauges), settings.discord_health_port),), runtime.supervisor)
    return runtime, features, listeners, TelemetryDrain(runtime), probe
