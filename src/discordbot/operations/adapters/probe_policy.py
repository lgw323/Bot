"""One proven configure-stage BUSY; two healthy scheduled probes within 15 s."""
from collections.abc import Mapping


def classified_busy(fields: Mapping[str, object]) -> bool:
    return (fields.get('error_code') == 'database_unavailable'
            and fields.get('operation') == 'select1_probe' and fields.get('stage') == 'probe_configure'
            and type(fields.get('sqlite_errorcode')) is int and fields['sqlite_errorcode'] == 5
            and fields.get('sqlite_family') == 'busy'
            and fields.get('exception_family') == 'sqlite_operational'
            and fields.get('connection_opened') is True and fields.get('close_succeeded') is True
            and fields.get('cleanup_failed') is False)


class ProbePolicy:
    """No retry is issued here. Terminal safety failures stay latched until stop."""
    def __init__(self) -> None:
        self.last_busy: float | None = None
        self.pending_since: float | None = None
        self.healthy = 0
        self.hard = False

    def failure(self, fields: Mapping[str, object], now: float, previously_ready: bool) -> str:
        if (not self.hard and previously_ready and classified_busy(fields)
                and self.pending_since is None and (self.last_busy is None or now - self.last_busy > 60)):
            self.last_busy = self.pending_since = now
            self.healthy = 0
            return 'bounded_busy'
        self.hard = True
        return 'hard'

    def success(self, now: float) -> str:
        if self.hard:
            return 'hard'
        if self.pending_since is None:
            return 'healthy'
        if now - self.pending_since >= 15:
            self.hard = True
            return 'recovery_expired'
        self.healthy += 1
        if self.healthy < 2:
            return 'recovering'
        self.pending_since = None
        self.healthy = 0
        return 'recovered'
