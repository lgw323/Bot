"""Bounded panel publication state; no Discord calls or message deletion.

A nonce is one publication generation. Persist it before sending and never
replace a publishing generation on restart merely because its send is uncertain.
At most one previous panel may await a confirmed non-destructive retirement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from discordbot.operations.adapters.filesystem import ExclusiveLock, atomic_json, read_json
from discordbot.platform.errors import ValidationError


_BASE = {"version", "channel", "message", "nonce", "state"}
_V2 = _BASE | {"previous", "created_at", "published_at"}


def _message(value: object) -> bool:
    return type(value) is int and 0 < value < 2**63


def _timestamp(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 40:
        return False
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return False
        stamp.astimezone(timezone.utc)
        return True
    except (ValueError, OverflowError):
        return False


def _now(value: datetime | None = None) -> str:
    stamp = datetime.now(timezone.utc) if value is None else value
    if type(stamp) is not datetime or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValidationError("panel timestamp must be aware")
    try:
        return stamp.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError):
        raise ValidationError("invalid panel timestamp") from None


class PanelStore:
    """CAS transitions preserve both a current panel and one pending predecessor."""
    def __init__(self, state: Path, channel: int) -> None:
        self.state, self.channel = state, channel
        self.path, self.lock = state / "operations-panel.json", state / ".operations-panel.lock"

    def read(self) -> dict[str, Any] | None:
        try:
            value = read_json(self.path, 1024, reject_duplicates=True)
        except FileNotFoundError:
            return None
        version = value.get("version")
        if (type(version) is not int or version not in {1, 2}
                or set(value) != (_BASE if version == 1 else _V2)
                or type(value["channel"]) is not int or value["channel"] != self.channel
                or type(value["nonce"]) is not str or re.fullmatch(r"[a-f0-9]{24}", value["nonce"]) is None
                or type(value["state"]) is not str or value["state"] not in {"publishing", "published"}
                or value["state"] == "published" and not _message(value["message"])
                or value["state"] == "publishing" and value["message"] is not None):
            raise ValidationError("invalid persisted operations panel")
        if version == 2:
            if (value["previous"] is not None and not _message(value["previous"])
                    or value["previous"] is not None and value["previous"] == value["message"]
                    or not _timestamp(value["created_at"])
                    or value["state"] == "published" and not _timestamp(value["published_at"])
                    or value["state"] == "publishing" and value["published_at"] is not None):
                raise ValidationError("invalid persisted panel rotation")
        return value

    def _new(self, previous: int | None = None) -> dict[str, Any]:
        return {"version": 2, "channel": self.channel, "message": None,
                "nonce": uuid4().hex[:24], "state": "publishing", "previous": previous,
                "created_at": _now(), "published_at": None}

    def claim(self) -> tuple[dict[str, Any], bool]:
        with ExclusiveLock(self.lock).acquire():
            old = self.read()
            if old is not None:
                return old, False
            row = self._new()
            atomic_json(self.path, row)
            return row, True

    def adopt_existing(self, nonce: str, message: int) -> dict[str, Any]:
        """Record a uniquely verified existing panel only while state is absent.

        Discord ownership/guild/components/generation proof belongs to the caller;
        this CAS must never replace a published or uncertain existing marker.
        """
        if type(nonce) is not str or re.fullmatch(r"[a-f0-9]{24}", nonce) is None or not _message(message):
            raise ValidationError("invalid existing panel identity")
        with ExclusiveLock(self.lock).acquire():
            if self.read() is not None:
                raise ValidationError("panel appeared during existing-panel discovery")
            stamp = _now()
            row = {"version": 2, "channel": self.channel, "message": message, "nonce": nonce,
                   "state": "published", "previous": None, "created_at": stamp, "published_at": stamp}
            atomic_json(self.path, row)
            return row

    def published(self, nonce: str, message: int, published_at: datetime | None = None) -> None:
        """Acknowledge a send or externally verified exact-nonce reconciliation."""
        if type(nonce) is not str or re.fullmatch(r"[a-f0-9]{24}", nonce) is None or not _message(message):
            raise ValidationError("invalid published panel identity")
        stamp = _now(published_at)
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if row is None or row["nonce"] != nonce or row["state"] != "publishing" or row.get("previous") == message:
                raise ValidationError("panel publication changed")
            # Legacy uncertain publication may be acknowledged, never re-sent.
            replacement = {**row, "version": 2, "previous": row.get("previous"),
                           "created_at": row.get("created_at", stamp),
                           "message": message, "state": "published", "published_at": stamp}
            atomic_json(self.path, replacement)

    def rotate(self, expected: dict[str, Any]) -> dict[str, Any]:
        """Claim exactly one replacement; retirement must finish before another."""
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if (row is None or row != expected or row["state"] != "published"
                    or row.get("previous") is not None):
                raise ValidationError("panel changed or retirement pending")
            replacement = self._new(previous=row["message"])
            if replacement["nonce"] == row["nonce"]:
                raise ValidationError("panel nonce reused")
            atomic_json(self.path, replacement)
            return replacement

    def retired(self, previous: int) -> dict[str, Any]:
        """Acknowledge only a matching predecessor's confirmed safe edit/missing proof."""
        if not _message(previous):
            raise ValidationError("invalid retired panel identity")
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if row is None or row["state"] != "published" or row.get("previous") != previous:
                raise ValidationError("panel retirement changed")
            replacement = {**row, "previous": None}
            atomic_json(self.path, replacement)
            return replacement

    def replace_missing(self, expected: dict[str, Any]) -> dict[str, Any]:
        """Only confirmed Unknown Message may replace an unchanged current marker."""
        with ExclusiveLock(self.lock).acquire():
            row = self.read()
            if (row is None or row != expected or row["state"] != "published"
                    or row.get("previous") is not None):
                raise ValidationError("panel changed during missing-message recovery")
            replacement = self._new()
            if replacement["nonce"] == row["nonce"]:
                raise ValidationError("panel nonce reused")
            atomic_json(self.path, replacement)
            return replacement
