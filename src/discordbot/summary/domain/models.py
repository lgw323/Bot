"""Vendor-free, bounded Summary values. Content is deliberately absent from repr."""

from dataclasses import dataclass, field
from datetime import datetime
import math

from discordbot.platform.errors import DataIntegrityError, NotFoundError, ValidationError


class NoSummaryData(NotFoundError):
    default_safe_message = "요약할 메시지가 없습니다."


class MalformedSummary(DataIntegrityError):
    default_safe_message = "요약 내용을 구조화하는 데 실패했습니다. 잠시 후 다시 시도해 주세요."


@dataclass(frozen=True, slots=True)
class Scope:
    guild: int
    channel: int


@dataclass(frozen=True, slots=True, repr=False)
class Message:
    scope: Scope
    id: int
    created_at: datetime
    author: str
    content: str
    bot: bool = False


@dataclass(frozen=True, slots=True)
class SummaryConfig:
    sources: tuple[Scope, ...]
    enabled: bool = True
    max_messages: int = 1000  # per source; at most ten sources
    retention_hours: float = 24.0
    preload_hours: float = 3.0
    page_size: int = 100
    prune_seconds: float = 600.0
    result_capacity: int = 32
    result_seconds: float = 3600.0
    timezone_offset_hours: float = 9.0

    def __post_init__(self) -> None:
        if not isinstance(self.sources, tuple) or not all(isinstance(scope, Scope) for scope in self.sources) or type(self.enabled) is not bool:
            raise ValidationError("Summary configuration must be immutable and typed")
        if not math.isfinite(self.timezone_offset_hours) or not -12 <= self.timezone_offset_hours <= 14:
            raise ValidationError("invalid Summary timezone")
        if (len(self.sources) > 10 or len(set(self.sources)) != len(self.sources)
                or len({s.guild for s in self.sources}) != len(self.sources)
                or any(s.guild <= 0 or s.channel <= 0 for s in self.sources)):
            raise ValidationError("invalid Summary sources")
        for value, maximum in ((self.max_messages, 1000), (self.page_size, 100),
                               (self.result_capacity, 32)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError("invalid Summary count bound")
        for value, maximum in ((self.retention_hours, 168), (self.preload_hours, self.retention_hours),
                               (self.prune_seconds, 600), (self.result_seconds, 3600)):
            if not math.isfinite(value) or not 0 < value <= maximum:
                raise ValidationError("invalid Summary time bound")


@dataclass(frozen=True, slots=True, repr=False)
class Query:
    hours: float = 6.0
    keywords: str = ""
    users: str = ""
    extra: str = ""

    def validate(self, retention_hours: float) -> None:
        if not math.isfinite(self.hours) or not 0 < self.hours <= retention_hours:
            raise ValidationError("invalid Summary range", safe_message=f"기간은 0시간 초과 {retention_hours:g}시간 이하여야 합니다.")
        if any(not isinstance(v, str) or len(v) > 1000 for v in (self.keywords, self.users, self.extra)):
            raise ValidationError("invalid Summary filter")

    def matches(self, message: Message) -> bool:
        keywords = tuple(s.strip().lower() for s in self.keywords.split(",") if s.strip())
        users = tuple(s.strip().lower() for s in self.users.split(",") if s.strip())
        return ((not keywords or any(s in message.content.lower() for s in keywords))
                and (not users or message.author.lower() in users))


@dataclass(frozen=True, slots=True, repr=False)
class Topic:
    title: str
    time: str = "N/A"
    participants: str = "N/A"
    keywords: str = "N/A"
    main_point: str = "정보 없음"
    context: str = "정보 없음"
    details: str = "정보 없음"


@dataclass(frozen=True, slots=True, repr=False)
class Summary:
    overall: str
    topics: tuple[Topic, ...]
    input_tokens: int = 0

    def validate(self) -> None:
        # Reject oversized output instead of silently losing inaccessible topics.
        if not isinstance(self.overall, str) or not self.overall or len(self.overall) > 3000 or not 1 <= len(self.topics) <= 100:
            raise MalformedSummary("invalid Summary structure")
        if not isinstance(self.input_tokens, int) or self.input_tokens < 0:
            raise MalformedSummary("invalid token count")
        for topic in self.topics:
            for name in Topic.__dataclass_fields__:
                value = getattr(topic, name)
                if not isinstance(value, str) or not value or len(value) > (200 if name == "title" else 800):
                    raise MalformedSummary("invalid Summary topic")


@dataclass(frozen=True, slots=True, repr=False)
class Prompt:
    instruction: str
    data: str


@dataclass(frozen=True, slots=True, repr=False)
class Result:
    id: str
    scope: Scope
    destination: int
    query: Query
    summary: Summary
    expires_at: float
    created_at: datetime
    message_id: int | None = field(default=None)

    def page(self, number: int) -> tuple[tuple[str, Topic], ...]:
        if type(number) is not int or not 0 <= number < (len(self.summary.topics) + 24) // 25:
            raise ValidationError("invalid Summary page")
        return tuple((f"{self.id}:{i}", topic) for i, topic in enumerate(self.summary.topics)
                     if number * 25 <= i < (number + 1) * 25)
