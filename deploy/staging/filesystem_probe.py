"""Linux-only PHASE 9 probe, confined to a newly created temporary directory."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def probe(parent: Path) -> dict[str, object]:
    parent = parent.resolve(strict=True)
    if sys.platform != "linux" or not parent.is_dir():
        raise ValueError("An existing Linux scratch directory is required")
    started = time.monotonic()
    result: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="phase9-fs-", dir=parent) as directory:
        root = Path(directory)
        root.chmod(0o2770)
        for name in ("a", "b"):
            (root / name).mkdir()
        (root / "current").symlink_to(root / "a", target_is_directory=True)
        (root / "next").symlink_to(root / "b", target_is_directory=True)
        os.replace(root / "next", root / "current")
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        assert (root / "current").resolve() == root / "b"
        result["atomic_symlink_and_directory_fsync"] = True
        mode = os.umask(0o077)
        try:
            path = root / "synthetic.db"
            connection = sqlite3.connect(path)
            path.chmod(0o660)
            try:
                assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
                connection.execute("CREATE TABLE probe(id INTEGER PRIMARY KEY, value INTEGER)")
                connection.executemany("INSERT INTO probe VALUES (?,?)", ((n, n * 2) for n in range(1000)))
                connection.commit()
                for item in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                    assert stat.S_IMODE(item.stat().st_mode) == 0o660
                    assert item.stat().st_gid == root.stat().st_gid
                result["setgid_db_wal_shm_0660_under_umask_0077"] = True
                with sqlite3.connect(root / "snapshot.db") as snapshot:
                    connection.backup(snapshot)
                    assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    assert snapshot.execute("SELECT count(*),sum(value) FROM probe").fetchone() == (1000, 999000)
            finally:
                connection.close()
            with sqlite3.connect(path) as reopened:
                assert reopened.execute("SELECT count(*) FROM probe").fetchone()[0] == 1000
            result["synthetic_sqlite_snapshot_and_restart"] = True
            lock = root / "operation.lock"
            with lock.open("a+b") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                code = ("import fcntl,sys; f=open(sys.argv[1],'a+b');\n"
                        "try: fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                        "except BlockingIOError: sys.exit(23)\n")
                child = subprocess.run([sys.executable, "-I", "-c", code, str(lock)],
                                       capture_output=True, timeout=5)
                assert child.returncode == 23
            with lock.open("a+b") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result["cross_process_flock_and_release"] = True
        finally:
            os.umask(mode)
        usage = os.statvfs(root)
        result["available_bytes"] = usage.f_bavail * usage.f_frsize
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch-parent", required=True, type=Path)
    print(json.dumps(probe(parser.parse_args().scratch_parent), sort_keys=True))
