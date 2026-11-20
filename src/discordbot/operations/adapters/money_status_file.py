"""One fixed public projection reader; never Money data, credentials or commands."""
from pathlib import Path
import os
import stat
import sys
from typing import Any

from discordbot.operations.adapters.money_status import MAXIMUM_BYTES

PROJECTION_PATH = Path('/run/mymoney-status/status.json')


def _identity(info) -> tuple[int, ...]:
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid',
        'st_nlink','st_size','st_mtime_ns','st_ctime_ns'))


def _read_projection(path: Path, owner: int) -> bytes | None:
    """Internal synthetic-fixture seam; public entrypoint never accepts a path."""
    directories = []; file_fd = None; result = None
    try:
        if not path.is_absolute() or type(owner) is not int or owner <= 0:
            return None
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os,'O_CLOEXEC',0)
        current = Path(path.anchor)
        directory_fd = os.open(str(current),flags)
        directories.append((current,directory_fd,os.fstat(directory_fd)))
        for part in path.parts[1:-1]:
            if part in ('','.','..'):
                return None
            directory_fd = os.open(part,flags,dir_fd=directory_fd)
            current = current/part
            directories.append((current,directory_fd,os.fstat(directory_fd)))
        def verify_directories():
            for index,(name,fd,before) in enumerate(directories):
                actual = os.fstat(fd); named = os.stat(str(name),follow_symlinks=False)
                expected_owner = owner if index == len(directories)-1 else 0
                if (not stat.S_ISDIR(actual.st_mode) or not stat.S_ISDIR(named.st_mode)
                        or actual.st_uid != expected_owner or stat.S_IMODE(actual.st_mode)&0o022
                        or index == len(directories)-1 and stat.S_IMODE(actual.st_mode) != 0o755
                        or _identity(actual) != _identity(before) or _identity(named) != _identity(before)):
                    raise ValueError
        verify_directories()
        file_fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=directory_fd)
        before = os.fstat(file_fd); named = os.stat(path.name,dir_fd=directory_fd,follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(named.st_mode)
                or before.st_uid != owner or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o644
                or not 1 <= before.st_size <= MAXIMUM_BYTES or _identity(before) != _identity(named)):
            return None
        raw = os.read(file_fd,before.st_size+1)
        if (len(raw) != before.st_size or _identity(os.fstat(file_fd)) != _identity(before)
                or _identity(os.stat(path.name,dir_fd=directory_fd,follow_symlinks=False)) != _identity(before)):
            return None
        verify_directories()
        result = raw
    except (OSError,ValueError,TypeError,AttributeError):
        result = None
    finally:
        for fd in ([file_fd] if file_fd is not None else []) + [row[1] for row in reversed(directories)]:
            try:
                os.close(fd)
            except OSError:
                result = None
    return result


def _owner_uid() -> int:
    import pwd
    entry = pwd.getpwnam('mymoney')
    if entry.pw_name != 'mymoney' or type(entry.pw_uid) is not int or entry.pw_uid <= 0:
        raise ValueError
    return entry.pw_uid


def read_fixed_projection() -> bytes | None:
    if sys.platform != 'linux':
        return None
    try:
        return _read_projection(PROJECTION_PATH,_owner_uid())
    except (OSError,KeyError,ValueError,ImportError):
        return None


class FixedMoneyStatus:
    """No construction I/O; use only the existing bounded read-only executor."""
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    async def snapshot(self) -> bytes | None:
        return await self.executor.run(read_fixed_projection)
