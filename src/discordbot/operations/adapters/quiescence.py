"""Bounded, read-only cgroup-v2 termination evidence for the fixed service pair."""

from __future__ import annotations

import os
from pathlib import Path
import stat

from discordbot.operations.adapters.filesystem import contained
from discordbot.platform.errors import DataIntegrityError, ExternalTemporaryError


class CgroupQuiescence:
    """Absence is evidence only under a readable, verified cgroup-v2 root.

    Reviewed units use system.slice and do not delegate cgroup management.
    Neither an empty MainPID nor an empty top-level cgroup.procs is sufficient:
    all descendant groups must also be empty. Unknown evidence fails closed.
    """

    def __init__(self, root: Path = Path('/sys/fs/cgroup')) -> None:
        self.root = root

    @staticmethod
    def _regular(path: Path, maximum: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError
            raw = stream.read(maximum + 1)
            if len(raw) > maximum:
                raise ValueError
            return raw

    def verify(self, unit: str) -> None:
        if unit not in {'discord-bot.service', 'watch-web.service'}:
            raise ExternalTemporaryError('unsupported rollback service')
        try:
            if not self.root.is_absolute() or not stat.S_ISDIR(self.root.lstat().st_mode):
                raise ValueError
            marker = contained(self.root, self.root / 'cgroup.controllers')
            self._regular(marker, 4096)
            parent = contained(self.root, self.root / 'system.slice')
            if not stat.S_ISDIR(parent.lstat().st_mode):
                raise ValueError
            with os.scandir(parent) as visible:
                next(visible, None)  # Prove the expected hierarchy is readable.
            target = contained(self.root, parent / unit)
            try:
                meta = target.lstat()
            except FileNotFoundError:
                return  # Loaded/stopped unit metadata is checked by the caller.
            if not stat.S_ISDIR(meta.st_mode):
                raise ValueError
            pending = [(target, 0)]
            directories = entries = 0
            while pending:
                node, depth = pending.pop()
                directories += 1
                if directories > 256 or depth > 16:
                    raise ValueError
                procs = contained(self.root, node / 'cgroup.procs')
                if self._regular(procs, 65536):
                    raise ValueError  # Any PID or malformed nonempty evidence blocks recovery.
                for child in node.iterdir():
                    entries += 1
                    if entries > 4096:
                        raise ValueError
                    contained(self.root, child)
                    info = child.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        pending.append((child, depth + 1))
        except (OSError, ValueError, DataIntegrityError):
            # Never include filesystem paths, file contents or raw OS errors.
            raise ExternalTemporaryError('rollback process absence is not confirmed') from None
