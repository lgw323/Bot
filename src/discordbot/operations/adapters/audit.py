"""Durable bounded audit segments; failure is never converted into success."""

from datetime import datetime, timezone
from pathlib import Path
import uuid

from discordbot.operations.adapters.filesystem import atomic_json, identifier


class Audit:
    def __init__(self, root: Path, correlation: str | None = None) -> None:
        self.root = root
        self.correlation = identifier(correlation or uuid.uuid4().hex)

    def write(self, operation: str, release: str, result: str, reason: str) -> None:
        fields = dict(operation=identifier(operation), release=identifier(release), result=identifier(result),
                      reason=identifier(reason), correlation=self.correlation,
                      timestamp=datetime.now(timezone.utc).isoformat())
        # Hard cap: operator archives evidence explicitly; never silently discard
        # durable audit history to make a new deployment succeed.
        if sum(1 for _ in self.root.iterdir()) >= 10000:
            raise OSError("audit capacity reached")
        atomic_json(self.root / (uuid.uuid4().hex + ".json"), fields)
