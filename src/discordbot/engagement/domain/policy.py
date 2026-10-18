"""Approved XP/calendar rules, independent of storage and Discord."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import calendar

KST = timezone(timedelta(hours=9))


def text_xp(text: str) -> int:
    return sum((3 if (ord(c) - 0xAC00) % 28 else 2)
               if 0xAC00 <= ord(c) <= 0xD7A3 else int(bool(c.strip())) for c in text)


def voice_xp(seconds: int | float) -> int:
    return int(seconds // 60) * 5


def required_xp(level: int) -> int:
    return int(100 * level ** 1.8 + 10 * 1.1 ** level)


def level_from_xp(total: int) -> int:
    level = 1
    while total >= required_xp(level):
        level += 1
    return level


@dataclass(frozen=True, slots=True)
class Progress:
    text: int
    seconds: int | float

    @property
    def voice(self) -> int:
        return voice_xp(self.seconds)

    @property
    def total(self) -> int:
        return self.text + self.voice

    @property
    def level(self) -> int:
        return level_from_xp(self.total)


def valid_birthday(month: int, day: int) -> bool:
    if type(month) is not int or type(day) is not int:
        return False
    try:
        date(2000, month, day)  # Leap birthdays remain valid every registration year.
        return True
    except ValueError:
        return False


def birthday_due(month: int, day: int, today: date) -> bool:
    return valid_birthday(month, day) and ((month, day) == (today.month, today.day)
        or ((month, day) == (2, 29) and (today.month, today.day) == (2, 28)
            and not calendar.isleap(today.year)))


def notification_date(now: datetime) -> date | None:
    local = now.astimezone(KST)
    return local.date() if local.hour >= 9 else None


def notification_poll_delay(now: datetime) -> float:
    local = now.astimezone(KST)
    nine = local.replace(hour=9, minute=0, second=0, microsecond=0)
    return min(60.0, (nine - local).total_seconds()) if local < nine else 60.0
