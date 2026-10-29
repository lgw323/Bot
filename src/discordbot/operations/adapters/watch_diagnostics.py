"""Best-effort bounded diagnostics over the existing authenticated Watch status call.

No Discord credentials or SDK in watch-web. Rows are removed on status response;
an interrupted response or process exit may lose them, just like the local queue.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import logging

from discordbot.operations.adapters.discord_logging import ERRORS, RESULTS, diagnostic_fields, notice

EVENTS = frozenset({'watch.maintenance', 'watch.metadata', 'watch.shutdown',
    'database.probe_failed', 'database.probe_contention', 'database.probe_recovered'})


def _record(row):
    if not isinstance(row, dict) or len(row) > 40:
        return None
    event, result = row.get('event'), row.get('result')
    if not isinstance(event, str) or event not in EVENTS or not isinstance(result, str) or result not in RESULTS:
        return None
    fields = diagnostic_fields(row)
    fields.update(event=event, result=result)
    code = row.get('error_code')
    if isinstance(code, str) and code in ERRORS:
        fields['error_code'] = code
    stamp = row.get('timestamp')
    if isinstance(stamp, str) and len(stamp) <= 40:
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is not None:
            fields['timestamp'] = parsed.astimezone(timezone.utc).isoformat()
    record = logging.LogRecord('discordbot.watch.web', logging.INFO, '', 0, event, (), None)
    record.fields = fields
    return record


class WatchDiagnostics:
    def __init__(self, clock):
        self.clock = clock
        self.pending = OrderedDict()
        self.dropped = 0

    def capture(self, event):
        try:
            record = _record(event.as_dict())
            item = notice(record) if record is not None else None
            if item is None or item.dedup_key in self.pending:
                return
            if len(self.pending) >= 32:
                self.dropped += 1
                return
            self.pending[item.dedup_key] = (self.clock.monotonic(), record.fields)
        except Exception:
            # Diagnostics must not fail the telemetry drain or feature work.
            self.dropped += 1

    def drain(self):
        rows = []
        while self.pending and len(rows) < 8:
            _, (created, fields) = self.pending.popitem(last=False)
            if self.clock.monotonic() - created <= 300:
                rows.append(fields)
            else:
                self.dropped += 1
        return rows


def receive_watch_diagnostics(rows):
    """Revalidate loopback content before it can reach the existing handler."""
    if not isinstance(rows, list) or len(rows) > 8:
        return
    for row in rows:
        try:
            record = _record(row)
            if record is not None and notice(record) is not None:
                logging.getLogger(record.name).handle(record)
        except Exception:
            # A malformed optional row or log handler must not affect readiness.
            continue
