"""Immutable Music identities and legacy-compatible projections."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

from discordbot.platform.errors import ValidationError


class LoopMode(IntEnum):
    NONE = 0
    SONG = 1
    QUEUE = 2


def volume_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValidationError("invalid music volume")
    return float(value)


@dataclass(frozen=True, slots=True, repr=False)
class Track:
    item_id: str
    url: str
    title: str
    duration: int
    requester_id: int
    uploader: str = ""
    thumbnail: str | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if (not self.item_id or len(self.item_id) > 64 or parsed.scheme not in {"http", "https"}
                or not parsed.hostname or len(self.url) > 2048 or len(self.title) > 512
                or not self.title or not isinstance(self.duration, int) or not 0 <= self.duration <= 86400
                or not isinstance(self.requester_id, int) or self.requester_id < 1
                or len(self.uploader) > 512 or (self.thumbnail is not None and len(self.thumbnail) > 2048)):
            raise ValidationError("invalid track metadata")

    @classmethod
    def from_legacy(cls, data: Mapping[str, Any], *, item_id: str | None = None) -> Track:
        try:
            return cls(item_id or uuid4().hex, data["webpage_url"], data["title"], data.get("duration", 0),
                       data["requester_id"], data.get("uploader", "알 수 없는 아티스트"), data.get("thumbnail"))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValidationError("invalid saved track") from None

    def legacy(self) -> dict[str, Any]:
        return {"webpage_url": self.url, "title": self.title, "duration": self.duration,
                "thumbnail": self.thumbnail, "uploader": self.uploader, "requester_id": self.requester_id}


def normalize_title(title: str) -> str:
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", "", title.lower())
    for keyword in ("mv", "music video", "official", "audio", "live", "cover", "lyrics", "가사", "공식", "커버", "라이브", "lyric video"):
        title = title.replace(keyword, "")
    title = re.sub(r"[-–—]", " ", title)
    return " ".join(re.sub(r"[^a-z0-9\s가-힣]", "", title).split())


@dataclass(frozen=True, slots=True)
class Bounds:
    actors: int = 4
    mailbox: int = 64
    queue: int = 500
    requests: int = 8
    tts_queue: int = 4
    provider_seconds: float = 30
    acquire_seconds: float = 90

    def __post_init__(self) -> None:
        if not all(0 < n <= ceiling for n, ceiling in ((self.actors, 4), (self.mailbox, 256),
                   (self.queue, 1000), (self.requests, 16), (self.tts_queue, 8),
                   (self.provider_seconds, 60), (self.acquire_seconds, 180))):
            raise ValueError("invalid Music hard bounds")


@dataclass(frozen=True, slots=True, repr=False)
class Projection:
    guild_id: int
    revision: int
    generation: int
    queue: tuple[Track, ...]
    current: Track | None
    session_id: str | None
    attempt: str | None
    status: str
    elapsed: int
    volume: float
    loop: LoopMode
    autoplay: bool
    text_channel_id: int | None
    voice_channel_id: int | None
    retry_at: float | None
    error: str | None

    def legacy(self) -> dict[str, Any]:
        return {"text_channel_id": self.text_channel_id, "voice_channel_id": self.voice_channel_id,
                "volume": self.volume, "loop_mode": self.loop.name, "auto_play_enabled": self.autoplay,
                "current_song": self.current.legacy() if self.current else None,
                "elapsed_seconds": self.elapsed, "queue": [song.legacy() for song in self.queue]}
