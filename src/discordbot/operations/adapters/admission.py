"""Approved installed-app selection; source review still requires every test."""

OPERATIONS_TESTS = "tests/integration/operations"
# Repository measurement tools need scripts, audit documents and Git provenance.
# These exact modules remain mandatory in the full source-review regression lane.
SOURCE_MEASUREMENT_TESTS = (
    f"{OPERATIONS_TESTS}/test_a9_local_harness.py",
    f"{OPERATIONS_TESTS}/test_a9_candidate_packet.py",
)
SOURCE_HISTORY_TESTS = ("tests/integration/source_review/test_a9_bt1_history.py",)
# History proofs live outside operations; this does not add installed exclusions.
REQUIRED_SOURCE_TESTS = (*SOURCE_MEASUREMENT_TESTS, *SOURCE_HISTORY_TESTS)


def installed_operations_args() -> list[str]:
    """Exclude only approved source modules before pytest imports/collects them."""
    return [OPERATIONS_TESTS, f"--confcutdir={OPERATIONS_TESTS}",
            *(f"--ignore={path}" for path in SOURCE_MEASUREMENT_TESTS)]
