"""User-global favorites and raw guild music persistence contracts."""

from dataclasses import dataclass
from typing import Protocol

from discordbot.storage.ports.contracts import DatabaseRequest


@dataclass(frozen=True, slots=True, repr=False)
class Favorite:
    url: str
    title: str


@dataclass(frozen=True, slots=True, repr=False)
class PlayCount:
    url: str
    title: str
    count: int


class MusicRepository(Protocol):
    async def list_favorites(self, user_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[Favorite, ...]: ...
    async def put_favorite(self, user_id: int, favorite: Favorite, request: DatabaseRequest) -> None: ...
    async def remove_favorite(self, user_id: int, url: str, request: DatabaseRequest) -> bool: ...
    async def get_volume(self, guild_id: int, request: DatabaseRequest) -> float | None: ...
    async def set_volume(self, guild_id: int, volume: float, request: DatabaseRequest) -> None: ...
    async def list_play_counts(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[PlayCount, ...]: ...
