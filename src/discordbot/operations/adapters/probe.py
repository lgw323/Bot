"""Bounded operational samples. No feature imports, user labels or raw SQL output."""

import asyncio

from discordbot.platform.errors import AppError, DataIntegrityError
from discordbot.platform.tasks import TaskSpec, CancellationBehavior
from discordbot.storage.ports.contracts import DatabaseRequest, DatabaseState


class Probe:
    def __init__(self, database, runtime, backup_latest=None):
        self.database, self.runtime = database, runtime
        self.database_ready = False
        self.task = None
        self.closed = False
        self.checked = 0.0
        self.backup_latest = backup_latest
        self.backup_age = -1.0

    async def start(self):
        report = await self.database.inspect(DatabaseRequest.within(5))
        if report.state is not DatabaseState.VALID or report.migration_version != 5:
            raise DataIntegrityError("runtime migration compatibility failed")
        self.database_ready = True
        self.checked = self.runtime.clock.monotonic()
        self.schedule()

    def ready(self):
        return self.database_ready and self.runtime.clock.monotonic() - self.checked < 15

    def schedule(self):
        if self.closed:
            return
        async def sample():
            await asyncio.sleep(5)
            start = self.runtime.clock.monotonic()
            try:
                await self.database.read(DatabaseRequest.within(2), lambda conn: conn.execute("SELECT 1").fetchone())
                self.database_ready = True
                self.runtime.metrics.increment("database_probe_total", labels={"result": "ok"})
            except AppError:
                self.database_ready = False
                self.runtime.metrics.increment("database_probe_total", labels={"result": "failed"})
            self.checked = self.runtime.clock.monotonic()
            self.runtime.metrics.increment("database_probe_seconds_total", self.checked - start)
            if self.backup_latest is not None:
                try:
                    modified = await self.runtime.executor.run(lambda: self.backup_latest.stat().st_mtime)
                    self.backup_age = max(0, self.runtime.clock.now().timestamp() - modified)
                except OSError:
                    self.backup_age = -1.0
        self.task = self.runtime.supervisor.start(TaskSpec("database-probe", "operations", "probe", "health", 10,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), sample)
        self.task.add_done_callback(lambda task: self.schedule() if not task.cancelled() and task.exception() is None else None)

    def gauges(self):
        observations = self.database.observations
        return {"process_ready": float(self.ready()), "tasks_active": len(self.runtime.supervisor.snapshot().active),
                "database_read_admitted": self.database.admitted[0], "database_write_admitted": self.database.admitted[1],
                "database_recent_failures": sum(item.result != "ok" for item in observations),
                "database_last_execution_seconds": observations[-1].execution_seconds if observations else 0,
                "backup_age_seconds": self.backup_age,
                "backup_rpo_exceeded": float(self.backup_age < 0 or self.backup_age > 6 * 3600),
                "task_capacity": self.runtime.supervisor.capacity if hasattr(self.runtime.supervisor, "capacity") else self.runtime.config.limits.task_capacity,
                "telemetry_dropped": self.runtime.telemetry_buffer.dropped_count,
                "metric_series_dropped": self.runtime.metrics.dropped_series}

    async def stop(self):
        self.closed = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
