"""Single durable request inbox; Discord never executes service commands."""

import hashlib
import json
import os
from pathlib import Path

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.filesystem import ExclusiveLock, atomic_json, read_json
from discordbot.platform.errors import ConflictError, ValidationError, ExternalTemporaryError
from discordbot.platform.executors import BoundedExecutor


def write_request(path: Path, value: dict) -> None:
    atomic_json(path, value)
    os.chmod(path, 0o660)


class RequestInbox:
    def __init__(self, state: Path, operation_lock: Path, executor: BoundedExecutor, audit: Audit, release: str) -> None:
        self.state, self.operation_lock, self.executor, self.audit, self.release = state, operation_lock, executor, audit, release

    async def accept(self, operation: str, receipt: str) -> str:
        if operation not in {"update", "restart"} or not isinstance(receipt, str) or not 1 <= len(receipt) <= 100:
            raise ValidationError("invalid manual operation")
        return await self.executor.run_retained(self._accept, operation, hashlib.sha256(receipt.encode()).hexdigest())

    async def snapshot(self) -> dict[str, str | None]:
        """Only bounded control metadata crosses into the Discord panel."""
        return await self.executor.run(self._snapshot)

    def _snapshot(self) -> dict[str, str | None]:
        path = self.state / "manual-request.json"
        try:
            value = read_json(path, 131072, reject_duplicates=True)
        except FileNotFoundError:
            value = {}
        operation = value.get("operation")
        result = value.get("result")
        receipt = value.get("receipt")
        if value and (operation not in {"update", "restart"}
                      or result not in {"pending", "in_progress", "ok", "failed", "ok_cleanup_failed"}
                      or not isinstance(receipt, str) or len(receipt) != 64
                      or any(c not in "0123456789abcdef" for c in receipt)):
            raise ValidationError("invalid manual request status")
        revision = hashlib.sha256(json.dumps([operation, result, receipt], separators=(",", ":")).encode()).hexdigest()
        return {"operation": operation, "result": result, "revision": revision}

    async def accept_current(self, operation: str, receipt: str, expected_revision: str) -> str:
        if (operation not in {"update", "restart"} or not isinstance(receipt, str) or not 1 <= len(receipt) <= 100
                or not isinstance(expected_revision, str) or len(expected_revision) != 64
                or any(c not in "0123456789abcdef" for c in expected_revision)):
            raise ValidationError("invalid confirmed manual operation")
        return await self.executor.run_retained(self._accept, operation, hashlib.sha256(receipt.encode()).hexdigest(), expected_revision)

    def _accept(self, operation: str, receipt: str, expected_revision: str | None = None) -> str:
        try:
            with ExclusiveLock(self.operation_lock).acquire():
                if expected_revision is not None and self._snapshot()["revision"] != expected_revision:
                    return "stale"
                request = self.state / "manual-request.json"
                history = []
                if request.exists():
                    old = read_json(request)
                    history = [old.get("receipt"), *old.get("history", [])][:1000]
                    if old.get("result") in {"pending", "in_progress"} or receipt in history:
                        return "already_running"
                self.audit.write("manual_" + operation, self.release, "started", "accepted")
                write_request(request, {"operation": operation, "receipt": receipt, "result": "pending", "history": history})
                return "accepted"
        except ConflictError:
            return "already_running"
        except OSError:
            raise ExternalTemporaryError("manual request persistence failed") from None
