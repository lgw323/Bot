"""Fixed SELECT-1 probe metadata. Never retain exception messages or SQL/paths."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import errno
import sqlite3

from discordbot.platform.errors import AppError, DataIntegrityError, DatabaseUnavailableError

STAGES = frozenset('probe_open probe_configure probe_begin probe_execute probe_fetch probe_commit probe_close probe_admission'.split())
SQLITE_FAMILIES = {sqlite3.SQLITE_BUSY: 'busy', sqlite3.SQLITE_LOCKED: 'locked',
    sqlite3.SQLITE_IOERR: 'io', sqlite3.SQLITE_CANTOPEN: 'cantopen', sqlite3.SQLITE_PERM: 'perm',
    sqlite3.SQLITE_READONLY: 'readonly', sqlite3.SQLITE_FULL: 'full', sqlite3.SQLITE_CORRUPT: 'corrupt',
    sqlite3.SQLITE_NOTADB: 'notadb', sqlite3.SQLITE_CONSTRAINT: 'constraint',
    sqlite3.SQLITE_INTERRUPT: 'interrupt', sqlite3.SQLITE_SCHEMA: 'schema'}
ERRNO_CATEGORIES = {errno.EACCES: 'access', errno.EPERM: 'access', errno.ENOENT: 'missing',
    errno.ENOTDIR: 'missing', errno.EIO: 'io', errno.EROFS: 'readonly', errno.ENOSPC: 'space',
    errno.EMFILE: 'capacity', errno.ENFILE: 'capacity'}
FAMILIES = frozenset('sqlite_operational sqlite_integrity sqlite_database sqlite_other permission os deadline cancellation app unexpected'.split())


def safe_probe_fields(fields: Mapping[str, object]) -> dict[str, str | int | bool]:
    """Second allowlist at telemetry boundary, even for injected AppError contexts."""
    result: dict[str, str | int | bool] = {'operation': 'select1_probe'}
    choices = {'stage': STAGES, 'exception_family': FAMILIES,
               'sqlite_family': frozenset(SQLITE_FAMILIES.values()) | {'other'},
               'errno_category': frozenset(ERRNO_CATEGORIES.values()) | {'other'}}
    for key, allowed in choices.items():
        value = fields.get(key)
        if isinstance(value, str) and value in allowed:
            result[key] = value
    code = fields.get('sqlite_errorcode')
    if type(code) is int and 0 <= code <= 0xFFFFFF:
        result['sqlite_errorcode'] = code
    for key in ('connection_opened', 'close_succeeded', 'cleanup_failed'):
        if type(fields.get(key)) is bool:
            result[key] = fields[key]
    return result


@dataclass
class ProbeTrace:
    stage: str = 'probe_open'
    connection_opened: bool = False
    close_succeeded: bool = False
    cleanup_failed: bool = False
    error: AppError | None = None

    def capture(self, exc: Exception) -> None:
        if self.error is not None:
            self.cleanup_failed = True
            return
        fields: dict[str, object] = {'stage': self.stage}
        if isinstance(exc, sqlite3.Error):
            family = ('sqlite_operational' if isinstance(exc, sqlite3.OperationalError) else
                      'sqlite_integrity' if isinstance(exc, sqlite3.IntegrityError) else
                      'sqlite_database' if isinstance(exc, sqlite3.DatabaseError) else 'sqlite_other')
            code = getattr(exc, 'sqlite_errorcode', None)
            if type(code) is int and 0 <= code <= 0xFFFFFF:
                fields.update(sqlite_errorcode=code, sqlite_family=SQLITE_FAMILIES.get(code & 255, 'other'))
            cls = DataIntegrityError if fields.get('sqlite_family') in {'corrupt', 'notadb', 'constraint', 'schema'} else DatabaseUnavailableError
        elif isinstance(exc, OSError):
            family = 'permission' if isinstance(exc, PermissionError) else 'os'
            fields['errno_category'] = ERRNO_CATEGORIES.get(exc.errno, 'other')
            cls = DatabaseUnavailableError
        elif isinstance(exc, AppError):
            family = {'deadline_exceeded': 'deadline', 'cancellation': 'cancellation'}.get(exc.code.value, 'app')
            cls = type(exc)
        else:
            family, cls = 'unexpected', DataIntegrityError
        fields['exception_family'] = family
        self.error = cls('Fixed database probe failed', context=safe_probe_fields(fields))

    def close(self, conn: sqlite3.Connection) -> None:
        self.stage = 'probe_close'
        try:
            conn.close()
            self.close_succeeded = True
        except Exception as exc:
            self.capture(exc)

    def raise_if_failed(self) -> None:
        if self.error is not None:
            fields = dict(self.error.context)
            fields.update(connection_opened=self.connection_opened, close_succeeded=self.close_succeeded,
                          cleanup_failed=self.cleanup_failed)
            raise type(self.error)('Fixed database probe failed', context=safe_probe_fields(fields)) from None
