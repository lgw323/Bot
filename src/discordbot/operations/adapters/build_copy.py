"""Materialize the known venv alias without privileged metadata or raw errors."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any

from discordbot.operations.adapters.filesystem import contained
from discordbot.platform.errors import DataIntegrityError


def materialize_library(library: Path, alias: Path) -> None:
    """Copy regular payload, ordinary modes and timestamps, never links/xattrs.

    Release inventory forbids links. Owner/group come from the deployment
    layout; SUID/SGID/sticky bits, ACLs and capabilities are not payload.
    Publish later applies the existing immutable runtime-group permissions.
    """
    if library.parent != alias.parent or library.name != "lib" or alias.name != "lib64":
        raise DataIntegrityError("unexpected virtual environment copy paths")
    contained(library.parent, library)
    contained(alias.parent, alias)
    if not stat.S_ISDIR(library.lstat().st_mode):
        raise DataIntegrityError("virtual environment library must be a directory")

    def copy(source: Path, destination: Path) -> None:
        if source != library:
            contained(library, source)
            contained(alias, destination)
        info = source.lstat()
        if stat.S_ISDIR(info.st_mode):
            destination.mkdir()
            for child in source.iterdir():
                copy(child, destination / child.name)
        elif stat.S_ISREG(info.st_mode):
            shutil.copyfile(source, destination, follow_symlinks=False)
        else:
            raise DataIntegrityError("virtual environment library contains a non-regular entry")
        contained(alias.parent, destination)
        os.utime(destination, ns=(info.st_atime_ns, info.st_mtime_ns),
                 follow_symlinks=os.utime not in os.supports_follow_symlinks)
        destination.chmod(stat.S_IMODE(info.st_mode) & 0o777)

    copy(library, alias)


_ERRNO_CODES = {errno.EPERM: "operation_not_permitted", errno.EACCES: "permission_denied",
                errno.ENOENT: "missing", errno.ENOSPC: "no_space", errno.EROFS: "readonly",
                errno.EEXIST: "exists", errno.EIO: "io_error", errno.EFBIG: "file_size_limit",
                errno.ENOTDIR: "not_directory", errno.EISDIR: "is_directory"}


def copy_failure_details(exc: BaseException, library: Path, alias: Path) -> dict[str, Any]:
    """Bound nested shutil.Error/exception chains; emit only fixed labels/codes.

    CPython's copytree aggregates OSError as (source, destination, str(error)),
    losing its errno attribute. Extract only a leading known numeric errno;
    never serialize exception messages, paths, traceback locals or type names.
    """
    result: dict[str, Any] = {"errors": [], "truncated": False}
    seen: set[int] = set()
    visits = 0

    def location(value: object) -> str:
        if not isinstance(value, (str, Path)) or len(str(value)) > 4096:
            return "other"
        path = Path(value)
        for label, root in (("venv_library", library), ("venv_alias", alias)):
            if path == root or path.is_relative_to(root):
                return label
        return "other"

    def visit(value: object, source: object = None, destination: object = None, depth: int = 0) -> None:
        nonlocal visits
        if visits >= 32 or depth >= 8 or len(result["errors"]) >= 16:
            result["truncated"] = True
            return
        visits += 1
        if isinstance(value, BaseException):
            if id(value) in seen:
                result["truncated"] = True
                return
            seen.add(id(value))
        if type(value) is shutil.Error and len(value.args) == 1 and isinstance(value.args[0], list):
            items = value.args[0]
            for entry in items[:16]:
                if isinstance(entry, (tuple, list)) and len(entry) == 3:
                    visit(entry[2], entry[0], entry[1], depth + 1)
                else:
                    visit(None, depth=depth + 1)
            if len(items) > 16:
                result["truncated"] = True
        else:
            number = value.errno if isinstance(value, OSError) else None
            if isinstance(value, str):
                match = re.match(r"\[Errno ([0-9]{1,5})\]", value[:32])
                number = int(match[1]) if match else None
            if type(number) is not int or number not in _ERRNO_CODES:
                number = None
            result["errors"].append({"errno": number, "code": _ERRNO_CODES.get(number, "unclassified"),
                                     "source": location(source), "destination": location(destination)})
        if isinstance(value, BaseException):
            previous = value.__cause__ if value.__cause__ is not None else value.__context__
            if previous is not None:
                visit(previous, depth=depth + 1)

    visit(exc)
    return result
