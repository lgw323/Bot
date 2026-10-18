"""C13 inventories payload files even when their names match root metadata."""

import os
from pathlib import Path

import pytest

from discordbot.operations.adapters.build import Builder
from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
from discordbot.platform.errors import DataIntegrityError
from tests.integration.operations.test_build import Runner, builder
from tests.integration.operations.test_filesystem import release, symlinks_on_windows


@pytest.mark.parametrize("relative", [
    "app/settings.json", "app/manifest.json", "app/src/package/manifest.json",
    "app/manifest.json/manifest.json", "app/src/Manifest.json",
    ".venv/Lib/site-packages/package/manifest.json",
    ".venv/lib/python3.12/site-packages/package/manifest.json",
    ".venv/lib64/python3.12/site-packages/package/manifest.json",
    "candidate.json", "app/candidate.json", ".building", "app/.building",
])
@pytest.mark.parametrize("operation", ["validate", "activate", "current"])
def test_unlisted_payload_rejected_at_every_release_read_boundary(
    tmp_path: Path, relative: str, operation: str,
) -> None:
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("new" if operation == "current" else "old")
    pointer = tmp_path / "current"
    pointer_before = pointer.read_bytes() if os.name == "nt" else pointer.readlink()
    extra = store.path("new") / relative
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text('{"synthetic":true}', encoding="utf-8")
    with pytest.raises(DataIntegrityError, match="unmanifested"):
        if operation == "current":
            store.current()
        else:
            getattr(store, operation)("new")
    pointer_after = pointer.read_bytes() if os.name == "nt" else pointer.readlink()
    assert pointer_after == pointer_before
    if operation != "current":
        assert store.current() == "old"
    assert not list(tmp_path.glob(".current-*"))


@pytest.mark.parametrize("layout", [
    "app/src/package", "app/tests/fixtures", "app/deploy/assets",
    ".venv/Lib/site-packages/package", ".venv/lib/python3.12/site-packages/package",
    ".venv/lib64/python3.12/site-packages/package",
])
@pytest.mark.parametrize("name", ["manifest.json", "candidate.json", ".building"])
def test_builder_publishes_and_reuses_inventoried_nested_metadata_names(
    builder: Builder, layout: str, name: str,
) -> None:
    relative = layout + "/" + name
    content = b'{"synthetic_payload":true}'
    if layout.startswith("app/"):
        source = builder.source / relative.removeprefix("app/")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
    else:
        class PayloadRunner(Runner):
            def run(self, args: list[str], cwd: Path, timeout: float) -> None:
                super().run(args, cwd, timeout)
                if "check" in args:
                    target = cwd / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
        builder.runner = PayloadRunner()
    identity = builder.build("a" * 40)
    path = builder.store.path(identity)
    candidate = read_json(path / "candidate.json")
    assert candidate["files"][relative] == digest(path / relative)
    assert {"manifest.json", "candidate.json", ".building"}.isdisjoint(candidate["files"])
    builder.publish(identity)
    manifest = builder.store.validate(identity)
    assert manifest == candidate
    assert (path / relative).read_bytes() == content
    assert not (path / "candidate.json").exists()
    assert not (path / ".building").exists()
    builder.store.activate(identity)
    assert builder.store.current() == identity
    calls = len(builder.runner.calls)
    assert builder.build("a" * 40) == identity
    builder.publish(identity)
    assert len(builder.runner.calls) == calls


@pytest.mark.parametrize("relative", ["app/manifest.json", ".venv/Lib/site-packages/package/manifest.json"])
@pytest.mark.parametrize("mutation", ["change", "remove"])
def test_listed_nested_manifest_integrity_still_guards_activation(
    tmp_path: Path, relative: str, mutation: str,
) -> None:
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    path = store.path("new")
    metadata = read_json(path / "manifest.json")
    payload = path / relative
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("synthetic payload", encoding="utf-8")
    metadata["files"][relative] = digest(payload)
    atomic_json(path / "manifest.json", metadata)
    assert store.validate("new") == metadata
    store.activate("old")
    if mutation == "change":
        payload.write_text("changed payload", encoding="utf-8")
    else:
        payload.unlink()
    with pytest.raises((DataIntegrityError, FileNotFoundError)):
        store.activate("new")
    assert store.current() == "old"


def test_manifest_named_directory_and_empty_directories_remain_supported(tmp_path: Path) -> None:
    store = release(tmp_path, "new")
    (store.path("new") / "app" / "manifest.json").mkdir()
    store.activate("new")
    assert store.current() == "new"
