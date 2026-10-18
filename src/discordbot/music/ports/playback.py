"""Vendor-free asynchronous, cancellation-cooperative boundaries."""
from dataclasses import dataclass, field
from uuid import uuid4
from collections.abc import Callable
from typing import Protocol

from discordbot.music.domain.model import Track


@dataclass(frozen=True, slots=True, repr=False)
class Media:
    path: str
    key: str
    lease_id: str = field(default_factory=lambda: uuid4().hex)


class Provider(Protocol):
    async def lookup(self, query: str, requester_id: int, *, limit: int) -> tuple[Track, ...]: ...


class MediaLibrary(Protocol):
    async def acquire(self, track: Track) -> Media: ...
    async def speech(self, text: str) -> Media: ...
    async def release(self, media: Media, *, corrupt: bool = False) -> None: ...


class Audio(Protocol):
    async def connect(self, channel_id: int) -> None: ...
    async def start(self, media: Media, attempt: str, seek: int, volume: float,
                    notify: Callable[[str, bool], None]) -> None: ...
    async def stop(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def disconnect(self) -> None: ...


class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...
