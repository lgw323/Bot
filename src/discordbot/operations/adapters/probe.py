"""Bounded operational samples. No feature imports, user labels or raw SQL output."""

import asyncio
import math

from discordbot.platform.errors import AppError, DataIntegrityError
from discordbot.platform.tasks import TaskSpec, CancellationBehavior
from discordbot.storage.ports.contracts import DatabaseRequest, DatabaseState
from discordbot.storage.adapters.probe_diagnostics import safe_probe_fields
from discordbot.operations.adapters.probe_policy import ProbePolicy


class Probe:
    def __init__(self, database, runtime, backup_latest=None):
        self.database, self.runtime = database, runtime
        self.database_ready = False
        self.task = None
        self.closed = False
        self.checked = 0.0
        self.backup_latest = backup_latest
        self._backup_modified: float | None = None
        self.policy = ProbePolicy()

    async def start(self):
        report = await self.database.inspect(DatabaseRequest.within(5))
        if report.state is not DatabaseState.VALID or report.migration_version != 5:
            raise DataIntegrityError("runtime migration compatibility failed")
        self.database_ready = True
        self.checked = self.runtime.clock.monotonic()
        self.schedule()

    def ready(self):
        now = self.runtime.clock.monotonic()
        return (self.database_ready and now - self.checked < 15
                and not self.policy.deadline_pending
                and (self.policy.pending_since is None or now - self.policy.pending_since < 15))

    def schedule(self):
        if self.closed or self.policy.hard:
            return
        async def sample():
            await asyncio.sleep(5)
            start = self.runtime.clock.monotonic()
            # A timeout ends the awaiter, not necessarily its SQLite worker.
            # Never enqueue more probes behind that worker, nor erase a late
            # close/SQLite failure. Only fixed read health checks may recover.
            if self.policy.deadline_pending:
                if self.database.admitted[0]:
                    await self.sample_backup()
                    return
                if not self.database.probe_recovery_safe:
                    self.policy.hard = True
                    self.database_ready = False
                    self.runtime.telemetry.emit('database.probe_failed', component='operations', result='failed',
                        fields={'operation': 'select1_probe', 'error_code': 'database_unavailable',
                                'probe_disposition': 'hard', 'probe_recovery_safe': False})
                    return
            try:
                await self.database.probe(DatabaseRequest.within(2))
                self.runtime.metrics.increment("database_probe_total", labels={"result": "ok"})
                disposition = self.policy.success(self.runtime.clock.monotonic())
                if disposition in {'healthy', 'recovering', 'recovered'}:
                    self.database_ready = True
                    self.checked = self.runtime.clock.monotonic()
                elif disposition in {'hard', 'recovery_expired', 'deadline_recovering'}:
                    self.database_ready = False
                if disposition == 'recovery_expired':
                    self.runtime.telemetry.emit('database.probe_failed', component='operations', result='failed',
                        fields={'operation': 'select1_probe', 'error_code': 'database_unavailable',
                                'probe_disposition': 'recovery_expired'})
                elif disposition == 'recovered':
                    self.runtime.telemetry.emit('database.probe_recovered', component='operations', result='success',
                        fields={'operation': 'select1_probe', 'healthy_probes': 2})
            except AppError as exc:
                self.runtime.metrics.increment("database_probe_total", labels={"result": "failed"})
                fields = safe_probe_fields(exc.context)
                disposition = self.policy.failure({'error_code': exc.code.value, **fields}, self.runtime.clock.monotonic(), self.ready())
                if disposition in {'hard', 'deadline_pending'}:
                    self.database_ready = False
                self.runtime.telemetry.emit('database.probe_contention' if disposition == 'bounded_busy' else 'database.probe_failed',
                    component='operations', result='failed',
                    fields={'error_code': exc.code.value, 'probe_disposition': disposition, **fields})
            self.runtime.metrics.increment("database_probe_seconds_total", self.runtime.clock.monotonic() - start)
            await self.sample_backup()
        self.task = self.runtime.supervisor.start(TaskSpec("database-probe", "operations", "probe", "health", 10,
            cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN, emit_routine_events=False), sample)
        self.task.add_done_callback(lambda task: self.schedule() if not task.cancelled() and task.exception() is None else None)

    async def sample_backup(self) -> None:
        if self.backup_latest is not None:
            try:
                modified = await self.runtime.executor.run(lambda: self.backup_latest.stat().st_mtime)
                self._backup_modified = (modified if type(modified) in (int, float)
                                         and math.isfinite(modified) else None)
            except OSError:
                self._backup_modified = None

    @property
    def backup_age(self) -> float:
        # A stopped sampler cannot observe replacement/removal of latest.json.
        # Reuse the existing unknown sentinel; never present its old safe sample.
        if (self.closed or self.policy.hard or self._backup_modified is None
                or self.task is None or self.task.done()):
            return -1.0
        return max(0.0, self.runtime.clock.now().timestamp() - self._backup_modified)

    def gauges(self):
        observations = self.database.observations
        backup_age = self.backup_age
        return {"process_ready": float(self.ready()), "tasks_active": len(self.runtime.supervisor.snapshot().active),
                "database_read_admitted": self.database.admitted[0], "database_write_admitted": self.database.admitted[1],
                "database_recent_failures": sum(item.result != "ok" for item in observations),
                "database_probe_recovery_pending": float(self.policy.pending_since is not None),
                "database_last_execution_seconds": observations[-1].execution_seconds if observations else 0,
                "backup_age_seconds": backup_age,
                "backup_rpo_exceeded": float(backup_age < 0 or backup_age > 6 * 3600),
                "task_capacity": self.runtime.supervisor.capacity if hasattr(self.runtime.supervisor, "capacity") else self.runtime.config.limits.task_capacity,
                "telemetry_dropped": self.runtime.telemetry_buffer.dropped_count,
                "metric_series_dropped": self.runtime.metrics.dropped_series}

    async def stop(self):
        self.closed = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
