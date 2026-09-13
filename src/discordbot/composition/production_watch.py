"""Watch executable root does not load Discord or the other feature contexts."""

from discordbot.composition.runtime import ProcessRuntime
from discordbot.operations.adapters.hosting import Servers, TelemetryDrain, health_app, server
from discordbot.operations.adapters.probe import Probe
from discordbot.operations.adapters.cli import validate_candidate
from discordbot.platform.clock import SystemClock
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
from discordbot.watch.adapters.server import build_servers
from discordbot.watch.adapters.web_runtime import WatchWebResource


class ValidatedWatch(WatchWebResource):
    async def start(self) -> None:
        await validate_candidate(self.database.config.path)
        await super().start()


def assemble(config, settings):
    clock = SystemClock()
    database = SqliteDatabase(DatabaseConfig(settings.database))
    telemetry = TelemetryEmitter(buffer=TelemetryBuffer(128), clock=clock, service=config.service.value,
                                 environment=config.environment.value, release=config.release)
    feature = ValidatedWatch(database, settings.public_origin, settings.secrets.capability_key,
                               settings.secrets.control_key, clock, telemetry)
    runtime = ProcessRuntime(config=config, resources=(feature,), clock=clock)
    feature.service.telemetry = runtime.telemetry
    probe = Probe(database, runtime, settings.backups / "latest.json")
    def gauges():
        return {**probe.gauges(), "watch_sessions": len(feature.service.sessions),
                "watch_clients": sum(len(actor.peers) for actor in feature.service.sessions.values())}
    listeners = Servers((*build_servers(feature, settings.public_port, settings.control_port),
                         server(health_app(runtime, lambda: feature.service.ready() and probe.ready() and listeners.ready(), gauges), settings.watch_health_port)), runtime.supervisor)
    return runtime, feature, listeners, TelemetryDrain(runtime), probe
