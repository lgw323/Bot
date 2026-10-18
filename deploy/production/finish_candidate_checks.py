"""One interactive-sudo entrypoint; no shell command chaining or secret arguments."""

import os
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo required")
    root = Path("/home/os/discordbot-phase10")
    commands = ([sys.executable, "-I", str(root / "restore_candidate.py"),
                 "--release", "r-672694d3f0c5418e-d026a47ed4f4b38a"],
                [sys.executable, "-I", str(root / "inspect_observation.py")])
    for command in commands:
        result = subprocess.run(command, timeout=450)
        if result.returncode:
            raise SystemExit(result.returncode)
