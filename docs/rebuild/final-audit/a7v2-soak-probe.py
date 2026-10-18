"""Bounded 100-round synthetic Phase 7 soak; stop on first failed round or cutoff."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/rebuild/final-audit"
TARGETS = [
    "docs/rebuild/final-audit/a7-paused-disconnect-probe.py",
    "docs/rebuild/final-audit/a7v1-retry-exhaustion-probe.py",
    "docs/rebuild/final-audit/a7v2-contract-probe.py",
    "tests/integration/music/test_actor.py::test_cf01_cf02_cf03_skip_retry_late_callback",
    "tests/integration/music/test_actor.py::test_cf01_skip_during_preparation",
    "tests/integration/music/test_actor.py::test_cf04_autoplay_manual_enqueue_invalidates_late_result",
    "tests/integration/music/test_actor.py::test_cf05_tts_completion_and_skip_never_resurrect_track",
    "tests/integration/music/test_resources.py::test_cf06_snapshot_atomic_revision_checksum_ack_partial_guild",
    "tests/integration/music/test_resources.py::test_cf15_cache_same_key_pins_eviction_corruption_and_ttl",
    "tests/integration/music/test_resources.py::test_cf15_cf20_local_process_reap[cancel]",
    "tests/integration/music/test_lifecycle.py::test_cf02_cf20_ffmpeg_adapter_local_child_ownership[immediate_stop]",
    "tests/integration/music/test_lifecycle.py::test_cf16_ready_storm_dashboard_coalesce_and_cf20_shutdown",
]
receipt = {"scope": "synthetic Windows; no live providers/voice/Pi", "targets": TARGETS,
           "requested_rounds": 100, "rounds": [], "status": "RUNNING", "owned_child": None}
path = OUT / "a7v2-soak-results.json"


def checkpoint():
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHON_DOTENV_DISABLED="1")
for round_number in range(1, 101):
    # User's 03:35 UTC long-test launch cutoff; reserve two additional minutes.
    if datetime.now(timezone.utc) >= datetime(2026, 10, 3, 3, 33, tzinfo=timezone.utc):
        receipt["status"] = "PARTIAL_TIME_BOUNDARY"
        break
    xml = OUT / "a7v2-soak-last-results.xml"
    start = time.monotonic()
    child = subprocess.Popen([sys.executable, "-m", "pytest", "-c", "pyproject.toml",
        *TARGETS, "-q", "--tb=short", "-W", "error::RuntimeWarning",
        "-W", "error::pytest.PytestUnraisableExceptionWarning", "--junitxml=" + str(xml)],
        cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    receipt["owned_child"] = child.pid
    checkpoint()
    try:
        output, _ = child.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=True)
        else:
            child.kill()
        output, _ = child.communicate(timeout=5)
        receipt["status"] = "BLOCKED_ROUND_TIMEOUT"
    receipt["owned_child"] = None
    result = {"round": round_number, "exit": child.returncode,
              "seconds": round(time.monotonic() - start, 3)}
    if xml.exists():
        cases = ET.parse(xml).findall(".//testcase")
        result["cases"] = len(cases)
        result["failed"] = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
        result["skipped"] = sum(c.find("skipped") is not None for c in cases)
    receipt["rounds"].append(result)
    if child.returncode:
        receipt["status"] = "FAIL" if receipt["status"] == "RUNNING" else receipt["status"]
        receipt["failure_output"] = output
        checkpoint()
        print(output, flush=True)
        break
    checkpoint()
    if round_number % 10 == 0:
        print("Completed", round_number, "rounds;", result["cases"], "cases per round", flush=True)
else:
    receipt["status"] = "PASS"
checkpoint()
print(receipt["status"], len(receipt["rounds"]), "rounds", flush=True)
raise SystemExit(0 if receipt["status"] == "PASS" else 1)
