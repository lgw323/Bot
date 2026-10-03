"""A8 independent retention contract probe: synthetic temporary releases only."""
import os
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters.deployment import LocalDeployment
from discordbot.operations.adapters.retention import cleanup_releases
from discordbot.operations.ports.deployment import Release
from tests.integration.operations.test_filesystem import release, symlinks_on_windows


@pytest.mark.parametrize("incomplete_count", [0, 4], ids=["published-only-control", "newer-incomplete"])
@pytest.mark.parametrize("entrypoint", ["cleanup", "post-deploy"])
def test_four_newest_published_survive_incomplete_candidates(tmp_path, monkeypatch, incomplete_count, entrypoint):
    now = 2_000_000_000.0
    monkeypatch.setattr("time.time", lambda: now)
    store = release(tmp_path, "active")
    published = ["published-" + str(i) for i in range(4)]
    for index, identity in enumerate(published):
        release(tmp_path, identity)
        # All published releases exceed seven days: the four-release floor,
        # not age protection, must preserve these independently usable releases.
        old = now - (10 + index) * 86400
        os.utime(store.path(identity), (old, old))
    store.activate("active")
    # Active is protected explicitly and older than all four other publications.
    os.utime(store.path("active"), (now - 20 * 86400, now - 20 * 86400))
    state = tmp_path / "state"
    state.mkdir()
    for index in range(incomplete_count):
        candidate = store.path("incomplete-" + str(index))
        candidate.mkdir()
        (candidate / ".building").write_text("synthetic interrupted build")
        os.utime(candidate, (now - index * 60, now - index * 60))
    for identity in published:
        store.validate(identity)

    if entrypoint == "cleanup":
        cleanup_releases(store, state, now=now)
    else:
        # Exercise the real post-deploy retention method without any build,
        # service invocation, credentials, database or network adapter.
        port = LocalDeployment(SimpleNamespace(state=state), SimpleNamespace(store=store), None, None)
        port.retain(Release("active"), None)

    assert store.current() == "active"
    for index in range(incomplete_count):
        assert store.path("incomplete-" + str(index)).exists()
    missing = [identity for identity in published if not store.path(identity).exists()]
    assert not missing, f"Four newest published releases were deleted: {missing}"
