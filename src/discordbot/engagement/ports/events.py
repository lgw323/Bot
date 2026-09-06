"""Durable event operations; each mutation owns one repository transaction."""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from discordbot.engagement.ports.repository import MemberData
from discordbot.storage.ports.contracts import DatabaseRequest


@dataclass(frozen=True, slots=True, repr=False)
class VoiceEvent:
    guild_id: int
    user_id: int
    epoch: str
    stream: str
    sequence: int
    channel_id: int | None
    muted: bool
    tick: float


@dataclass(frozen=True, slots=True)
class EngagementConfig:
    master_user_id: int = field(repr=False)
    birthday_channels: tuple[tuple[int, int], ...] = field(default=(), repr=False)
    receipt_capacity: int = 100_000
    receipt_days: int = 7
    voice_capacity: int = 10_000
    request_seconds: float = 5.0

    def __post_init__(self) -> None:
        from discordbot.platform.errors import ConfigurationError
        if (type(self.master_user_id) is not int or self.master_user_id <= 0
                or any(type(value) is not int for value in (self.receipt_capacity, self.receipt_days, self.voice_capacity))
                or type(self.birthday_channels) is not tuple
                or any(type(pair) is not tuple or len(pair) != 2 for pair in self.birthday_channels)
                or type(self.request_seconds) not in (int, float)
                or not 1 <= self.receipt_capacity <= 1_000_000
                or not 1 <= self.receipt_days <= 30
                or not 1 <= self.voice_capacity <= 100_000
                or not 0 < self.request_seconds <= 10
                or len(self.birthday_channels) > 100
                or len(dict(self.birthday_channels)) != len(self.birthday_channels)
                or any(type(x) is not int or x <= 0 for pair in self.birthday_channels for x in pair)):
            raise ConfigurationError("invalid engagement configuration")


class Authorization(Protocol):
    def is_master(self, user_id: int) -> bool: ...


class BirthdayDelivery(Protocol):
    async def send(self, guild_id: int, channel_id: int, users: tuple[int, ...]) -> None: ...


class EngagementEvents(Protocol):
    async def begin_epoch(self, epoch: str, request: DatabaseRequest) -> None: ...
    async def apply_text(self, guild_id: int, user_id: int, event_id: str, xp: int,
                         created: float, now: float, config: EngagementConfig, request: DatabaseRequest) -> bool: ...
    async def apply_voice(self, event: VoiceEvent, capacity: int, request: DatabaseRequest) -> bool: ...
    async def flush_voice(self, epoch: str, tick: float, request: DatabaseRequest, *, observed_only: bool = False) -> None: ...
    async def ranking(self, guild_id: int, request: DatabaseRequest) -> tuple[MemberData, ...]: ...
    async def birthdays(self, guild_id: int, request: DatabaseRequest, *, offset: int = 0) -> tuple[MemberData, ...]: ...
    async def delete_birthday(self, guild_id: int, user_id: int, request: DatabaseRequest) -> bool: ...
    async def claim_birthday(self, guild_id: int, today: date, request: DatabaseRequest) -> bool: ...
    async def finish_birthday(self, guild_id: int, today: date, status: str, request: DatabaseRequest) -> None: ...
