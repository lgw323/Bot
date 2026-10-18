import json

from .test_production_tools import tool


def test_finite_observer_records_only_actual_elapsed_time(tmp_path, monkeypatch):
    observer = tool("staging/observe.py")
    (tmp_path / "STAGING_SYNTHETIC_ONLY").touch()
    monkeypatch.setattr(observer, "ROOT", tmp_path)
    monkeypatch.setattr(observer, "systemd", lambda _: {"ActiveState": "inactive"})
    clock = iter((100, 102, 161))
    monkeypatch.setattr(observer.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(observer.time, "sleep", lambda _: None)
    monkeypatch.setattr(observer, "sample", lambda: {"errors": [], "health": {}})
    observer.observe(tmp_path, 60, 30)
    result = json.loads((tmp_path / "summary.json").read_text())
    assert result["observed_seconds"] == 61
    assert result["samples"] == 2 and result["status"] == "complete"
    assert len((tmp_path / "samples.jsonl").read_text().splitlines()) == 2
