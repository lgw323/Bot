"""Read effective unit credential sources, then stat them; never open key contents."""
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import subprocess

UNITS = ('discord-bot.service', 'watch-web.service', 'discordbot-backup.service')


def bindings(text: str) -> dict[str, str]:
    """Parse systemctl cat's fragment/drop-ins in their supplied order.

    The repository uses simple absolute file sources. Reject unsupported syntax
    rather than guessing paths or treating an unparsed property as no keys.
    """
    result: dict[str, str] = {}
    section = ''
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            section = line
        if section != '[Service]' or not line.startswith('LoadCredential='):
            continue
        value = line.partition('=')[2]
        if not value:
            result.clear()
            continue
        role, separator, source = value.partition(':')
        if (not separator or not re.fullmatch(r'[a-z_]+', role)
                or not re.fullmatch(r'/etc/discordbot/[A-Za-z0-9_./-]+', source)
                or '..' in Path(source).parts):
            raise ValueError('unsupported credential binding; no missing-key conclusion')
        if role in result and result[role] != source:
            raise ValueError('ambiguous credential binding; no missing-key conclusion')
        result[role] = source
    if not result:
        raise ValueError('no parsed credential bindings; discovery incomplete')
    return result


def metadata(source: Path) -> dict[str, object]:
    try:
        value = source.lstat()
    except PermissionError:
        return {'status': 'unreadable', 'contents_read': False}
    except FileNotFoundError:
        return {'status': 'missing', 'contents_read': False}
    return {'status': 'present', 'contents_read': False, 'regular_file': stat.S_ISREG(value.st_mode),
            'mode': oct(stat.S_IMODE(value.st_mode)), 'uid': value.st_uid, 'gid': value.st_gid,
            'nonempty': value.st_size > 0}


def collect() -> dict[str, object]:
    result: dict[str, object] = {}
    for unit in UNITS:
        process = subprocess.run(['systemctl', 'cat', unit], capture_output=True, text=True, timeout=10)
        if process.returncode:
            result[unit] = {'status': 'unit_unreadable'}
            continue
        try:
            sources = bindings(process.stdout)
        except ValueError:
            result[unit] = {'status': 'discovery_incomplete'}
            continue
        result[unit] = {'status': 'bindings_resolved', 'credentials': {
            role: {'source': source, **metadata(Path(source))} for role, source in sources.items()}}
    return result


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2))
