"""One bounded local packet: real candidate storage/service, synthetic inputs only.

Not an application composition root, Discord transport, capacity or A9 acceptance.
The existing harness owns the new temp root; this adapter owns only its DB/loop.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.platform.errors import ConflictError, DataIntegrityError, DatabaseUnavailableError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

STEPS = ("text_write", "duplicate_write", "profile_read", "busy_write",
         "rollback_write", "cancel_write", "birthday_delivery", "shutdown")
SCENARIO = {"id": "a9-engagement-sqlite-v1", "steps": STEPS,
            "synthetic_guild": 100, "synthetic_user": 10, "text": "abc",
            "clock": "2027-02-28T00:00:00+00:00", "delivery_delay_seconds": .01,
            "busy_seconds": .03, "request_seconds": .5, "barrier_seconds": .5,
            "cleanup_grace_seconds": 1.0}


class SyntheticClock:
    def now(self) -> datetime:
        return datetime(2027, 2, 28, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return 1000.0


class FakeDelivery:
    calls = 0

    async def send(self, guild_id: int, channel_id: int, users: tuple[int, ...]) -> None:
        assert (guild_id, channel_id, users) == (100, 1001, (10,))
        await asyncio.sleep(SCENARIO["delivery_delay_seconds"])
        self.calls += 1


class CandidateAdapter:
    def __init__(self, root: Path, deadline: float) -> None:
        self.root, self.deadline = root, deadline
        self.runner = asyncio.Runner()
        self.db = SqliteDatabase(DatabaseConfig(root / "synthetic.db", queue_capacity=8,
            busy_timeout_seconds=.03, startup_timeout_seconds=.5, shutdown_grace_seconds=.5))
        self.app = EngagementService(SqliteEngagementRepository(self.db), SqliteEngagementEvents(self.db),
            MasterAuthorization(42), EngagementConfig(42, ((100, 1001),), request_seconds=.5),
            SyntheticClock(), "a9-synthetic-epoch")
        self.delivery = FakeDelivery()
        self.observations: list[dict[str, Any]] = []
        self.seen: set[int] = set()
        self.retained: list[Any] = []  # Keep object identities stable across deque eviction.
        self.checks: dict[str, bool] = {}
        self.closed = False
        self.stop_complete = False
        self.app_started = False

    def collect(self, step: str) -> None:
        for item in self.db.observations:
            if id(item) in self.seen:
                continue
            self.seen.add(id(item))
            self.retained.append(item)
            if len(self.observations) >= 128:
                raise RuntimeError("observation bound exceeded")
            self.observations.append({"step": step, "lane": item.lane, "phase": item.phase,
                "result": item.result, "queue_seconds": item.queue_seconds,
                "execution_seconds": item.execution_seconds})

    def start(self) -> None:
        async def setup() -> None:
            async with asyncio.timeout(max(.001, self.deadline - time.monotonic())):
                await DataRecovery(self.db).bootstrap(DatabaseRequest.within(.5))
                await self.db.start()
                await self.app.start()
                self.app_started = True
        try:
            self.runner.run(setup())
        finally:
            self.collect("setup")

    def execute(self, step: str) -> str:
        async def bounded() -> str:
            async with asyncio.timeout(max(.001, self.deadline - time.monotonic())):
                return await self.operation(step)
        try:
            return self.runner.run(bounded())
        except Exception:
            # Preserve the actual failed attempt, without raw SQL/errors/row data.
            return "unexpected_fault"
        finally:
            self.collect(step)

    async def message(self, event: str = "one") -> bool:
        return await self.app.message(100, 10, event, "abc", self.app.clock.now())

    async def operation(self, step: str) -> str:
        if step == "text_write":
            assert await self.message()
            self.checks["write_applied"] = True
        elif step == "duplicate_write":
            assert not await self.message()
            self.checks["duplicate_rejected"] = True
        elif step == "profile_read":
            assert (await self.app.profile(100, 10)).text == 3
            self.checks["read_exact_xp"] = True
        elif step == "busy_write":
            # Hold a real second SQLite writer: failure originates in BEGIN IMMEDIATE.
            with closing(sqlite3.connect(self.db.config.path, isolation_level=None)) as lock:
                lock.execute("BEGIN IMMEDIATE")
                try:
                    await self.message("busy")
                except DatabaseUnavailableError as exc:
                    assert exc.context.get("sqlite_code") == sqlite3.SQLITE_BUSY
                else:
                    raise AssertionError("expected actual SQLite busy")
                finally:
                    lock.rollback()
            assert (await self.app.profile(100, 10)).text == 3
            assert await self.message("busy")  # Failed transaction consumed no receipt.
            assert (await self.app.profile(100, 10)).text == 6
            self.checks["busy_atomic_retry"] = True
            return "expected_db_busy"
        elif step == "rollback_write":
            def mutation(conn: sqlite3.Connection) -> None:
                conn.execute("UPDATE users SET xp=xp+100 WHERE guild_id=100 AND user_id=10")
                raise DataIntegrityError("synthetic rollback trigger")
            try:
                await self.db.write(DatabaseRequest.within(.5), mutation)
            except DataIntegrityError:
                pass  # The subsequent persisted read is the rollback oracle.
            else:
                raise AssertionError("rollback trigger missing")
            assert (await self.app.profile(100, 10)).text == 6
            self.checks["rollback_exact_xp"] = True
            return "expected_rollback"
        elif step == "cancel_write":
            started, release = asyncio.Event(), threading.Event()
            loop = asyncio.get_running_loop()
            def mutation(conn: sqlite3.Connection) -> None:
                conn.execute("UPDATE users SET xp=xp+100 WHERE guild_id=100 AND user_id=10")
                loop.call_soon_threadsafe(started.set)
                if not release.wait(.5):
                    raise TimeoutError("synthetic barrier expired")
            task = asyncio.create_task(self.db.write(DatabaseRequest.within(.5), mutation))
            try:
                await asyncio.wait_for(started.wait(), .5)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    self.checks["cancellation_propagated"] = True
                else:
                    raise AssertionError("cancellation missing")
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await self.db.write(DatabaseRequest.within(.5), lambda conn: None)
            assert (await self.app.profile(100, 10)).text == 6
            self.checks["cancel_rollback_exact_xp"] = True
            return "expected_cancellation"
        elif step == "birthday_delivery":
            await self.app.register_birthday(42, 100, 10, 2, 28)
            assert await self.app.notify_guild(100, 1001, self.delivery)
            assert not await self.app.notify_guild(100, 1001, self.delivery)
            assert self.delivery.calls == 1
            self.checks["durable_fake_delivery_dedupe"] = True
        elif step == "shutdown":
            await self.app.stop()
            await self.db.stop()
            self.stop_complete = True
            try:
                await self.db.read(DatabaseRequest.within(.5), lambda conn: None)
            except ConflictError:
                self.checks["closed_admission"] = True
            else:
                raise AssertionError("shutdown accepted work")
            assert self.db.admitted == (0, 0)
        else:
            raise ValueError("unknown fixed step")
        return "ok"

    def close(self, *, flush: bool = True) -> dict[str, Any]:
        async def shutdown() -> None:
            if not self.stop_complete:
                try:
                    if self.app_started and flush:
                        await self.app.stop()
                finally:
                    await self.db.stop()
                    self.stop_complete = True
        if not self.closed:
            try:
                self.runner.run(asyncio.wait_for(shutdown(), 1.0))
            finally:
                self.collect("cleanup")
                self.runner.close()
                self.closed = True
        return self.evidence()

    def evidence(self) -> dict[str, Any]:
        return {"checks": self.checks, "database_observations": self.observations,
                "fake_delivery_calls": self.delivery.calls,
                "admitted_remaining": sum(self.db.admitted), "loop_closed": self.closed,
                "database_stopped": self.stop_complete}

    def remove_files(self) -> None:
        # Called only after harness verifies root ownership and workers are drained.
        if not self.closed or not self.stop_complete or self.db.admitted != (0, 0):
            raise OSError("refuse cleanup before worker drain")
        for name in ("synthetic.db", "synthetic.db-wal", "synthetic.db-shm"):
            path = self.root / name
            if path.is_symlink() or path.is_junction():
                raise OSError("refuse replaced synthetic file")
            path.unlink(missing_ok=True)
