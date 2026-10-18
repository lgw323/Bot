"""A8-M1: real retention over temporary releases; no deployment or service calls."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters.deployment import LocalDeployment
from discordbot.operations.adapters.filesystem import ReleaseStore, atomic_json, read_json
from discordbot.operations.adapters.retention import cleanup_releases
from discordbot.operations.ports.deployment import Release
from discordbot.platform.errors import DataIntegrityError
from .test_build import builder
from .test_filesystem import release, symlinks_on_windows


NOW = 2_000_000_000.0
DAY = 86400


def age(path: Path, seconds: float) -> None:
    os.utime(path, (NOW - seconds, NOW - seconds))


def candidate(store: ReleaseStore, identity: str, kind: str) -> Path:
    if kind == "manifest-building":
        release(store.root, identity)
    else:
        store.path(identity).mkdir()
    path = store.path(identity)
    if kind in {"building", "manifest-building"}:
        (path / ".building").write_text("interrupted synthetic build")
    if kind == "candidate-only":
        atomic_json(path / "candidate.json", {"release": identity})
    return path


@pytest.fixture(params=["cleanup", "post-deploy"])
def retain(request, monkeypatch):
    monkeypatch.setattr("time.time", lambda: NOW)

    def run(store: ReleaseStore, state: Path, previous: str | None = None) -> None:
        if request.param == "cleanup":
            cleanup_releases(store, state, now=NOW)
        else:
            port = LocalDeployment(SimpleNamespace(state=state), SimpleNamespace(store=store), None, None)
            port.retain(Release(store.current()), Release(previous) if previous else None)

    return request.param, run


@pytest.mark.parametrize("count", [0, 1, 3, 4, 6])
@pytest.mark.parametrize("kind", ["building", "candidate-only", "empty", "manifest-building"])
def test_only_publications_count_toward_four_newest(tmp_path, retain, count, kind):
    store = release(tmp_path, "active")
    store.activate("active")
    age(store.path("active"), 30 * DAY)
    # Names and creation order intentionally disagree with newest-first mtime.
    for index in reversed(range(count)):
        identity = f"published-{index}"
        release(tmp_path, identity)
        store.validate(identity)
        age(store.path(identity), (10 + index) * DAY)
    for index in range(4):
        age(candidate(store, f"incomplete-{index}", kind), index)
    retain[1](store, tmp_path)
    assert store.current() == "active"
    assert {p.name for p in store.releases.iterdir()} == (
        {"active"} | {f"published-{i}" for i in range(min(count, 4))}
        | {f"incomplete-{i}" for i in range(4)}
    )


@pytest.mark.parametrize("kind,grace", [("published", 7 * DAY), ("building", DAY),
                                         ("candidate-only", DAY), ("empty", DAY),
                                         ("manifest-building", DAY)])
@pytest.mark.parametrize("offset,survives", [(-1, True), (0, False), (1, False)])
def test_age_grace_boundary_outside_four_release_floor(tmp_path, retain, kind, grace, offset, survives):
    store = release(tmp_path, "active")
    store.activate("active")
    for index in range(4):
        release(tmp_path, f"newest-{index}")
        age(store.path(f"newest-{index}"), index)
    if kind == "published":
        release(tmp_path, "boundary")
        target = store.path("boundary")
        store.validate("boundary")
    else:
        target = candidate(store, "boundary", kind)
    age(target, grace + offset)
    retain[1](store, tmp_path)
    assert target.exists() is survives
    assert store.current() == "active"


def test_current_counts_in_publication_floor_and_old_intent_pins_are_additive(tmp_path, retain):
    store = release(tmp_path, "active")
    store.activate("active")
    age(store.path("active"), 8 * DAY)
    for index in range(4):
        release(tmp_path, f"published-{index}")
        age(store.path(f"published-{index}"), (10 + index) * DAY)
    pins = {"previous": "pin-previous", "current": "pin-current", "target": "pin-target"}
    for identity in [*pins.values(), "rollback-previous", "rollback-current", "rollback-target"]:
        release(tmp_path, identity)
        age(store.path(identity), 40 * DAY)
    atomic_json(tmp_path / "activation.json", pins)
    rollback = {key: "rollback-" + key for key in pins}
    rollback["protected_until"] = NOW - DAY  # Existing intent protection does not expire silently.
    atomic_json(tmp_path / "rollback.json", rollback)
    retain[1](store, tmp_path, "rollback-previous")
    expected = {"active", "published-0", "published-1", "published-2", *pins.values(), "rollback-previous"}
    if retain[0] == "cleanup":
        expected.update({"rollback-current", "rollback-target"})
        assert read_json(tmp_path / "rollback.json") == rollback
    else:
        assert read_json(tmp_path / "rollback.json") == {
            "current": "active", "previous": "rollback-previous", "protected_until": NOW + 7 * DAY,
        }
    assert {p.name for p in store.releases.iterdir()} == expected
    assert read_json(tmp_path / "activation.json") == pins


def test_invalid_activation_intent_fails_before_deletion(tmp_path, retain):
    store = release(tmp_path, "active")
    store.activate("active")
    stale = candidate(store, "stale", "building")
    age(stale, 20 * DAY)
    (tmp_path / "activation.json").write_text("not json")
    with pytest.raises(DataIntegrityError):
        retain[1](store, tmp_path)
    assert stale.exists()
    assert store.current() == "active"


def test_nested_link_is_rejected_before_removal(tmp_path, retain):
    store = release(tmp_path, "active")
    store.activate("active")
    stale = candidate(store, "stale", "building")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("synthetic protected data")
    (stale / "escape").symlink_to(outside, target_is_directory=True)
    age(stale, 20 * DAY)
    with pytest.raises(DataIntegrityError):
        retain[1](store, tmp_path)
    assert (outside / "keep").read_text() == "synthetic protected data"
    assert stale.exists()


def test_sixteen_directory_admission_cap_preserves_all_protected_releases(builder):
    for index in range(16):
        release(builder.store.root, f"published-{index}")
        age(builder.store.path(f"published-{index}"), index)
    with pytest.raises(DataIntegrityError, match="release capacity reached"):
        builder.build("c" * 40)
    assert not builder.runner.calls
    assert cleanup_releases(builder.store, builder.store.root, now=NOW) == 0
    assert len(list(builder.store.releases.iterdir())) == 16


def test_cleanup_without_current_keeps_four_publications(tmp_path):
    store = ReleaseStore(tmp_path)
    for index in range(5):
        release(tmp_path, f"published-{index}")
        age(store.path(f"published-{index}"), (10 + index) * DAY)
    assert cleanup_releases(store, tmp_path, now=NOW) > 0
    assert store.current() is None
    assert {p.name for p in store.releases.iterdir()} == {f"published-{i}" for i in range(4)}
