"""Independent negative controls; replace only the actor module in this process.

Run with m1 or m2. Historical test/probe files and checkout source stay unchanged.
"""
from pathlib import Path
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import conftest  # noqa: E402,F401 -- install credential guard before application imports
import discordbot.music.application.actor as actor_module  # noqa: E402
import pytest  # noqa: E402

mode = sys.argv[1]
baseline, targets = {
    "m1": ("3092f49ce82ac44232535b39b779718a5bd0f414", [
        "docs/rebuild/final-audit/a7-paused-disconnect-probe.py"]),
    "m2": ("22736424a32991d480ca3518085e948292eb40db", [
        "docs/rebuild/final-audit/a7v1-retry-exhaustion-probe.py",
        "tests/integration/music/test_pause_session_lifetime.py"]),
}[mode]
source = subprocess.check_output([
    "git", "show", baseline + ":src/discordbot/music/application/actor.py"], cwd=ROOT)
print("Baseline:", baseline, "actor SHA-256:", hashlib.sha256(source).hexdigest())
exec(compile(source, str(actor_module.__file__), "exec"), actor_module.__dict__)
raise SystemExit(pytest.main([
    "-c", str(ROOT / "pyproject.toml"), *[str(ROOT / target) for target in targets],
    "-q", "--tb=short", "-W", "error::RuntimeWarning",
    "-W", "error::pytest.PytestUnraisableExceptionWarning",
    "--junitxml=" + str(ROOT / f"docs/rebuild/final-audit/a7v2-baseline-{mode}-results.xml"),
]))
