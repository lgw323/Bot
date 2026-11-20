"""Strict navigation shape, after the panel owner has verified Discord identity."""
from __future__ import annotations

import re

_LINK = re.compile(r'https://discord\.com/channels/([1-9][0-9]{0,18})/([1-9][0-9]{0,18})/([1-9][0-9]{0,18})')


def panel_link(value: object, *, channel: int | None = None) -> str | None:
    """Never accept arbitrary URLs or another configured log channel.

    Shape checks are not ownership proof. Only OperationsPanel.verified_link
    supplies this value in production, after fetching the current own panel.
    """
    if type(value) is not str:
        return None
    match = _LINK.fullmatch(value)
    if match is None or any(int(part) >= 2**63 for part in match.groups()):
        return None
    if channel is not None and (type(channel) is not int or int(match[2]) != channel):
        return None
    return value
