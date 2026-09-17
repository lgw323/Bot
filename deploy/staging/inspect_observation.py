"""Read fixed PHASE 10 synthetic observation files and publish numeric aggregates only."""

import json
import os
from pathlib import Path


def summarize(root: Path) -> dict:
    path = root / "samples.jsonl"
    if not path.is_file():
        return {"status": "no_samples"}
    if path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Observation input limit")
    samples = [json.loads(line) for line in path.read_text().splitlines()]
    if not 1 <= len(samples) <= 10000:
        raise ValueError("Observation count limit")
    summary = json.loads((root / "summary.json").read_text())
    first, last = samples[0], samples[-1]
    result = {"status": summary["status"], "samples": len(samples),
              "requested_seconds": summary["requested_seconds"], "recorded_elapsed_seconds": summary["observed_seconds"],
              "first_unix": first["time_unix"], "last_unix": last["time_unix"],
              "sample_span_seconds": last["time_unix"] - first["time_unix"],
              "maximum_gap_seconds": max((b["time_unix"] - a["time_unix"] for a, b in zip(samples, samples[1:])), default=0),
              "samples_with_collection_errors": sum(bool(s["errors"]) for s in samples),
              "health": {}, "services": {}}
    def bounds(values):
        return {"first": values[0], "last": values[-1], "min": min(values), "max": max(values)} if values else None
    for port in ("9010", "9011"):
        observations = [s["health"][port] for s in samples if port in s["health"]]
        result["health"][port] = {"missing": len(samples) - len(observations),
            "not_ready": sum(not h["ready"] for h in observations), "metrics": {}}
        for key in ("database_probe_total{result=\"failed\"}", "database_recent_failures",
                    "database_last_execution_seconds", "backup_age_seconds", "backup_rpo_exceeded"):
            values = [h["metrics"][key] for h in observations if key in h["metrics"]]
            result["health"][port]["metrics"][key] = bounds(values)
    for unit in ("discordbot-staging-discord.service", "watch-web.service"):
        observations = [s["services"][unit] for s in samples if unit in s["services"]]
        result["services"][unit] = {"missing": len(samples) - len(observations)}
        for key in ("MainPID", "NRestarts"):
            result["services"][unit][key] = bounds([int(s[key]) for s in observations])
        for key in ("VmRSS", "fd_count", "Threads"):
            result["services"][unit][key] = bounds([s["process"][key] for s in observations if key in s["process"]])
    result["temperature_c"] = bounds([s["temperature_c"] for s in samples])
    result["disk_free_bytes"] = bounds([s["disk_free_bytes"] for s in samples])
    result["cache_bytes"] = bounds([s["cache"]["bytes"] for s in samples if "cache" in s])
    result["audit_files"] = bounds([s["audit"]["files"] for s in samples if "audit" in s])
    triggers = {s["services"].get("discordbot-backup.timer", {}).get("LastTriggerUSec", "") for s in samples}
    result["distinct_backup_timer_triggers"] = len(triggers - {""})
    result["throttling_unavailable_samples"] = sum(s["throttling"] == "unavailable" for s in samples)
    return result


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo required for protected observation evidence")
    roots = (Path("/var/lib/discordbot/phase10-observation-20260915"),
             Path("/var/tmp/phase10-observation-20260915-02"))
    result = {root.name: summarize(root) for root in roots}
    path = Path("/home/os/discordbot-phase10/observation-review.json")
    if path.exists() or path.is_symlink():
        raise SystemExit("Existing review preserved")
    with path.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o644)
    print("Synthetic observation aggregates written; no service changed.")
