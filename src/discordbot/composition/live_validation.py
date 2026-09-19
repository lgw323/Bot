"""Root-owned, release-bound, finite PHASE 10B admission; absent means legacy policy."""
import json
import os
from pathlib import Path
import stat
import time


def full_sweep_active(release: str, marker: Path = Path('/run/discordbot-live-smoke'),
                      *, now: float | None = None) -> bool:
    try:
        if marker.is_symlink():
            return False
        fd = os.open(marker, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 512:
                return False
            value = json.load(stream)
        started, expires = value['started_unix'], value['expires_unix']
        current = time.time() if now is None else now
        return (value['mode'] == 'phase10-full-sweep' and value['release'] == release
                and type(started) in (int, float) and type(expires) in (int, float)
                and 0 < expires - started <= 1800 and started <= current < expires)
    except (OSError, ValueError, TypeError, KeyError):
        return False
