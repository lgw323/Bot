"""Watch values, protocol validation and conservative pre-staging ceilings."""

from dataclasses import dataclass, field
import math
import re
from urllib.parse import parse_qs, urlparse

from discordbot.platform.errors import AuthorizationError, CapacityError, ValidationError, ConflictError


class InvalidCapability(AuthorizationError):
    default_safe_message = "유효하지 않거나 만료된 시청 세션입니다."


class ClosedSession(ConflictError):
    default_safe_message = "종료된 시청 세션입니다."


class RateLimited(CapacityError):
    default_safe_message = "요청이 너무 빠릅니다. 잠시 후 다시 시도해 주세요."


class ProtocolFailure(ValidationError):
    pass


class SlowPeer(CapacityError):
    pass


@dataclass(frozen=True, slots=True)
class WatchLimits:
    sessions: int = 8
    clients_per_session: int = 8
    total_clients: int = 64
    mailbox: int = 100
    outbound: int = 16
    playlist: int = 100
    message_bytes: int = 4096
    body_bytes: int = 8192
    requests: int = 32
    rate_per_second: int = 10
    lifetime_seconds: int = 21600

    def __post_init__(self) -> None:
        ceilings = (8, 8, 64, 100, 16, 100, 4096, 8192, 32, 10, 21600)
        for name, ceiling in zip(self.__dataclass_fields__, ceilings):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValidationError("invalid Watch resource limit")


@dataclass(frozen=True, slots=True, repr=False)
class Intent:
    session_id: str  # internal digest, never the bearer capability
    guild: int
    user: int
    created: float
    expires: float
    closed: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class Invite:
    session_id: str
    capability: str
    expires: float
    published: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class Cleanup:
    session_id: str
    channel: int | None
    message: int | None
    admin_channel: int | None
    admin_message: int | None


def positive_id(value: object) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise ValidationError("invalid Watch identifier")
    return value


def display(value: object, maximum: int, default: str = "") -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ProtocolFailure("invalid Watch text")
    return value.strip() or default


def video_id(url: str) -> str:
    try:
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            raise ValueError
        host = (parsed.hostname or "").lower()
        if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
            raise ValueError
        parts = parsed.path.strip("/").split("/")
        candidate = parts[0] if host == "youtu.be" else parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch" else parts[1] if len(parts) >= 2 and parts[0] in {"embed", "live", "shorts"} else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            raise ValueError
        return candidate
    except (ValueError, TypeError):
        raise ValidationError("invalid YouTube video URL") from None


def protocol(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ProtocolFailure("invalid Watch message")
    kind = value["type"]
    allowed = {"join": {"username"}, "chat": {"username", "text"},
        "state_change": {"state", "playing", "time"}, "seek": {"time"},
        "sync_request": set(), "sync_response": {"state", "playing", "time", "videoId"},
        "playlist_change": {"message"}}
    if kind not in allowed or set(value) - allowed[kind] - {"type"}:
        raise ProtocolFailure("unknown Watch message or field")
    result = dict(value)
    if kind == "join":
        result["username"] = display(value.get("username", ""), 50, "임시유저")
    if kind == "chat":
        result["text"] = display(value.get("text", ""), 500)
        if not result["text"]:
            raise ProtocolFailure("empty Watch chat")
        if "username" in value:
            result["username"] = display(value["username"], 50, "임시유저")
    if kind in {"seek", "state_change", "sync_response"}:
        stamp = value.get("time")
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= stamp <= 604800:
            raise ProtocolFailure("invalid Watch playback time")
    if kind in {"state_change", "sync_response"}:
        if ("state" not in value and "playing" not in value
                or "state" in value and (not isinstance(value["state"], str) or value["state"] not in {"playing", "paused"})
                or "playing" in value and type(value["playing"]) is not bool):
            raise ProtocolFailure("invalid Watch playback state")
    if "videoId" in value and (not isinstance(value["videoId"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", value["videoId"])):
        raise ProtocolFailure("invalid Watch playback video")
    if kind == "playlist_change":
        result["message"] = display(value.get("message", ""), 200)
    return result


class Rate:
    def __init__(self, capacity: int) -> None:
        self.capacity, self.count, self.window = capacity, 0, -1

    def take(self, now: float) -> None:
        window = int(now)
        if window != self.window:
            self.window, self.count = window, 0
        if self.count >= self.capacity:
            raise RateLimited("Watch rate exhausted")
        self.count += 1
