"""Synthetic preparation only: no service, application DB or provider access."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import uuid

import pytest

from scripts import a9_local_harness as harness


@pytest.fixture
def config():
    run_id = uuid.uuid4().hex
    return harness.Config(run_id, "fake://a9/" + run_id,
                          Path(tempfile.gettempdir()).resolve() / ("a9-campaign-" + run_id))


class Clock:
    value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def exercise(config, **kwargs):
    clock = Clock()
    return harness.run(config, clock=clock.now, sleep=clock.sleep, **kwargs)


@pytest.mark.parametrize("multiplier", [1, 2])
def test_workload_counts_percentiles_and_cleanup(config, multiplier):
    result = exercise(replace(config, multiplier=multiplier))
    assert result["status"] == "complete"
    assert result["recorded_operations"] == 16 * multiplier
    assert result["missing_operations"] == result["missing_ticks"] == 0
    assert result["max_tick_gap_seconds"] == pytest.approx(.01)
    assert result["late_tick_gaps"] == 0
    assert all(value == {"successful_samples": 4 * multiplier, "p95_seconds": 0,
                         "p99_seconds": 0} for value in result["latency"].values())
    assert result["cleanup_complete"] and not config.temp_root.exists()
    assert result["owned_workers_remaining"] == 0 and result["a9"] == "BLOCKED"
    assert result["output_bytes"] <= config.max_output_bytes


@pytest.mark.parametrize("field,value", [
    ("target_identity", "http://127.0.0.1:9010"), ("target_identity", "fake://a9/other"),
    ("target_identity", ""), ("adapter", "live"), ("scope", "UNAPPROVED"),
    ("temp_root", Path("/var/lib/discordbot")), ("temp_root", Path("data")),
    ("run_id", "../escape"), ("ticks", 0), ("ticks", 33), ("ticks", True),
    ("multiplier", 3), ("max_operations", 257), ("max_output_bytes", 65537),
    ("max_seconds", 86400), ("max_seconds", float("nan")),
    ("interval_seconds", float("inf")), ("fault", "anything"), ("fault_at", 16),
])
def test_unsafe_or_ambiguous_configuration_never_writes(config, field, value):
    with pytest.raises(harness.UnsafeTarget):
        exercise(replace(config, **{field: value}))
    assert not config.temp_root.exists()


def test_existing_root_and_unknown_destination_fields_are_refused(config):
    config.temp_root.mkdir()
    sentinel = config.temp_root / "unowned.txt"
    sentinel.write_text("synthetic sentinel", encoding="utf-8")
    try:
        with pytest.raises(harness.UnsafeTarget):
            exercise(config)
        assert sentinel.read_text(encoding="utf-8") == "synthetic sentinel"
    finally:
        sentinel.unlink()
        config.temp_root.rmdir()
    with pytest.raises(harness.UnsafeTarget):
        harness.config_from_mapping({"temp_root": str(config.temp_root), "service": "anything"})


@pytest.mark.parametrize("fault", ["provider_timeout", "db_busy", "slow_peer", "unexpected"])
def test_faults_count_separately_from_successful_latency(config, fault):
    result = exercise(replace(config, fault=fault))
    classification = "unexpected_fault" if fault == "unexpected" else "expected_" + fault
    assert result["classifications"][classification] == 1
    assert result["latency"]["music"]["successful_samples"] == (0 if fault == "unexpected" else 3)
    assert result["status"] == ("aborted" if fault == "unexpected" else "complete")
    if fault == "unexpected":
        assert result["missing_operations"] == 15
        assert result["latency"]["music"]["p99_seconds"] is None
    assert result["cleanup_complete"]


@pytest.mark.parametrize("field,value,reason", [
    ("max_operations", 3, "operation_budget"),
    ("max_output_bytes", 1, "output_budget"),
    ("max_seconds", .01, "time_budget"),
])
def test_budgets_abort_and_retain_partial_counts(config, field, value, reason):
    result = exercise(replace(config, **{field: value}))
    assert result["status"] == "aborted" and result["reason"] == reason
    assert result["missing_operations"] > 0
    assert result["cleanup_complete"] and not config.temp_root.exists()


def test_free_floor_abort_before_first_sample(config, monkeypatch):
    monkeypatch.setattr(harness.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    result = exercise(config)
    assert result["reason"] == "free_floor" and result["recorded_operations"] == 0
    assert result["missing_ticks"] == 4 and result["cleanup_complete"]
    assert all(value["p95_seconds"] is None for value in result["latency"].values())


def test_operator_abort_after_partial_work(config):
    checks = iter([False] * 3 + [True])
    result = exercise(config, abort_requested=lambda: next(checks))
    assert result["reason"] == "operator_abort" and result["recorded_operations"] == 2
    assert result["cleanup_complete"]


def test_late_ticks_report_gaps(config):
    clock = Clock()
    def late_sleep(seconds):
        clock.value += seconds + .03
    result = harness.run(config, clock=clock.now, sleep=late_sleep)
    assert result["late_tick_gaps"] > 0
    assert result["max_tick_gap_seconds"] == pytest.approx(.04)
    assert result["cleanup_complete"]


@pytest.mark.parametrize("error,reason", [(KeyboardInterrupt, "interrupted"), (OSError, "harness_error")])
def test_interrupt_and_io_error_cleanup(config, error, reason):
    def interrupted():
        raise error("synthetic error must not enter evidence")
    result = exercise(config, abort_requested=interrupted)
    assert result["reason"] == reason and result["cleanup_complete"]
    assert "synthetic error" not in json.dumps(result)


def test_cleanup_failure_is_not_success_or_recursive_deletion(config):
    sentinel = config.temp_root / "unowned.txt"
    def abort():
        sentinel.write_text("synthetic", encoding="utf-8")
        return True
    try:
        result = exercise(config, abort_requested=abort)
        assert result["reason"] == "cleanup_failed" and not result["cleanup_complete"]
        assert sentinel.exists() and not (config.temp_root / "samples.jsonl").exists()
    finally:
        sentinel.unlink()
        config.temp_root.rmdir()


def test_real_clock_brief_smoke(config):
    result = harness.run(replace(config, ticks=2))
    assert result["status"] == "complete" and result["recorded_operations"] == 8
    assert 0 <= result["elapsed_seconds"] < 2 and result["cleanup_complete"]


def test_review_example_is_unapproved_and_not_executable():
    path = Path(__file__).resolve().parents[3] / "docs/rebuild/final-audit/a9-local-example.UNAPPROVED.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    assert example["approval"] == "UNAPPROVED"
    with pytest.raises(harness.UnsafeTarget):
        harness.config_from_mapping(example)


def test_percentiles_have_known_nearest_rank_and_empty_semantics():
    values = list(range(1, 101))
    assert harness._percentile(values, .95) == 95
    assert harness._percentile(values, .99) == 99
    assert harness._percentile([], .95) is None


@pytest.mark.parametrize("link_method", ["is_symlink", "is_junction"])
def test_link_targets_refused_before_write(config, monkeypatch, link_method):
    original = getattr(Path, link_method)
    monkeypatch.setattr(Path, link_method,
                        lambda path: path == config.temp_root or original(path))
    with pytest.raises(harness.UnsafeTarget):
        exercise(config)
    assert not config.temp_root.exists()


def test_traversal_and_wrong_parent_are_refused(config):
    for root in (config.temp_root.parent / ".." / config.temp_root.parent.name / config.temp_root.name,
                 config.temp_root.parent / "nested" / config.temp_root.name):
        with pytest.raises(harness.UnsafeTarget):
            exercise(replace(config, temp_root=root))


def test_identity_replacement_aborts_and_cleanup_does_not_adopt_new_root(config, monkeypatch):
    # Windows locks directories containing open files. Model the changed inode
    # instead of requiring a POSIX rename of that open directory.
    original = Path.stat
    changed_identity = False
    def stat(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path == config.temp_root and changed_identity:
            return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + 1,
                                   st_mode=value.st_mode,
                                   st_file_attributes=getattr(value, "st_file_attributes", 0))
        return value
    def changed():
        nonlocal changed_identity
        changed_identity = True
        return False
    monkeypatch.setattr(Path, "stat", stat)
    try:
        result = exercise(config, abort_requested=changed)
        assert result["reason"] == "cleanup_refused"
        assert not result["cleanup_complete"] and result["recorded_operations"] == 0
        assert config.temp_root.exists()
    finally:
        (config.temp_root / "samples.jsonl").unlink()
        config.temp_root.rmdir()
