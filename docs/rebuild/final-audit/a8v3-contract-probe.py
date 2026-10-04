"""Independent C13/C14 boundaries; only synthetic temporary release and DB paths."""
from contextlib import asynccontextmanager
from pathlib import Path
import stat
import time

import pytest

from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
from discordbot.platform.errors import DataIntegrityError
from tests.integration.operations.test_build import builder
from tests.integration.operations.test_filesystem import release, symlinks_on_windows
from tests.integration.operations.test_recovery import backup


@pytest.mark.parametrize("marker_kind", ["file", "directory"])
def test_root_admission_marker_cannot_be_legitimized_by_inventory(tmp_path, marker_kind):
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    path = store.path("new")
    marker = path / ".building"
    if marker_kind == "directory":
        marker.mkdir()
    else:
        marker.write_text("incomplete")
        value = read_json(path / "manifest.json")
        value["files"][".building"] = digest(marker)
        atomic_json(path / "manifest.json", value)
    with pytest.raises(DataIntegrityError, match="incomplete"):
        store.activate("new")
    assert store.current() == "old"


@pytest.mark.parametrize("parent", ["manifest.json", "candidate.json", ".building"])
def test_reserved_parent_directory_payload_is_checksummed_on_reuse(builder, parent):
    payload = builder.source / "src" / parent / "nested" / "manifest.json"
    payload.parent.mkdir(parents=True)
    payload.write_text("reviewed synthetic payload")
    identity = builder.build("a" * 40)
    builder.publish(identity)
    path = builder.store.path(identity)
    relative = f"app/src/{parent}/nested/manifest.json"
    assert builder.store.validate(identity)["files"][relative] == digest(path / relative)
    assert builder.build("a" * 40) == identity
    # The trusted deploy owner can mutate modes; simulate accidental additions.
    parent_path = path / "app" / "src" / parent
    parent_path.chmod(parent_path.stat().st_mode | stat.S_IWUSR)
    extra = path / "app" / "src" / parent / "extra" / "manifest.json"
    extra.parent.mkdir()
    extra.write_text("unreviewed synthetic payload")
    with pytest.raises(DataIntegrityError, match="unmanifested"):
        builder.build("a" * 40)


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_count", [8, 31])
async def test_restore_validation_is_sequential_at_normal_and_admission_edge(
    backup, monkeypatch, prior_count, record_property,
):
    seed = await backup.create("synthetic-release")
    data = (backup.root / (seed + ".enc")).read_bytes()
    metadata = read_json(backup.root / (seed + ".json"))
    identities = [seed]
    for index in range(prior_count - 1):
        identity = f"20000101T000000000000-{index:032x}"
        (backup.root / (identity + ".enc")).write_bytes(data)
        atomic_json(backup.root / (identity + ".json"), dict(metadata, identity=identity))
        identities.append(identity)
    assert len(list(backup.root.iterdir())) == prior_count * 2 + 1
    original = backup._validated_candidate
    visited = []
    active = 0
    peak_plaintext_bytes = 0

    @asynccontextmanager
    async def checked(identity, directory):
        nonlocal active, peak_plaintext_bytes
        assert active == 0 and not list(backup.root.glob(".rehearsal-*"))
        active += 1
        try:
            async with original(identity, directory) as isolated:
                assert len(list(backup.root.glob(".rehearsal-*.db"))) == 1
                peak_plaintext_bytes = max(peak_plaintext_bytes, isolated.stat().st_size)
                assert all((backup.root / (item + ".enc")).exists() for item in identities)
                assert read_json(backup.root / "latest.json")["identity"] == seed
                visited.append(identity)
                yield isolated
            assert not isolated.exists()
        finally:
            active -= 1

    monkeypatch.setattr(backup, "_validated_candidate", checked)
    started = time.monotonic()
    newest = await backup.create("synthetic-release")
    elapsed = time.monotonic() - started
    assert len(visited) == len(set(visited)) == prior_count + 1
    assert visited == sorted(identities + [newest], reverse=True)
    assert len(list(backup.root.glob("*.enc"))) == 8
    assert not list(backup.root.glob(".rehearsal-*")) and active == 0
    record_property("validated_archives", len(visited))
    record_property("encrypted_bytes_per_archive", len(data))
    record_property("peak_completed_private_db_bytes", peak_plaintext_bytes)
    record_property("create_wall_seconds", round(elapsed, 6))
