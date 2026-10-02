"""Engagement use cases; no Discord, SQL, process-global lock or task creation."""

import asyncio
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from discordbot.engagement.domain.policy import Progress, birthday_due, notification_date, text_xp, valid_birthday
from discordbot.engagement.ports.events import Authorization, BirthdayDelivery, EngagementConfig, EngagementEvents, VoiceEvent, VoicePresence
from discordbot.engagement.ports.repository import EngagementRepository, MemberData
from discordbot.platform.clock import Clock
from discordbot.platform.context import current_correlation
from discordbot.platform.errors import AppError, AuthorizationError, CapacityError, ConflictError, ExternalTemporaryError, ShutdownError, ValidationError
from discordbot.storage.ports.contracts import DatabaseRequest


class EngagementService:
    def __init__(self, repository: EngagementRepository, events: EngagementEvents,
                 authorization: Authorization, config: EngagementConfig, clock: Clock, epoch: str) -> None:
        self.repository = repository
        self.events = events
        self.authorization = authorization
        self.config = config
        self.clock = clock
        self.epoch = epoch
        self._accepting = False
        self._voice_faulted = False
        self._voice_stream: str | None = None
        self._voice_pending = 0
        self._voice_drained = asyncio.Event()
        self._voice_drained.set()

    def request(self) -> DatabaseRequest:
        correlation = current_correlation()
        return DatabaseRequest.within(self.config.request_seconds, correlation.correlation_id if correlation else "engagement")

    def _admit(self) -> None:
        if not self._accepting:
            raise ConflictError("engagement admission closed")

    async def start(self) -> None:
        await self.events.begin_epoch(self.epoch, self.request())
        self._accepting = True

    async def stop(self) -> None:
        self._accepting = False
        tick, request = self.clock.monotonic(), self.request()
        # SQL ordering alone does not order the callers' failure handling. Close
        # admission, then drain those outcomes before choosing the flush policy.
        try:
            async with asyncio.timeout(self.config.request_seconds):
                await self._voice_drained.wait()
        except TimeoutError:
            raise ShutdownError("voice observations did not drain") from None
        # A missed mute/leave makes extrapolation unsafe. Keep observed segments
        # only at an uncertain boundary; a new epoch reconciles live presence.
        await self.events.flush_voice(self.epoch, tick, request,
            observed_only=self._voice_faulted, stream=self._voice_stream)

    @contextmanager
    def _voice_observation(self) -> Iterator[None]:
        # Event-loop owned; no await between admission and registering this work.
        self._voice_pending += 1
        self._voice_drained.clear()
        try:
            yield
        except (AppError, asyncio.CancelledError):
            self._voice_faulted = True
            raise
        finally:
            self._voice_pending -= 1
            if not self._voice_pending:
                self._voice_drained.set()

    def gateway_session(self, stream: str) -> None:
        self._admit()
        # Set before any await: shutdown between raw READY and the cache snapshot
        # must not extrapolate rows belonging to the lost Gateway session.
        self._voice_stream = stream

    async def voice_ready(self, stream: str, members: tuple[VoicePresence, ...]) -> None:
        self._admit()
        if self._voice_faulted:
            raise ConflictError("voice observation incomplete; restart reconciliation required")
        if self._voice_stream is not None and stream != self._voice_stream:
            raise ConflictError("voice snapshot belongs to an inactive Gateway session")
        tick = self.clock.monotonic()
        events = tuple(VoiceEvent(member.guild_id, member.user_id, self.epoch, stream, 0,
            member.channel_id, member.muted, tick) for member in members)
        with self._voice_observation():
            await self.events.reconcile_voice(self.epoch, stream, events,
                self.config.voice_capacity, self.request())

    async def message(self, guild_id: int | None, user_id: int, event_id: str, content: str,
                      created: datetime, *, bot: bool = False) -> bool:
        self._admit()
        if bot or guild_id is None:
            return False
        return await self.events.apply_text(guild_id, user_id, event_id, text_xp(content),
            created.timestamp(), self.clock.now().timestamp(), self.config, self.request())

    async def voice(self, guild_id: int, user_id: int, stream: str, sequence: int,
                    channel_id: int | None, muted: bool, *, bot: bool = False, tick: float | None = None) -> bool:
        self._admit()
        if bot:
            return False
        if self._voice_faulted:
            raise ConflictError("voice observation incomplete; restart reconciliation required")
        if self._voice_stream is not None and stream != self._voice_stream:
            raise ConflictError("voice event belongs to an inactive Gateway session")
        event = VoiceEvent(guild_id, user_id, self.epoch, stream, sequence, channel_id, muted,
                           self.clock.monotonic() if tick is None else tick)
        with self._voice_observation():
            return await self.events.apply_voice(event, self.config.voice_capacity, self.request())

    def profile_target(self, requester: int, requested: int | None) -> int:
        return requested if requested is not None and self.authorization.is_master(requester) else requester

    async def profile(self, guild_id: int, user_id: int) -> Progress:
        self._admit()
        member = await self.repository.get_member(guild_id, user_id, self.request())
        return Progress(member.xp, member.total_vc_seconds) if member else Progress(0, 0)

    async def ranking(self, guild_id: int) -> tuple[MemberData, ...]:
        self._admit()
        return await self.events.ranking(guild_id, self.request())

    def require_master(self, requester: int) -> None:
        if not self.authorization.is_master(requester):
            raise AuthorizationError("master authorization required", safe_message="이 명령어를 사용할 권한이 없습니다.")

    async def register_birthday(self, requester: int, guild_id: int, user_id: int, month: int, day: int) -> None:
        self._admit()
        self.require_master(requester)
        if not valid_birthday(month, day):
            raise ValidationError("invalid calendar date", safe_message="올바른 날짜를 입력해주세요.")
        await self.repository.set_birthday(guild_id, user_id, month, day, self.request())

    async def delete_birthday(self, requester: int, guild_id: int, user_id: int) -> bool:
        self._admit()
        self.require_master(requester)
        return await self.events.delete_birthday(guild_id, user_id, self.request())

    async def birthdays(self, guild_id: int, *, offset: int = 0) -> tuple[MemberData, ...]:
        self._admit()
        return await self.events.birthdays(guild_id, self.request(), offset=offset)

    async def notify_guild(self, guild_id: int, channel_id: int, delivery: BirthdayDelivery) -> bool:
        self._admit()
        today = notification_date(self.clock.now())
        if today is None:
            return False
        users: list[int] = []
        offset = 0
        while True:
            page = await self.birthdays(guild_id, offset=offset)
            users.extend(row.user_id for row in page if birthday_due(row.birth_month, row.birth_day, today))
            if len(users) > 10_000 or offset >= 100_000:
                raise CapacityError("birthday scan capacity exceeded")
            if len(page) < 100:
                break
            offset += 100
        # Claim before external side effect; a cancelled/uncertain send is never retried blindly.
        if not await self.events.claim_birthday(guild_id, today, self.request()):
            return False
        try:
            if users:
                async with asyncio.timeout(self.config.request_seconds):
                    await delivery.send(guild_id, channel_id, tuple(users))
        except asyncio.CancelledError:
            raise  # Durable 'claimed' already suppresses duplicate sends after restart.
        except Exception:
            await self.events.finish_birthday(guild_id, today, "uncertain", self.request())
            raise ExternalTemporaryError("birthday delivery outcome uncertain") from None
        await self.events.finish_birthday(guild_id, today, "sent", self.request())
        return bool(users)
