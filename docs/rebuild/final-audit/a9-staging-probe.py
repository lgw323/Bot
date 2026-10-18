"""A9 independent synthetic observation checks; no host commands or network.

Run with pytest from the repository so its credential guard is installed.
All observation files are temporary fixtures. Completion describes elapsed
collection time and must never be promoted to a clean soak verdict.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load_tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        "a9_" + name, ROOT / "deploy" / "staging" / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("boundary", ["marker_missing", "production_active"])
def test_observer_refuses_unsafe_boundary_before_sampling(tmp_path, monkeypatch, boundary):
    observer = load_tool("observe")
    monkeypatch.setattr(observer, "ROOT", tmp_path)
    if boundary == "production_active":
        (tmp_path / "STAGING_SYNTHETIC_ONLY").touch()
    monkeypatch.setattr(observer, "systemd", lambda _: {
        "ActiveState": "active" if boundary == "production_active" else "inactive"
    })
    monkeypatch.setattr(observer, "sample", lambda: pytest.fail("unsafe sample"))
    with pytest.raises(RuntimeError, match="Synthetic-only boundary changed"):
        observer.observe(tmp_path, 60, 30)
    assert not (tmp_path / "samples.jsonl").exists()
    assert not (tmp_path / "summary.json").exists()


@pytest.mark.parametrize("boundary", ["marker_removed", "production_started"])
def test_observer_rechecks_boundary_and_preserves_partial_evidence(tmp_path, monkeypatch, boundary):
    observer = load_tool("observe")
    marker = tmp_path / "STAGING_SYNTHETIC_ONLY"
    marker.touch()
    monkeypatch.setattr(observer, "ROOT", tmp_path)
    active = [False]
    monkeypatch.setattr(observer, "systemd", lambda _: {
        "ActiveState": "active" if active[0] else "inactive"
    })
    ticks = iter((100.0, 101.0))
    monkeypatch.setattr(observer.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(observer, "sample", lambda: {"errors": ["9010:HTTPError"], "health": {}})

    def transition(_: float) -> None:
        if boundary == "marker_removed":
            marker.unlink()
        else:
            active[0] = True

    monkeypatch.setattr(observer.time, "sleep", transition)
    with pytest.raises(RuntimeError, match="Synthetic-only boundary changed"):
        observer.observe(tmp_path, 60, 30)
    result = json.loads((tmp_path / "summary.json").read_text())
    assert result["status"] == "observing"
    assert result["observed_seconds"] == 1.0
    assert result["samples"] == 1
    assert result["error_counts"] == {"9010:HTTPError": 1}
    assert len((tmp_path / "samples.jsonl").read_text().splitlines()) == 1


def test_elapsed_completion_retains_collection_errors(tmp_path, monkeypatch):
    observer = load_tool("observe")
    (tmp_path / "STAGING_SYNTHETIC_ONLY").touch()
    monkeypatch.setattr(observer, "ROOT", tmp_path)
    monkeypatch.setattr(observer, "systemd", lambda _: {"ActiveState": "inactive"})
    ticks = iter((0.0, 60.0))
    monkeypatch.setattr(observer.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(observer, "sample", lambda: {"errors": ["9010:HTTPError"], "health": {}})
    observer.observe(tmp_path, 60, 30)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["status"] == "complete"
    assert summary["observed_seconds"] == 60.0
    assert summary["error_counts"] == {"9010:HTTPError": 1}
    assert summary["last"]["health"] == {}


def test_aggregate_keeps_health_gaps_failure_growth_and_sampled_limits(tmp_path):
    inspector = load_tool("inspect_observation")
    samples = []
    for index in range(3):
        sample = {
            "time_unix": index * 60.0,
            "errors": ["9010:HTTPError"] if index == 1 else [],
            "health": {},
            "services": {},
            "temperature_c": 50.0,
            "disk_free_bytes": 1000 - index * 100,
            "throttling": "unavailable" if index == 1 else "0",
        }
        for port in ("9010", "9011"):
            if port == "9010" and index == 1:
                continue
            sample["health"][port] = {
                "ready": True,
                "metrics": {
                    'database_probe_total{result="failed"}': 10 + index,
                    "database_last_execution_seconds": 0.001 + index / 100,
                    "backup_rpo_exceeded": 0,
                },
            }
        samples.append(sample)
    (tmp_path / "samples.jsonl").write_text(
        "".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8"
    )
    (tmp_path / "summary.json").write_text(json.dumps({
        "status": "complete", "requested_seconds": 120, "observed_seconds": 120.1,
    }), encoding="utf-8")
    result = inspector.summarize(tmp_path)
    assert result["samples"] == 3 and result["sample_span_seconds"] == 120.0
    assert result["maximum_gap_seconds"] == 60.0
    assert result["samples_with_collection_errors"] == 1
    assert result["health"]["9010"]["missing"] == 1
    assert result["health"]["9010"]["not_ready"] == 0
    failures = result["health"]["9010"]["metrics"]['database_probe_total{result="failed"}']
    assert failures["last"] - failures["first"] == 2
    assert result["health"]["9010"]["metrics"]["backup_age_seconds"] is None
    assert result["throttling_unavailable_samples"] == 1
    assert result["disk_free_bytes"]["last"] - result["disk_free_bytes"]["first"] == -200
    assert result["distinct_backup_timer_triggers"] == 0


def test_absent_observation_is_not_success(tmp_path):
    assert load_tool("inspect_observation").summarize(tmp_path) == {"status": "no_samples"}
