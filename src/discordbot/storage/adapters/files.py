"""Private candidates and no-clobber publication; never replace a live DB."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from discordbot.platform.errors import ConflictError


@contextmanager
def candidate_file(destination: Path, suffix: str = ".db") -> Iterator[Path]:
    if not destination.is_absolute() or not destination.parent.is_dir():
        raise ConflictError("candidate requires an existing absolute parent directory")
    fd, name = tempfile.mkstemp(prefix=".discordbot-candidate-", suffix=suffix, dir=destination.parent)
    os.close(fd)
    path = Path(name)
    try:
        yield path
    finally:
        for item in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            item.unlink(missing_ok=True)


def sync_file(path: Path) -> None:
    # Windows CRT _commit requires a writable descriptor. Only candidates call this.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def sync_directory(directory: Path) -> None:
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def publish_new(candidate: Path, destination: Path) -> None:
    """Atomic no-replace hard link on the same filesystem, then remove temp name.

    Fail closed on filesystems without link support. No exists/replace race and no
    point at which a zero-byte/partial destination can be mistaken for a good DB.
    """
    sync_file(candidate)
    try:
        os.link(candidate, destination)
    except FileExistsError:
        raise ConflictError("destination already exists; original preserved") from None
    sync_directory(destination.parent)


def distinct_paths(source: Path, destination: Path) -> None:
    if (source.resolve() == destination.resolve()
            or (source.exists() and destination.exists() and os.path.samefile(source, destination))):
        raise ConflictError("source and destination must be different files")
