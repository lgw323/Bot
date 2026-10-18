"""Independent mixed-order/idempotence checks; disposable synthetic releases only."""
import os
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters.deployment import LocalDeployment
from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.operations.adapters.retention import cleanup_releases
from discordbot.operations.ports.deployment import Release
from tests.integration.operations.test_filesystem import release, symlinks_on_windows


@pytest.mark.parametrize("entrypoint", ["cleanup", "post-deploy"])
@pytest.mark.parametrize("active_newest", [False, True])
def test_interleaved_candidates_pins_floor_and_idempotence(tmp_path, monkeypatch, entrypoint, active_newest):
    now, day = 2_000_000_000.0, 86400
    monkeypatch.setattr("time.time", lambda: now)
    store = release(tmp_path, "active")
    store.activate("active")
    os.utime(store.path("active"), (now, now - (8 if active_newest else 40) * day))
    # Creation/name order intentionally disagree with directory age.
    for index in [5, 1, 4, 0, 3, 2]:
        identity = f"release-{5-index}"
        release(tmp_path, identity)
        store.validate(identity)
        os.utime(store.path(identity), (now, now - (10 + index) * day))
        incomplete = store.path(f"unfinished-{index}")
        incomplete.mkdir()
        (incomplete / ".building").touch()
        # Interleave expired and fresh incomplete directories; none consume floor.
        os.utime(incomplete, (now, now - (index if index % 2 else 11 * day)))
    release(tmp_path, "rollback-pin")
    release(tmp_path, "activation-pin")
    for identity in ["rollback-pin", "activation-pin"]:
        os.utime(store.path(identity), (now, now - 50 * day))
    atomic_json(tmp_path / "activation.json", {"target": "activation-pin"})
    atomic_json(tmp_path / "rollback.json", {"previous": "rollback-pin", "protected_until": 0})
    expected = {"active", "rollback-pin", "activation-pin", "unfinished-1", "unfinished-3", "unfinished-5"}
    expected.update(f"release-{5-index}" for index in range(3 if active_newest else 4))
    for _ in range(2):
        if entrypoint == "cleanup":
            cleanup_releases(store, tmp_path, now=now)
        else:
            port = LocalDeployment(SimpleNamespace(state=tmp_path), SimpleNamespace(store=store), None, None)
            port.retain(Release("active"), Release("rollback-pin"))
        assert {path.name for path in store.releases.iterdir()} == expected
        for identity in expected - {"unfinished-1", "unfinished-3", "unfinished-5"}:
            store.validate(identity)
