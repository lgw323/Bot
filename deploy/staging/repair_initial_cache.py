"""Repair only the known failed PHASE 9 source-bytecode initialization attempt."""

import hashlib
import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo required")
    root = Path("/var/lib/discordbot")
    source = root / "staging-source"
    if (not (root / "STAGING_SYNTHETIC_ONLY").is_file() or
            (root / "data/bot_database.db").exists() or
            Path("/opt/discordbot/current").exists() or
            list(Path("/opt/discordbot/releases").iterdir())):
        raise SystemExit("Repair only applies before the first synthetic DB/release")
    target = root / "staging-tools/build_initial.py"
    expected = "03b382a42f01340ade7c21b95d357bd254d24d68c4c4059b5f1f1f0bf1fbfd29"
    if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise SystemExit("Unexpected initial helper; no replacement")
    bytecode = list(source.rglob("*.pyc"))
    for path in bytecode:
        if path.is_symlink() or path.parent.name != "__pycache__" or not path.resolve().is_relative_to(source.resolve()):
            raise SystemExit("Unexpected source cache path")
    for path in bytecode:
        path.unlink()
    target.write_bytes(Path("/home/os/discordbot-phase9/build_initial.py").read_bytes())
    target.chmod(0o644)
    print(f"Removed {len(bytecode)} generated source bytecode files; original data untouched", flush=True)
    runpy.run_path("/home/os/discordbot-phase9/activate_local.py", run_name="__main__")
