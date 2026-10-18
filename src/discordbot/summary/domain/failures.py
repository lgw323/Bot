"""Allowlisted Summary failure metadata; no provider text or user payloads."""
from collections.abc import Mapping

REASONS = frozenset({'http_rate_limited', 'http_server_error', 'http_rejected',
                     'transport_error', 'timeout'})


def safe_failure_fields(context: Mapping[str, object]) -> dict[str, str | int]:
    fields: dict[str, str | int] = {}
    reason, status = context.get('reason'), context.get('http_status')
    if isinstance(reason, str) and reason in REASONS:
        fields['reason'] = reason
    if type(status) is int and 100 <= status <= 599:
        fields['http_status'] = status
    return fields
