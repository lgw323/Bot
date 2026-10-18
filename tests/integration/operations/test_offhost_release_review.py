import json

from .test_production_tools import tool


def test_observation_review_reports_bits_and_errors_without_raw_content(tmp_path):
    module = tool("production/verify-offhost-release.py")
    module.ROOT = tmp_path
    root = tmp_path / "phase10-observation-20260915"
    root.mkdir()
    first = {"time_unix": 1, "errors": [], "throttling": "0x0", "disk_free_bytes": 1000,
             "backups": {"bytes": 100}, "audit": {"bytes": 10}}
    second = dict(first, time_unix=2, errors=["9010:HTTPError", "untrusted-content-do-not-copy"],
                  throttling="0x50000", disk_free_bytes=900, backups={"bytes": 120})
    (root / "samples.jsonl").write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    result = module.observation_details()
    assert result["throttling_numeric_values"] == {"0": 1, "327680": 1}
    assert result["collection_errors"] == {"9010:HTTPError": 1, "other_collection_error": 1}
    assert result["largest_free_space_drops"][0]["free_delta_bytes"] == -100
    assert result["largest_free_space_drops"][0]["backup_bytes_delta"] == 20
    assert "untrusted-content" not in json.dumps(result)
