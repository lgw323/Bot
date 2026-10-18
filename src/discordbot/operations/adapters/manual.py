"""Single durable request inbox; Discord never executes service commands."""

import hashlib
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

    def _accept(self, operation: str, receipt: str) -> str:
        try:
            with ExclusiveLock(self.operation_lock).acquire():
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
