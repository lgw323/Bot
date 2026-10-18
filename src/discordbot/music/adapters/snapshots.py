"""Atomic, bounded restart checkpoints; legacy guild records remain readable."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from discordbot.music.domain.model import Projection
from discordbot.platform.errors import ConflictError, DataIntegrityError, ExternalPermanentError
from discordbot.platform.executors import BoundedExecutor


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RestoreRecord:
    guild_id: int
    identity: str
    revision: int
    session_id: str | None
    paused: bool
    data: dict[str, Any]


class SnapshotStore:
    def __init__(self, path: Path, executor: BoundedExecutor, *, maximum_bytes: int = 4 * 1024 * 1024,
                 guilds: int = 4) -> None:
        self.path, self.executor, self.maximum_bytes, self.guilds = path, executor, maximum_bytes, guilds
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > self.maximum_bytes:
            raise DataIntegrityError("Music snapshot exceeds size limit")
        try:
            result = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(result, dict) or len(result) > self.guilds or any(not key.isdigit() or int(key) < 1 for key in result):
                raise ValueError
            return result
        except (ValueError, UnicodeError):
            raise DataIntegrityError("invalid Music snapshot") from None

    def _write(self, records: dict[str, Any]) -> None:
        temporary = self.path.with_name("." + uuid4().hex + ".tmp")
        try:
            payload = json.dumps(records, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(payload) > self.maximum_bytes:
                raise DataIntegrityError("Music snapshot exceeds size limit")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ExternalPermanentError("Music checkpoint disk operation failed") from None
        finally:
            temporary.unlink(missing_ok=True)

    async def records(self) -> tuple[tuple[RestoreRecord, ...], tuple[int, ...]]:
        async with self._lock:
            data = await self.executor.run_retained(self._read)
        valid, failed = [], []
        for guild, record in data.items():
            try:
                meta = record.get("_v2")
                if "_v2" in record:
                    checked = {**meta}
                    checksum = checked.pop("checksum")
                    if meta["version"] != 2 or meta["revision"] < 0 or checksum != digest({"state": {k: v for k, v in record.items() if k != "_v2"}, "metadata": checked}):
                        raise ValueError
                    identity, revision = meta["identity"], meta["revision"]
                    session, paused = meta.get("session_id"), meta.get("paused", False)
                    if (not isinstance(identity, str) or not 0 < len(identity) <= 64 or type(revision) is not int
                            or (session is not None and (not isinstance(session, str) or not 0 < len(session) <= 128))
                            or type(paused) is not bool):
                        raise ValueError
                else:
                    identity, revision, session, paused = digest(record), 0, None, False
                valid.append(RestoreRecord(int(guild), identity, revision, session, paused,
                                           {k: v for k, v in record.items() if k != "_v2"}))
            except (KeyError, TypeError, ValueError, AttributeError):
                failed.append(int(guild))
        return tuple(valid), tuple(failed)

    async def save(self, projection: Projection) -> None:
        async with self._lock:
            records = await self.executor.run_retained(self._read)
            guild = str(projection.guild_id)
            old = records.get(guild, {}).get("_v2", {})
            if old.get("revision", -1) > projection.revision:
                raise ConflictError("stale Music checkpoint")
            if guild not in records and len(records) >= self.guilds:
                raise DataIntegrityError("too many Music snapshot guilds")
            legacy = projection.legacy()
            metadata = {"version": 2, "revision": projection.revision, "identity": uuid4().hex,
                        "session_id": projection.session_id, "paused": projection.paused}
            metadata["checksum"] = digest({"state": legacy, "metadata": metadata})
            records[guild] = {**legacy, "_v2": metadata}
            await self.executor.run_retained(self._write, records)

    async def acknowledge(self, record: RestoreRecord) -> None:
        """Only the caller that received the actor's restore ACK may consume it."""
        async with self._lock:
            records = await self.executor.run_retained(self._read)
            current = records.get(str(record.guild_id))
            if current is None:
                return
            identity = current.get("_v2", {}).get("identity", digest(current))
            if identity != record.identity:
                raise ConflictError("restore source has changed")
            del records[str(record.guild_id)]
            await self.executor.run_retained(self._write, records)
