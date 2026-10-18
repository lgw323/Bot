"""One process-global media/TTS disk budget; publish only verified complete files."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from discordbot.music.ports.playback import Media
from discordbot.platform.clock import Clock
from discordbot.platform.errors import CapacityError, DataIntegrityError, ExternalPermanentError
from discordbot.platform.executors import BoundedExecutor

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Entry:
    path: Path
    size: int
    checksum: str
    touched: float
    pins: int = 0


class DiskCache:
    def __init__(self, directory: Path, executor: BoundedExecutor, clock: Clock, *,
                 total_bytes: int = 256 * 1024 * 1024, item_bytes: int = 32 * 1024 * 1024,
                 items: int = 128, ttl: float = 86400, waiting: int = 8) -> None:
        if not 0 < item_bytes <= total_bytes or not 1 <= items <= 256 or not 0 < ttl <= 86400 or not 0 <= waiting <= 16:
            raise ValueError("invalid cache bounds")
        self.directory, self.executor, self.clock = directory, executor, clock
        self.total_bytes, self.item_bytes, self.items, self.ttl = total_bytes, item_bytes, items, ttl
        self._entries: dict[str, Entry] = {}
        self._leases: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.capacity, self.admitted = waiting + 1, 0
        self.closed = False

    @property
    def bytes(self) -> int:
        return sum(entry.size for entry in self._entries.values())

    async def start(self) -> None:
        def scan() -> dict[str, Entry]:
            self.directory.mkdir(parents=True, exist_ok=True)
            result = {}
            # Dedicated cache directory only. Unknown files are never deleted.
            for path in self.directory.iterdir():
                if path.suffix == ".part" and len(path.stem) == 32:
                    path.unlink(missing_ok=True)
                elif path.suffix == ".blob":
                    parts = path.stem.split("-")
                    if len(parts) != 2 or any(len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in parts):
                        continue
                    size = path.stat().st_size
                    if not 0 < size <= self.item_bytes or len(result) >= self.items:
                        path.unlink()
                        continue
                    age = max(0, self.clock.now().timestamp() - path.stat().st_mtime)
                    result[parts[0]] = Entry(path, size, parts[1], self.clock.monotonic() - age)
            return result
        self._entries = await self.executor.run_retained(scan)
        async with self._lock:
            await self._evict(0, 0)

    async def _remove(self, key: str) -> None:
        entry = self._entries[key]
        await self.executor.run_retained(lambda: entry.path.unlink(missing_ok=True))
        del self._entries[key]

    async def _evict(self, reserve: int, count: int) -> None:
        for key, entry in sorted(tuple(self._entries.items()), key=lambda kv: kv[1].touched):
            if entry.pins:
                continue
            if (self.bytes + reserve > self.total_bytes or len(self._entries) + count > self.items
                    or self.clock.monotonic() - entry.touched >= self.ttl):
                await self._remove(key)
        if self.bytes + reserve > self.total_bytes or len(self._entries) + count > self.items:
            raise CapacityError("Music cache budget pinned or exhausted")

    async def acquire(self, identity: str, producer: Callable[[Path, int], Awaitable[None]]) -> Media:
        if self.closed or self.admitted >= self.capacity:
            raise CapacityError("Music cache acquisition capacity exhausted")
        self.admitted += 1
        key = hashlib.sha256(identity.encode()).hexdigest()
        work_id = uuid4().hex
        temporary = None
        failure_reason = 'cache_read_failure'
        try:
            async with self._lock:
                if len(self._leases) >= 32:
                    raise CapacityError("Music cache lease capacity exhausted")
                entry = self._entries.get(key)
                if entry:
                    valid = await self.executor.run_retained(lambda: entry.path.exists() and entry.path.stat().st_size == entry.size
                                                     and hashlib.sha256(entry.path.read_bytes()).hexdigest() == entry.checksum)
                    if valid and (entry.pins or self.clock.monotonic() - entry.touched < self.ttl):
                        stamp = self.clock.now().timestamp()
                        await self.executor.run_retained(lambda: os.utime(entry.path, (stamp, stamp)))
                        entry.pins += 1
                        entry.touched = self.clock.monotonic()
                        media = Media(str(entry.path), key)
                        self._leases[media.lease_id] = key
                        logger.info('music.cache_leased', extra={'fields':{'stage':'cache_lease',
                            'work_id':work_id, 'result':'hit', 'bytes':entry.size}})
                        return media
                    if entry.pins:
                        raise DataIntegrityError("in-use media cache corrupted")
                    await self._remove(key)
                # Reserve worst-case bytes BEFORE the producer starts. Partials
                # and published entries together stay within the global budget.
                await self._evict(self.item_bytes, 1)
                temporary = self.directory / (uuid4().hex + ".part")
                failure_reason = 'cache_write_failure'
                logger.info('music.media_acquisition_started', extra={'fields':{'stage':'media_acquisition', 'work_id':work_id}})
                await producer(temporary, self.item_bytes)
                logger.info('music.media_acquired', extra={'fields':{'stage':'media_acquisition', 'work_id':work_id}})
                failure_reason = 'cache_publish_failure'

                def publish() -> Entry:
                    size = temporary.stat().st_size
                    if size == 0:
                        raise DataIntegrityError('Music cache item is empty', context={'reason':'empty_output'})
                    if size > self.item_bytes:
                        raise CapacityError("Music cache item size invalid", context={'reason':'output_limit'})
                    with temporary.open("rb") as source:
                        checksum = hashlib.file_digest(source, "sha256").hexdigest()
                    destination = self.directory / (key + "-" + checksum + ".blob")
                    with temporary.open("r+b") as source:
                        os.fsync(source.fileno())
                    os.replace(temporary, destination)
                    return Entry(destination, size, checksum, self.clock.monotonic(), 1)

                entry = await self.executor.run_retained(publish)
                self._entries[key] = entry
                media = Media(str(entry.path), key)
                self._leases[media.lease_id] = key
                logger.info('music.cache_leased', extra={'fields':{'stage':'cache_lease',
                    'work_id':work_id, 'result':'published', 'bytes':entry.size}})
                return media
        except OSError:
            raise ExternalPermanentError("Music cache disk operation failed", context={'reason':failure_reason}) from None
        finally:
            if temporary is not None:
                await self.executor.run_retained(lambda: temporary.unlink(missing_ok=True))
            self.admitted -= 1

    async def release(self, media: Media, *, corrupt: bool = False) -> None:
        # Lease release cannot queue behind another guild's long download.
        # All index/pin mutations run on this event loop; deletion is deferred
        # to the bounded cleanup/acquire owner under its lock.
        entry = self._entries.get(media.key)
        if entry and str(entry.path) == media.path and self._leases.pop(media.lease_id, None) == media.key:
            entry.pins = max(0, entry.pins - 1)
            if corrupt:
                entry.touched = -self.ttl

    async def cleanup(self) -> None:
        async with self._lock:
            await self._evict(0, 0)

    async def close(self) -> None:
        self.closed = True
        async with self._lock:
            if any(entry.pins for entry in self._entries.values()):
                raise DataIntegrityError("Music cache still has live audio leases")
