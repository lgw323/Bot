"""Exact, local-only adapter for the unchanged architecture import subprocess.

This is a reviewed-code audit boundary, not an OS sandbox for hostile Python.
No general subprocess permission is granted by this adapter.
"""
from __future__ import annotations

import ast
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

TEST_SHA256 = "8040d050100e41539eb9bebed4c4bdeee875a15103e66a9da02dd0bd7ec9d363"
_launch: ContextVar[tuple[Any, ...] | None] = ContextVar("import_probe_launch", default=None)
LAUNCHES: list[dict[str, Any]] = []

# Embedded before the original script: the child cannot inherit parent audit hooks.
# Paths are checked both lexically and after resolving aliases, without Path.resolve.
CHILD_GUARD = r'''
import os
import sys
sys.dont_write_bytecode = True
def _normal(path):
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))
def _within(path, root):
    return path == root or path.startswith(root + os.sep)
_owned = _normal(OWNED)
_read_roots = tuple(_normal(p) for p in READ_ROOTS)
_protected = tuple(_normal(p) for p in PROTECTED)
def _path_guard(value, write=False):
    if not isinstance(value, (str, bytes, os.PathLike)):
        if write:
            raise PermissionError('import probe denies descriptor write')
        return
    requested = _normal(value)
    resolved = _normal(os.path.realpath(requested))
    for path in (requested, resolved):
        parts = path.replace('\\', '/').split('/')
        if any(part.startswith('.env') or part in {'.ssh', '.aws', '.git', 'secrets', 'credentials'} for part in parts):
            raise PermissionError('import probe denies credentials')
        if any(_within(path, root) for root in _protected):
            raise PermissionError('import probe denies operational data')
        if _within(path, _owned):
            continue
        if write or not any(_within(path, root) for root in _read_roots):
            raise PermissionError('import probe denies non-owned path')
        if os.path.splitext(path)[1].lower() not in {'.py', '.pyc', '.pyd', '.dll', '.so', '.zip', '.pth'}:
            raise PermissionError('import probe permits code reads only')
def _guard(event, args):
    if event == 'open':
        mode = args[1]
        flags = args[2] or 0
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        _path_guard(args[0], writing)
    elif event == 'sqlite3.connect':
        _path_guard(args[0], True)
    elif event in {'os.rename', 'os.link', 'os.symlink'}:
        _path_guard(args[0], True)
        _path_guard(args[1], True)
    elif event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.chown', 'os.truncate', 'os.utime'}:
        _path_guard(args[0], True)
    elif event.startswith('socket.'):
        raise PermissionError('import probe denies transport')
    elif event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork', 'os.startfile', 'os.startfile/2', 'os.putenv', 'os.unsetenv'}:
        raise PermissionError('import probe denies process/environment escape')
sys.addaudithook(_guard)
# Safe rejection probes emit audit events only; none opens the named paths or
# contacts a transport. These run in the real child before the original script.
assert sys.flags.isolated and sys.flags.dont_write_bytecode and sys.dont_write_bytecode
assert set(os.environ) <= {'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE', 'TEMP', 'TMP', 'PYTHON_DOTENV_DISABLED', 'LC_CTYPE'}
_negative_events = [
    ('open', (PROTECTED[0] + os.sep + 'forbidden.db', 'r', 0)),
    ('open', (PROTECTED[1] + os.sep + 'forbidden.py', 'r', 0)),
    ('open', (OWNED + os.sep + '.env', 'r', 0)),
    ('open', (OWNED + os.sep + '.ssh' + os.sep + 'id_test', 'r', 0)),
    ('open', (os.path.dirname(OWNED) + os.sep + 'not-owned-probe.txt', 'w', os.O_CREAT | os.O_WRONLY)),
    ('open', (READ_ROOTS[0] + os.sep + 'forbidden.pyc', 'w', os.O_CREAT | os.O_WRONLY)),
    ('socket.getaddrinfo', ('example.invalid', 443, 0, 0, 0)),
    ('socket.connect', (None, ('192.0.2.1', 443))),
    ('socket.sendto', (None, ('192.0.2.1', 443))),
    ('subprocess.Popen', ('unapproved', ['unapproved'], OWNED, {})),
    ('os.system', ('unapproved',)),
    ('os.putenv', ('DISCORD_TOKEN', 'synthetic-only')),
]
for _event, _args in _negative_events:
    try:
        sys.audit(_event, *_args)
    except PermissionError:
        pass
    else:
        raise AssertionError('import probe child rejection failed: ' + _event)
sys.audit('open', OWNED + os.sep + 'synthetic.db', 'w', os.O_CREAT | os.O_WRONLY)
sys.audit('open', READ_ROOTS[0] + os.sep + 'discordbot' + os.sep + '__init__.py', 'r', 0)
'''


def reviewed_script(root: Path) -> str:
    """Evaluate only the reviewed literal f-string, never the test module."""
    path = root / 'tests/architecture/test_import_rules.py'
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != TEST_SHA256:
        raise PermissionError('import probe test changed; review required')
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'test_importing_every_v2_module_has_no_runtime_side_effects')
    value = function.body[0].value
    return eval(compile(ast.Expression(value), str(path), 'eval'),
                {'__builtins__': {'str': str}, 'ROOT': root})


def approved_launch(args: tuple[Any, ...]) -> bool:
    """Only the synchronous audit event of this exact prepared launch is admitted."""
    expected = _launch.get()
    if expected is None:
        return False
    executable, argv, cwd, environment = expected
    rendered = subprocess.list2cmdline(argv) if isinstance(args[1], str) else argv
    return (args[0] == executable and args[1] == rendered
            and args[2] == cwd and args[3] == environment)


def install(root: Path) -> None:
    root = root.resolve()
    executable = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if Path(sys.executable).absolute() != executable.absolute():
        raise PermissionError('import probe requires reviewed checkout interpreter')
    original = reviewed_script(root)
    native = subprocess.Popen

    class ImportProbePopen(native):
        def __init__(self, args: Any, *positional: Any, **kwargs: Any) -> None:
            expected = [sys.executable, '-I', '-c', original]
            # Other reviewed callers retain their own runner's admission policy.
            if args != expected:
                super().__init__(args, *positional, **kwargs)
                return
            if (positional or set(kwargs) != {'cwd', 'env', 'text', 'stdout', 'stderr'}
                    or kwargs.get('text') is not True
                    or Path(kwargs.get('cwd', '')).absolute() != root
                    or kwargs.get('stdin') is not None
                    or kwargs.get('stdout') != subprocess.PIPE
                    or kwargs.get('stderr') != subprocess.PIPE):
                raise PermissionError('import probe launch shape changed')
            # Fresh owned home/temp; no cleanup of evidence or other directories.
            owned = Path(tempfile.mkdtemp(prefix='discord-import-probe-'))
            environment = {k: os.environ[k] for k in ('SYSTEMROOT', 'WINDIR') if k in os.environ}
            environment.update(HOME=str(owned), USERPROFILE=str(owned), TEMP=str(owned),
                               TMP=str(owned), PYTHON_DOTENV_DISABLED='1')
            preamble = (f'OWNED = {str(owned)!r}\n'
                        f'READ_ROOTS = {[str(root / "src"), sys.prefix, sys.base_prefix]!r}\n'
                        f'PROTECTED = {[str(root / "data"), str(root / "scratch/phase10") ]!r}\n')
            script = preamble + CHILD_GUARD + '\nexec(' + repr(original) + ", {'__name__': '__main__'})\n"
            command = [sys.executable, '-I', '-B', '-c', script]
            kwargs.update(env=environment, cwd=str(root), executable=sys.executable)
            token = _launch.set((sys.executable, command, str(root), environment))
            try:
                super().__init__(command, **kwargs)
                LAUNCHES.append({'executable': sys.executable, 'flags': ['-I', '-B', '-c'],
                                 'cwd': str(root), 'owned': str(owned),
                                 'environment_keys': sorted(environment),
                                 'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
                                 'child_sha256': hashlib.sha256(script.encode()).hexdigest(),
                                 'child_negative_events': 12})
            finally:
                _launch.reset(token)

    subprocess.Popen = ImportProbePopen
