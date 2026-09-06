"""Storage shape validation; no user-facing business policy."""

import math

from discordbot.platform.errors import ValidationError


def identifier(value: int) -> None:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ValidationError("invalid storage identifier")


def nonnegative(value: int | float, *, integer: bool = False) -> None:
    if (type(value) not in (int, float) or (integer and type(value) is not int)
            or not math.isfinite(value) or not 0 <= value <= 2**63 - 1):
        raise ValidationError("invalid stored number")


def text_value(value: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, str) or (nonempty and not value) or len(value.encode("utf-8")) > 65536:
        raise ValidationError("invalid stored text")
