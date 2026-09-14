"""Fail-closed diagnosis of the explicitly synthetic initial staging build."""

import json
import os
import subprocess
from pathlib import Path


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo required")
    root = Path("/var/lib/discordbot")
    source = root / "staging-source"
    result = {
        "synthetic_marker": (root / "STAGING_SYNTHETIC_ONLY").is_file(),
        "source_bytecode_count": len(list(source.rglob("*.pyc"))),
        "synthetic_database_exists": (root / "data/bot_database.db").exists(),
        "current_exists": Path("/opt/discordbot/current").is_symlink(),
        "candidates": [{"id": p.name, "building": (p / ".building").exists(),
                        "manifest": (p / "manifest.json").exists()}
                       for p in Path("/opt/discordbot/releases").iterdir()],
    }
    # Explicit fail-closed retry only for diagnosis when no DB/current/candidate
    # exists. All possible subprocess output here is from synthetic code paths.
    if (result["synthetic_marker"] and not result["synthetic_database_exists"]
            and not result["current_exists"] and not result["candidates"]):
        child = subprocess.run(["runuser", "-u", "discordbot-deploy", "--",
                                "/var/lib/discordbot/bootstrap/bin/python", "-I",
                                str(root / "staging-tools/build_initial.py")], capture_output=True,
                               text=True, timeout=900)
        result["returncode"] = child.returncode
        result["diagnostic"] = child.stderr[-5000:]
    output = Path("/home/os/discordbot-phase9/build-diagnostic.json")
    output.write_text(json.dumps(result, indent=2))
    output.chmod(0o644)
    print(json.dumps(result), flush=True)
