"""Legacy Watch reader, before Phase 6 assigns the session write owner."""

from dataclasses import dataclass
from typing import Protocol

from discordbot.storage.ports.contracts import DatabaseRequest


@dataclass(frozen=True, slots=True, repr=False)
class WatchSessionData:
    session_id: str
    guild_id: int
    created_by: int
    created_at: str
    channel_id: int | None
    message_id: int | None


@dataclass(frozen=True, slots=True, repr=False)
class WatchPlaylistData:
    video_url: str
    video_title: str
    added_by: str
    order_index: int


class WatchRepository(Protocol):
    async def get_session(self, guild_id: int, session_id: str, request: DatabaseRequest) -> WatchSessionData | None: ...
    async def list_sessions(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[WatchSessionData, ...]: ...
    async def list_playlist(self, guild_id: int, session_id: str, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[WatchPlaylistData, ...]: ...
