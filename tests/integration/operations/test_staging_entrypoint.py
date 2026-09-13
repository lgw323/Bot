"""Staging tooling regression without sudo, host paths, or network access."""

import os
from pathlib import Path
import subprocess
import sys


def test_isolated_initial_builder_disables_bytecode_before_source_access(tmp_path):
    script = Path(__file__).resolve().parents[3] / "deploy/staging/build_initial.py"
    code = """
import runpy, sys
assert not sys.dont_write_bytecode  # -I ignores PYTHONDONTWRITEBYTECODE.
namespace = runpy.run_path(sys.argv[1])
class ReachedSource(Exception): pass
def source_path(*args):
    assert sys.dont_write_bytecode, 'initial import would contaminate source export'
    raise ReachedSource
main = namespace['main']
main.__globals__['Path'] = source_path
try:
    main()
except ReachedSource:
    pass
else:
    raise AssertionError('source guard not exercised')
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(script)], cwd=tmp_path,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
