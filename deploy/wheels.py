"""Stdlib-only offline lock materialization for first staging bootstrap."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("pins", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from discordbot.operations.adapters.build import seal_wheels, verify_wheels
    from discordbot.operations.adapters.filesystem import atomic_bytes
    seal_wheels(args.wheelhouse.absolute(), args.pins.absolute())
    text, _ = verify_wheels(args.wheelhouse.absolute(), args.pins.absolute())
    atomic_bytes(args.wheelhouse / "requirements.lock", text.encode())


if __name__ == "__main__":
    main()
