"""Discord scope/permission and history translation only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from discordbot.platform.errors import AuthorizationError, ExternalTemporaryError
from discordbot.summary.domain.models import Message, Scope


def message_value(message: Any) -> Message | None:
    if message.guild is None:
        return None
    return Message(Scope(message.guild.id, message.channel.id), message.id,
                   message.created_at, message.author.display_name, message.content, message.author.bot)


class DiscordAuthorization:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def require(self, scope: Scope, requester: int) -> None:
        channel = self.bot.get_channel(scope.channel)
        guild = self.bot.get_guild(scope.guild)
        member = guild.get_member(requester) if guild else None
        if channel is None or getattr(channel.guild, "id", None) != scope.guild or member is None:
            raise AuthorizationError("Summary source access denied")
        permissions = channel.permissions_for(member)
        if not permissions.view_channel or not permissions.read_message_history:
            raise AuthorizationError("Summary source access denied")


class DiscordHistory:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def page(self, scope: Scope, *, before: int | None, after: datetime, limit: int) -> tuple[Message, ...]:
        import discord

        channel = self.bot.get_channel(scope.channel)
        if channel is None or getattr(channel.guild, "id", None) != scope.guild:
            raise AuthorizationError("Summary history source unavailable")
        try:
            rows = []
            async for message in channel.history(limit=limit, after=after,
                    before=discord.Object(before) if before is not None else None, oldest_first=False):
                value = message_value(message)
                if value is not None:
                    rows.append(value)
            return tuple(rows)
        except discord.Forbidden:
            raise AuthorizationError("Summary history denied") from None
        except discord.HTTPException:
            raise ExternalTemporaryError("Summary history unavailable") from None
