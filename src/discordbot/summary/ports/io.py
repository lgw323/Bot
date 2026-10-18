"""Small cancellable async dependencies; implementations must not suppress cancellation."""

from datetime import datetime
from typing import Protocol

from discordbot.summary.domain.models import Message, Prompt, Scope, Summary


class Authorization(Protocol):
    async def require(self, scope: Scope, requester: int) -> None: ...


class History(Protocol):
    async def page(self, scope: Scope, *, before: int | None, after: datetime,
                   limit: int) -> tuple[Message, ...]: ...


class Provider(Protocol):
    async def generate(self, prompt: Prompt, *, remaining: float) -> Summary: ...
    async def close(self) -> None: ...
