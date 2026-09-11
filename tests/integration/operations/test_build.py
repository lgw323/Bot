import os
import zipfile
from pathlib import Path

import pytest

from discordbot.operations.adapters.build import Builder, seal_wheels, verify_wheels
from discordbot.operations.adapters.filesystem import ReleaseStore
from discordbot.platform.errors import DataIntegrityError


class Runner:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def run(self, args, cwd, timeout):
        self.calls.append(args)
        if self.fail:
            raise OSError("injected")
        if "venv" in args:
            venv = Path(args[-1])
            (venv / ("Scripts" if os.name == "nt" else "bin")).mkdir(parents=True)
            (venv / "pyvenv.cfg").write_text("synthetic immutable environment")
            (venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).write_text("synthetic interpreter")


@pytest.fixture
def builder(tmp_path):
    source, root, wheels = (tmp_path / name for name in ("source", "root", "wheels"))
    for path in (source, root / "releases", wheels): path.mkdir(parents=True)
    for name in ("src", "tests", "deploy"): (source / name).mkdir()
    (source / "src" / "app.py").write_text("pass")
    pins = source / "deploy" / "dependencies.pins"
    pins.write_text("example==1.0\n")
    with zipfile.ZipFile(wheels / "example-1.0-py3-none-any.whl", "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", "Name: example\nVersion: 1.0\n")
    seal_wheels(wheels, pins)
    return Builder(ReleaseStore(root), Runner(), source, wheels)


def test_build_pins_per_release_venv_before_publish(builder):
    identity = builder.build("a" * 40)
    path = builder.store.path(identity)
    assert (path / ".building").exists()
    with pytest.raises(FileNotFoundError): builder.store.validate(identity)
    pip = next(args for args in builder.runner.calls if "install" in args)
    assert {"--no-index", "--no-deps", "--require-hashes", "--only-binary=:all:"} <= set(pip)
    assert str(path / ".venv") in builder.runner.calls[0]
    builder.publish(identity)
    assert builder.store.validate(identity)["commit"] == "a" * 40
    assert builder.build("a" * 40) == identity


def test_failed_build_does_not_publish_and_cleans_candidate(builder):
    builder.runner.fail = True
    with pytest.raises(OSError): builder.build("a" * 40)
    assert not list(builder.store.releases.iterdir())


def test_tampered_wheel_rejected_before_environment_creation(builder):
    next(builder.wheels.glob("*.whl")).write_bytes(b"tampered")
    with pytest.raises(DataIntegrityError): builder.build("a" * 40)
    assert not builder.runner.calls


def test_missing_transitive_wheel_is_not_resolved_online(builder):
    pins = builder.source / "deploy" / "dependencies.pins"
    pins.write_text("example==1.0\nmissing==2.0\n")
    with pytest.raises(DataIntegrityError): seal_wheels(builder.wheels, pins)
    with pytest.raises(DataIntegrityError): verify_wheels(builder.wheels, pins)


def test_candidate_changed_after_tests_cannot_publish(builder):
    identity = builder.build("a" * 40)
    (builder.store.path(identity) / "app" / "src" / "app.py").write_text("changed")
    with pytest.raises(DataIntegrityError): builder.publish(identity)


def test_source_sensitive_artifacts_are_rejected(builder):
    (builder.source / "src" / ".env").write_text("synthetic forbidden")
    with pytest.raises(DataIntegrityError): builder.build("a" * 40)
    assert not list(builder.store.releases.iterdir())


def test_emergency_update_rejects_unrelated_dependency_change(builder, monkeypatch):
    previous = builder.store.path("previous") / "app" / "deploy"
    previous.mkdir(parents=True)
    (previous / "dependencies.pins").write_text("example==0.9\n")
    monkeypatch.setattr(builder.store, "current", lambda: "previous")
    builder.provider_only = True
    with pytest.raises(DataIntegrityError, match="only the yt-dlp"):
        builder.build("a" * 40)
    assert not builder.runner.calls
