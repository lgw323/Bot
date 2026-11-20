"""Process-local SDK observations, not outage durations or root-cause claims."""
from __future__ import annotations

from dataclasses import dataclass
import math


_MAX_SECONDS = 7 * 86400


def _number(value: object) -> int | float | None:
    # Do not coerce objects/strings or render rejected values in diagnostics.
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


@dataclass(slots=True)
class GatewayObservations:
    """Constant-space counters; all values reset when the process restarts."""

    disconnects: int = 0
    under_one_second: int = 0
    unknown_intervals: int = 0
    capped_intervals: int = 0
    notices_enqueued: int = 0
    notices_not_enqueued: int = 0
    last_interval: float = -1.0
    last_latency: float = -1.0

    def _latency(self, value: object) -> float | None:
        numeric = _number(value)
        self.last_latency = (float(numeric) if numeric is not None and 0 <= numeric <= _MAX_SECONDS
                             else -1.0)
        return None if self.last_latency < 0 else self.last_latency

    def disconnected(self, latency: object) -> dict[str, object]:
        self.disconnects += 1
        return {
            'event': 'discord.gateway_disconnect_observed',
            'sdk_callback': 'disconnect',
            'connection_sequence': self.disconnects,
            'cause': 'unconfirmed',
            'sdk_last_heartbeat_latency_seconds': self._latency(latency),
        }

    def recovered(self, start: object, end: object, callback: object,
                  enqueued: bool, latency: object) -> dict[str, object]:
        first, last = _number(start), _number(end)
        interval = _number(last - first) if first is not None and last is not None else None
        if interval is not None and interval < 0:
            interval = None
        capped = interval is not None and interval > _MAX_SECONDS
        self.last_interval = -1.0 if interval is None else float(min(interval, _MAX_SECONDS))
        self.unknown_intervals += int(interval is None)
        self.capped_intervals += int(capped)
        self.under_one_second += int(interval is not None and interval < 1)
        self.notices_enqueued += int(enqueued)
        self.notices_not_enqueued += int(not enqueued)
        return {
            'event': 'discord.gateway_recovery_observed',
            'sdk_callback': callback if type(callback) is str and callback in ('ready', 'resumed') else 'unknown',
            'connection_sequence': self.disconnects,
            'cause': 'unconfirmed',
            'measurement_scope': 'sdk_callback_interval_not_total_outage',
            'observed_interval_seconds': None if interval is None else self.last_interval,
            'interval_capped': capped,
            'recovery_notice_enqueued': enqueued,
            'sdk_last_heartbeat_latency_seconds': self._latency(latency),
        }

    def gauges(self) -> dict[str, float]:
        return {
            'discord_log_disconnect_events_total': self.disconnects,
            'discord_log_recovery_under_one_second_total': self.under_one_second,
            'discord_log_recovery_interval_unknown_total': self.unknown_intervals,
            'discord_log_recovery_interval_capped_total': self.capped_intervals,
            'discord_log_recovery_notices_enqueued_total': self.notices_enqueued,
            'discord_log_recovery_notices_not_enqueued_total': self.notices_not_enqueued,
            'discord_log_last_observed_connection_interval_seconds': self.last_interval,
            'discord_log_last_heartbeat_latency_seconds': self.last_latency,
        }
