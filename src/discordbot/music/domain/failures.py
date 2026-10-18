"""Allowlisted failure evidence; no provider text or request data crosses it."""
from collections.abc import Mapping
from typing import Any


REASONS = frozenset({
    'executable_not_found', 'process_start_failure', 'process_io_failure', 'child_nonzero',
    'provider_rejected', 'auth_required', 'no_audio_format', 'download_failed', 'http_forbidden',
    'timeout', 'invalid_output', 'empty_output', 'cache_read_failure', 'cache_write_failure',
    'cache_publish_failure', 'output_limit', 'js_runtime_missing',
})


def safe_failure_fields(context: Mapping[str, Any]) -> dict[str, str | int]:
    result: dict[str, str | int] = {}
    reason = context.get('reason')
    if isinstance(reason, str) and reason in REASONS:
        result['reason'] = reason
    code = context.get('child_exit_code')
    if type(code) is int and -255 <= code <= 255:
        result['child_exit_code'] = code
    return result
