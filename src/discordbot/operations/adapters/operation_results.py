"""Bounded, non-secret operational outcomes shared by the worker and UI.

This is status evidence, never authority to run an operation. Only the existing
operations CLI writes outcomes; accepting a manual request is not success.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from uuid import uuid4

from discordbot.operations.adapters.filesystem import atomic_json, contained, identifier
from discordbot.platform.errors import DataIntegrityError

RESULTS = frozenset({'in_progress', 'ok', 'failed', 'ok_cleanup_failed'})
TERMINAL = RESULTS - {'in_progress'}
STAGES = frozenset('accepted build preflight test compatibility backup publish stop activate start readiness '
                   'smoke audit retention complete unchanged checkpoint interrupted unknown'.split())
SOURCES = frozenset({'manual', 'operator', 'scheduled', 'unknown'})


def _read(path: Path) -> dict[str, Any] | None:
    """Reject links, special files, duplicate keys and unbounded metadata."""
    contained(path.parent, path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > 4096:
            raise DataIntegrityError('operation status metadata invalid')
        raw = stream.read(4097)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if len(raw) > 4096 or not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise DataIntegrityError('operation status metadata invalid') from None


def validate_operation_result(value: dict[str, Any]) -> dict[str, Any]:
    expected = {'version', 'id', 'operation', 'source', 'result', 'stage', 'release', 'timestamp', 'receipt'}
    try:
        if (set(value) != expected or type(value['version']) is not int or value['version'] != 1
                or not isinstance(value['id'], str) or not re.fullmatch('[a-f0-9]{32}', value['id'])
                or value['operation'] not in {'update', 'restart'} or value['source'] not in SOURCES
                or value['result'] not in RESULTS or value['stage'] not in STAGES
                or value['receipt'] is not None and (not isinstance(value['receipt'], str)
                    or not re.fullmatch('[a-f0-9]{64}', value['receipt']))):
            raise ValueError
        identifier(value['release'])
        if (value['result'] == 'ok' and (value['stage'] not in {'complete', 'unchanged'}
                or value['stage'] == 'unchanged' and value['operation'] != 'update')
                or value['result'] == 'ok_cleanup_failed' and (value['operation'], value['stage']) != ('update', 'retention')):
            raise ValueError
        stamp = value['timestamp']
        if not isinstance(stamp, str) or len(stamp) > 40 or datetime.fromisoformat(stamp).tzinfo is None:
            raise ValueError
        return dict(value)
    except (KeyError, TypeError, ValueError):
        raise DataIntegrityError('operation result fields invalid') from None


def read_operation_result(state: Path) -> dict[str, Any] | None:
    """Return only the documented schema; a corrupt file never becomes success."""
    value = _read(state / 'operation-result.json')
    return validate_operation_result(value) if value is not None else None


class OperationResults:
    def __init__(self, state: Path) -> None:
        self.path = state / 'operation-result.json'

    def write(self, operation: str, source: str, result: str, stage: str, release: str,
              *, identity: str | None = None, receipt: str | None = None,
              timestamp: datetime | None = None) -> dict[str, Any]:
        stamp = timestamp or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            raise DataIntegrityError('operation timestamp timezone required')
        value = validate_operation_result(dict(version=1, id=identity or uuid4().hex,
            operation=operation, source=source, result=result, stage=stage, release=release,
            timestamp=stamp.astimezone(timezone.utc).isoformat(), receipt=receipt))
        # Same bounded shared-state policy as manual-request.json. This contains
        # no account IDs, payloads, paths, credentials or exception text.
        atomic_json(self.path, value)
        os.chmod(self.path, 0o660)
        return value
