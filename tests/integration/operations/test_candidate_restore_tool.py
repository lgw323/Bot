from types import SimpleNamespace

import pytest

from .test_production_tools import tool


def test_candidate_restore_requires_reviewed_schema_and_aggregates():
    restore = tool("production/restore_candidate.py")
    report = SimpleNamespace(migration_version=5, counts=tuple(restore.COUNTS.items()))
    restore.report_valid(report)
    report.migration_version = 4
    with pytest.raises(ValueError):
        restore.report_valid(report)
    report.migration_version = 5
    report.counts = tuple(dict(restore.COUNTS, users=0).items())
    with pytest.raises(ValueError):
        restore.report_valid(report)
