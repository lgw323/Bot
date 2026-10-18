"""Pin the import root to this immutable release before loading application code."""

import sys
from pathlib import Path


def main() -> int:
    release = Path(__file__).resolve().parents[2]
    if Path(sys.executable).resolve().parents[2] != release:
        raise SystemExit("interpreter and release identity differ")
    sys.path.insert(0, str(release / "app" / "src"))
    service, *arguments = sys.argv[1:]
    if service == "operations":
        from discordbot.operations.adapters.cli import main as entrypoint
        return entrypoint(arguments)
    from discordbot.composition.main import main as entrypoint
    return entrypoint([service, "--release", str(release), *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
