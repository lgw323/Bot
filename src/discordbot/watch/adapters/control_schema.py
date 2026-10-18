"""Validate every successful control response before it reaches Discord UI."""

import math
import re

from discordbot.platform.errors import ExternalTemporaryError


def response_data(operation: str, value: dict[str, object]) -> dict[str, object]:
    def sid(item):
        return isinstance(item, str) and re.fullmatch(r"[a-f0-9]{64}", item)
    def identity(item):
        return item is None or type(item) is int and 0 < item < 2**63
    valid = False
    if operation == "create":
        valid = (set(value) == {"session_id", "capability", "expires", "published"}
            and sid(value["session_id"]) and isinstance(value["capability"], str)
            and re.fullmatch(r"[A-Za-z0-9_-]{43}", value["capability"])
            and type(value["expires"]) in (int, float) and math.isfinite(value["expires"])
            and value["expires"] > 0 and type(value["published"]) is bool)
    elif operation == "status":
        valid = set(value) == {"ready"} and type(value["ready"]) is bool
    elif operation == "cleanup":
        valid = set(value) == {"items"} and isinstance(value["items"], list) and len(value["items"]) <= 100
        if valid:
            for row in value["items"]:
                if (not isinstance(row, dict) or set(row) != {"session_id", "channel", "message", "admin_channel", "admin_message"}
                    or not sid(row["session_id"]) or not all(identity(row[k]) for k in ("channel", "message", "admin_channel", "admin_message"))
                    or (row["channel"] is None) != (row["message"] is None)
                    or (row["admin_channel"] is None) != (row["admin_message"] is None)):
                    valid = False
                    break
    else:
        valid = not value
    if not valid:
        raise ExternalTemporaryError("invalid Watch control response schema")
    return value
