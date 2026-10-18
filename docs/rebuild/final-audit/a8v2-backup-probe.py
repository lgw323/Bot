"""Independent commit ordering and retained-worker cancellation; synthetic only."""
import asyncio
from contextlib import asynccontextmanager
import threading

import pytest

from discordbot.operations.adapters import recovery
from discordbot.operations.adapters.filesystem import read_json
from tests.integration.operations.test_recovery import backup


@pytest.mark.asyncio
async def test_full_validation_finishes_before_audit_pointer_and_prune(backup, monkeypatch, tmp_path):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    events = []
    active = 0
    original_validate = backup._validated_candidate
    original_audit = backup.audit.write
    original_atomic = recovery.atomic_json
    original_prune = backup._prune

    @asynccontextmanager
    async def validate(identity, directory):
        nonlocal active
        assert active == 0
        active += 1
        events.append(("validate", identity))
        try:
            async with original_validate(identity, directory) as isolated:
                assert isolated.is_file()
                assert read_json(backup.root / "latest.json")["identity"] == prior[-1]
                assert all((backup.root / (p + ".enc")).is_file() for p in prior)
                yield isolated
            assert not isolated.exists()
            events.append(("clean", identity))
        finally:
            active -= 1

    def audit(operation, release, result, reason):
        if result == "ok":
            assert active == 0
            assert len([e for e in events if e[0] == "clean"]) == 9
            events.append(("audit", result))
        return original_audit(operation, release, result, reason)

    def atomic(path, value):
        if path == backup.root / "latest.json":
            assert events[-1] == ("audit", "ok")
            events.append(("latest", value["identity"]))
        return original_atomic(path, value)

    def prune(identities):
        assert events[-1][0] == "latest"
        assert identities == (prior[0],)
        events.append(("prune", identities))
        return original_prune(identities)

    with monkeypatch.context() as scoped:
        scoped.setattr(backup, "_validated_candidate", validate)
        scoped.setattr(backup.audit, "write", audit)
        scoped.setattr(recovery, "atomic_json", atomic)
        scoped.setattr(backup, "_prune", prune)
        newest = await backup.create("synthetic-release")
    assert [i for kind, i in events if kind == "validate"] == sorted(prior + [newest], reverse=True)
    assert events[-3:] == [("audit", "ok"), ("latest", newest), ("prune", (prior[0],))]
    for index, identity in enumerate(prior[1:] + [newest]):
        assert await backup.restore(tmp_path / f"checked-{index}.db", "synthetic-release", candidates=(identity,)) == identity


@pytest.mark.asyncio
async def test_real_restore_worker_cancellation_preserves_previous_publication(backup, monkeypatch):
    prior = [await backup.create("synthetic-release") for _ in range(8)]
    before = {p.name: p.read_bytes() for p in backup.root.iterdir()}
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    original = recovery.DataRecovery._restore

    def restoring(self, candidate, destination, control):
        if candidate.path.stem != prior[0]:
            return original(self, candidate, destination, control)
        # Retain a real completed private DB while the actual owned worker runs.
        result = original(self, candidate, destination, control)
        entered.set()
        try:
            if not release.wait(5):
                raise AssertionError("synthetic audit worker was not released")
            control.checkpoint()
            return result
        finally:
            exited.set()

    monkeypatch.setattr(recovery.DataRecovery, "_restore", restoring)
    task = asyncio.create_task(backup.create("synthetic-release"))
    try:
        async with asyncio.timeout(10):
            while not entered.is_set():
                if task.done():
                    await task
                    raise AssertionError("restore boundary was not reached")
                await asyncio.sleep(0.005)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert exited.is_set()
    assert read_json(backup.root / "latest.json")["identity"] == prior[-1]
    for name, data in before.items():
        assert (backup.root / name).read_bytes() == data
    assert not list(backup.root.glob(".rehearsal-*"))
    assert all(p.suffix in {".enc", ".json"} for p in backup.root.iterdir())
