"""Seven-day compatibility protection is independent of release count ceilings."""

import time
from pathlib import Path

from discordbot.operations.adapters.filesystem import ReleaseStore, read_json


def cleanup_releases(store: ReleaseStore, state: Path, *, now: float | None = None) -> int:
    now = time.time() if now is None else now
    protected = {store.current()}
    for filename in ("rollback.json", "activation.json"):
        path = state / filename
        if path.exists():
            value = read_json(path)
            protected.update(value.get(key) for key in ("previous", "current", "target"))
    releases = sorted((p for p in store.releases.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    # Publication completes only after the manifest is written and .building
    # is removed. In-progress candidates cannot consume the publication floor.
    published = [p for p in releases if (p / "manifest.json").is_file() and not (p / ".building").exists()]
    protected.update(p.name for p in published[:4])
    published_names = {p.name for p in published}
    reclaimed = 0
    for path in releases:
        age = now - path.stat().st_mtime
        # Failed/incomplete artifacts are never boot candidates. Published
        # artifacts retain the minimum compatibility window even at count cap.
        minimum = 7 * 86400 if path.name in published_names else 86400
        if path.name not in protected and age >= minimum:
            reclaimed += store.remove(path.name, protected)
    return reclaimed
