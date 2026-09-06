"""Stored membership facts; XP/date policy belongs to Phase 4 application code."""

from dataclasses import dataclass
from typing import Protocol

from discordbot.storage.ports.contracts import DatabaseRequest


@dataclass(frozen=True, slots=True, repr=False)
class MemberData:
    user_id: int
    guild_id: int
    xp: int
    level: int
    total_vc_seconds: int | float
    birth_month: int | None
    birth_day: int | None


class EngagementRepository(Protocol):
    async def get_member(self, guild_id: int, user_id: int, request: DatabaseRequest) -> MemberData | None: ...
    async def list_members(self, guild_id: int, request: DatabaseRequest, *, limit: int = 100, offset: int = 0) -> tuple[MemberData, ...]: ...
    async def add_progress(self, guild_id: int, user_id: int, xp: int, seconds: int | float, request: DatabaseRequest, *, level: int | None = None) -> None: ...
    async def set_birthday(self, guild_id: int, user_id: int, month: int | None, day: int | None, request: DatabaseRequest) -> None: ...
