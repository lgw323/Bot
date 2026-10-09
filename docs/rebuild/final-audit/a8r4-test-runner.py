"""Local A8R4 evidence runner: credentials, operational data and network denied."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "conftest.py"))
PROTECTED = tuple(os.path.normcase(str(ROOT / path)) + os.sep
                  for path in ("data", "scratch/phase10"))


def guard(event, args):
    if event in {"open", "sqlite3.connect"} and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        resolved = os.path.normcase(os.path.realpath(path))
        if any(candidate.startswith(prefix) for candidate in (path, resolved) for prefix in PROTECTED):
            raise PermissionError("A8R4 denies operational data access")
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname"}:
        # Windows asyncio implements its internal wakeup pair using loopback.
        # Permit only stdlib socketpair construction, never an application socket.
        frame = sys._getframe(1)
        while frame:
            if frame.f_code.co_name in {"socketpair", "_fallback_socketpair"} and frame.f_code.co_filename == __import__("socket").__file__:
                return
            frame = frame.f_back
        raise PermissionError("A8R4 denies network access")


sys.addaudithook(guard)
import pytest

# Kept below the reusable parent-guard prefix: installed-admission loaders do
# not acquire this source-only adapter or a new source-test dependency.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_probe_guard
import_probe_guard.install(ROOT)

raise SystemExit(pytest.main(sys.argv[1:]))
