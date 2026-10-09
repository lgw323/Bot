"""Both required lanes cover the whole operations inventory without import leaks."""
from contextlib import nullcontext
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters.admission import (
    OPERATIONS_TESTS, REQUIRED_SOURCE_TESTS, SOURCE_HISTORY_TESTS,
    SOURCE_MEASUREMENT_TESTS, installed_operations_args,
)
from discordbot.operations.adapters.deployment import LocalDeployment
from .test_production_tools import tool


EXPECTED_SOURCE = (
    "tests/integration/operations/test_a9_local_harness.py",
    "tests/integration/operations/test_a9_candidate_packet.py",
)


def test_selection_excludes_exactly_two_source_modules():
    assert SOURCE_MEASUREMENT_TESTS == EXPECTED_SOURCE
    assert SOURCE_HISTORY_TESTS == ("tests/integration/source_review/test_a9_bt1_history.py",)
    assert REQUIRED_SOURCE_TESTS == (*EXPECTED_SOURCE, *SOURCE_HISTORY_TESTS)
    assert installed_operations_args() == [
        OPERATIONS_TESTS, f"--confcutdir={OPERATIONS_TESTS}",
        *(f"--ignore={path}" for path in EXPECTED_SOURCE),
    ]
    root = Path(__file__).resolve().parents[3]
    modules = {p.relative_to(root).as_posix()
               for p in (root / OPERATIONS_TESTS).rglob("test_*.py")}
    source = set(SOURCE_MEASUREMENT_TESTS)
    installed = modules - source
    assert source <= modules
    assert installed and installed.isdisjoint(source)
    assert installed | source == modules


def test_local_deployment_keeps_command_controls(tmp_path):
    calls = []
    store = SimpleNamespace(path=lambda identity: tmp_path / identity)
    runner = SimpleNamespace(run=lambda args, cwd, timeout: calls.append((args, cwd, timeout)))
    deployment = LocalDeployment(None, SimpleNamespace(store=store, runner=runner), None, None)
    deployment.test(SimpleNamespace(identity="synthetic"))
    release = tmp_path / "synthetic"
    python = release / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert calls == [([str(python), "-m", "pytest", "-p", "no:cacheprovider",
        *installed_operations_args(), "-q", "-W", "error::RuntimeWarning", "-W",
        "error::pytest.PytestUnraisableExceptionWarning"], release / "app", 300)]


def test_candidate_verifier_keeps_command_controls(tmp_path, monkeypatch):
    from discordbot.operations.adapters import build, filesystem
    calls = []
    records = []
    store = SimpleNamespace(current=lambda: "old", path=lambda identity: tmp_path / identity,
        validate=lambda identity: {"dependency_hash": "synthetic", "schema_min": 5, "schema_max": 5})
    runner = SimpleNamespace(run=lambda args, cwd, timeout: calls.append((args, cwd, timeout)))
    builder = SimpleNamespace(build=lambda commit: "synthetic", store=store, runner=runner,
        publish=lambda identity: None)
    monkeypatch.setattr(build, "Builder", lambda *args, **kwargs: builder)
    monkeypatch.setattr(build, "CommandRunner", lambda: runner)
    monkeypatch.setattr(filesystem, "ReleaseStore", lambda root: store)
    monkeypatch.setattr(filesystem, "ExclusiveLock",
        lambda path: SimpleNamespace(acquire=lambda: nullcontext()))
    verifier = tool("production/verify_candidate.py")
    monkeypatch.setattr(verifier, "record", lambda path, value: records.append(value))
    # build_worker inserts a source path; restore it when this synthetic call ends.
    monkeypatch.setattr(verifier.sys, "path", list(verifier.sys.path))
    verifier.build_worker(tmp_path, "a" * 40)
    release = tmp_path / "synthetic"
    assert calls == [([str(release / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider",
        *installed_operations_args(), "-q", "-W", "error::RuntimeWarning", "-W",
        "error::pytest.PytestUnraisableExceptionWarning", "-o", "xfail_strict=true"], release / "app", 300)]
    assert records[0]["activated"] is False


def test_collection_partition_precedes_import_and_keeps_future_tests(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    operations = tmp_path / OPERATIONS_TESTS
    operations.mkdir(parents=True)
    # Explicit source collection must import these; installed collection must not.
    for relative in REQUIRED_SOURCE_TESTS:
        # The full source gate may already have collected the real module names.
        monkeypatch.delitem(sys.modules, relative[:-3].replace("/", "."), raising=False)
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(
            "import os\n"
            "if os.environ.get('SYNTHETIC_INSTALLED_LANE'):\n"
            "    raise AssertionError('source tool imported by installed lane')\n"
            "def test_source_required(): pass\n", encoding="utf-8")
    future = operations / "future"
    future.mkdir()
    # Same basename in a different directory and similar new names are admitted.
    for path in (future / "test_a9_local_harness.py", operations / "test_a9_future_tool.py",
                 operations / "test_runtime_future.py"):
        path.write_text("def test_installed_required(): pass\n", encoding="utf-8")

    def collect(selection):
        nodeids = []
        class Collected:
            def pytest_collection_finish(self, session):
                nodeids.extend(item.nodeid for item in session.items)
        result = pytest.main(["-c", str(config), "--collect-only", "-q",
            "-p", "no:cacheprovider", "--import-mode=importlib", *selection], plugins=[Collected()])
        assert result == pytest.ExitCode.OK
        return set(nodeids)

    monkeypatch.setenv("SYNTHETIC_INSTALLED_LANE", "1")
    installed = collect(installed_operations_args())
    monkeypatch.delenv("SYNTHETIC_INSTALLED_LANE")
    source = collect([*REQUIRED_SOURCE_TESTS, "--confcutdir=tests/integration"])
    all_operations = collect([OPERATIONS_TESTS, *SOURCE_HISTORY_TESTS,
                              "--confcutdir=tests/integration"])
    assert installed.isdisjoint(source)
    assert installed | source == all_operations
    assert len(source) == 3 and len(installed) == 3  # This fixed synthetic fixture only.
