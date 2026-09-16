"""Operator-only hidden input. Never reads dotenv, accepts secrets as arguments, or overwrites files."""

import argparse
import base64
import getpass
import os
from pathlib import Path


NAMES = {"discord_token", "gemini_key", "db_key", "control_key", "capability_key"}


def validate(name: str, value: str) -> None:
    if name not in NAMES or not value or not value.isascii() or len(value) > 4096 or any(char.isspace() for char in value):
        raise ValueError("Invalid secret format")
    lowered = value.lower()
    if any(marker in lowered for marker in ("censored", "replace_me", "your_", "changeme", "placeholder")):
        raise ValueError("Template placeholder refused")
    if name == "db_key":
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        if len(raw) != 32 or len(value) != 44:
            raise ValueError("Expected a 32-byte URL-safe Base64 key")
    if name in {"control_key", "capability_key"} and len(value) < 32:
        raise ValueError("At least 32 characters required")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--name", choices=sorted(NAMES), required=True)
    args = parser.parse_args()
    root = args.directory.absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise SystemExit("Linked directory refused")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = root / args.name
    if destination.exists() or destination.is_symlink():
        raise SystemExit("Existing secret preserved; choose a new candidate directory")
    value = getpass.getpass(f"Enter {args.name} (hidden; never paste into chat): ").strip()
    confirmation = getpass.getpass("Confirm value (hidden): ").strip()
    if value != confirmation:
        raise SystemExit("Values differ; no file written")
    try:
        validate(args.name, value)
    except ValueError:
        raise SystemExit("Invalid format or placeholder; no file written") from None
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print("Secret saved privately. Value not displayed. No service was started.")


if __name__ == "__main__":
    main()
