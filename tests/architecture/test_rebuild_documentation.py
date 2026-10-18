from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
REBUILD_ROOT = ROOT / "docs" / "rebuild"
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)

BASELINE_DOCUMENTS = {
    "README.md",
    "00-executive-summary.md",
    "01-current-system-overview.md",
    "02-repository-map.md",
    "03-feature-inventory.md",
    "04-command-event-inventory.md",
    "05-runtime-flow.md",
    "06-data-model.md",
    "07-external-dependencies.md",
    "08-business-rules.md",
    "09-performance-reliability-audit.md",
    "10-architecture-problems.md",
    "11-prd.md",
    "12-functional-requirements.md",
    "13-non-functional-requirements.md",
    "14-target-architecture.md",
    "15-async-concurrency-design.md",
    "16-error-handling-policy.md",
    "17-observability.md",
    "18-security-review.md",
    "19-testing-strategy.md",
    "20-migration-plan.md",
    "21-target-repository-structure.md",
}
CURRENT_DOCUMENTS = {
    "architecture-decision-log.md",
    "current-plan.md",
    "open-questions.md",
    "requirement-test-trace.md",
}
# Bound later current documents by name. Audit authorities are required below;
# other extensions remain required whenever a canonical document links to them.
CURRENT_EXTENSIONS = {
    "phase-10b-active-state.md",
    "phase-10b-gate-ledger.md",
    "final-audit-active-state.md",
    "final-audit-ledger.md",
    "final-audit-document-index.md",
}
AUDIT_AUTHORITIES = {
    "final-audit-active-state.md",
    "final-audit-ledger.md",
    "final-audit-document-index.md",
}
PHASE_DOCUMENTS = {
    "phase-00": {"phase-0-report.md"},
    "phase-01": {
        "characterization-contracts.md",
        "concurrency-failure-plan.md",
        "phase-1-report.md",
    },
    "phase-02": {"phase-2-report.md", "platform-contract.md"},
    "phase-03": {"phase-3-report.md", "data-compatibility-contract.md", "migration-rehearsal.md"},
    "phase-04": {"phase-4-report.md", "engagement-contract.md"},
    "phase-05": {"phase-5-report.md", "summary-contract.md"},
    "phase-06": {"phase-6-report.md", "watch-contract.md", "loopback-contract.md"},
    "phase-07": {"phase-7-report.md", "music-contract.md", "music-actor-contract.md", "media-cache-contract.md"},
    "phase-08": {"phase-8-report.md", "deployment-contract.md", "backup-restore-contract.md", "operations-contract.md"},
    "phase-09": {"phase-9-report.md"},
    "phase-10": {"production-migration-contract.md", "cutover-runbook.md", "config-migration-guide.md", "phase-10-report.md", "final-command-sheet.md"},
}


def _markdown_names(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("*.md")}


def _anchor(text: str) -> str:
    value = text.strip().casefold()
    value = re.sub(r"[`*_~]", "", value)
    value = re.sub(r"[^\w\- ]", "", value)
    return value.replace(" ", "-")


def _assert_final_audit_inventory(rebuild_root: Path) -> None:
    # S0 active-state B/F and ledger routing require authority -> report links;
    # index "Counts and master orchestration authority" separates later reports
    # from the frozen original set. A2-N1 explicitly rejects the A0-only ceiling.
    # Follow only canonical audit Markdown: exports/other trees cannot admit files.
    audit_root = (rebuild_root / "final-audit").resolve()
    pending = [rebuild_root / "current" / name for name in sorted(AUDIT_AUTHORITIES)]
    for authority in pending:
        assert authority.is_file(), f"missing audit authority: {authority.name}"
    assert (audit_root / "a0-phase-0-report.md").is_file(), "missing required A0 report"
    reached: set[Path] = set()
    while pending:
        document = pending.pop().resolve()
        if document in reached:
            continue
        reached.add(document)
        for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            parsed = urlsplit(raw_target.strip().strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            if target.is_relative_to(audit_root) and target.suffix.casefold() == ".md":
                assert target.is_file(), f"missing routed audit document: {target.name}"
                pending.append(target)
    actual = {path.resolve() for path in audit_root.rglob("*.md") if path.is_file()}
    unrouted = actual - reached
    assert not unrouted, f"unrouted audit documents: {sorted(str(p.relative_to(audit_root)) for p in unrouted)}"


def test_heading_anchor_preserves_spaces_around_removed_punctuation() -> None:
    assert _anchor("Final completion verdict — 2026-09-20") == "final-completion-verdict--2026-09-20"


def test_rebuild_documents_are_partitioned_without_loss() -> None:
    assert _markdown_names(REBUILD_ROOT) == {"README.md", "phase-10-full-sweep-report.md"}
    assert _markdown_names(REBUILD_ROOT / "baseline") == BASELINE_DOCUMENTS
    current = _markdown_names(REBUILD_ROOT / "current")
    assert CURRENT_DOCUMENTS <= current <= CURRENT_DOCUMENTS | CURRENT_EXTENSIONS
    _assert_final_audit_inventory(REBUILD_ROOT)
    for phase, expected in PHASE_DOCUMENTS.items():
        assert _markdown_names(REBUILD_ROOT / "phases" / phase) == expected


def test_all_relative_rebuild_document_links_resolve() -> None:
    _assert_relative_rebuild_document_links(REBUILD_ROOT)


def _assert_relative_rebuild_document_links(rebuild_root: Path) -> None:
    failures: list[str] = []
    for document in sorted(rebuild_root.rglob("*.md")):
        # S0 defines this copied handoff tree as export material, not canonical docs.
        if document.is_relative_to(rebuild_root / "gpt_handoff"):
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("#"):
                continue
            linked_path = (document.parent / unquote(parsed.path)).resolve()
            if not linked_path.exists():
                failures.append(f"{document.relative_to(rebuild_root)} -> missing {target}")
                continue
            if parsed.fragment and linked_path.is_file() and linked_path.suffix.casefold() == ".md":
                linked_text = linked_path.read_text(encoding="utf-8")
                anchors = {_anchor(heading) for heading in HEADING.findall(linked_text)}
                if unquote(parsed.fragment).casefold() not in anchors:
                    failures.append(
                        f"{document.relative_to(rebuild_root)} -> missing anchor {target}"
                    )
    assert failures == []


@pytest.fixture
def audit_tree(tmp_path: Path) -> Path:
    """Synthetic routing only; no application imports or operational fixtures."""
    (tmp_path / "current").mkdir()
    (tmp_path / "final-audit").mkdir()
    for name in AUDIT_AUTHORITIES:
        (tmp_path / "current" / name).write_text(
            "[A0](../final-audit/a0-phase-0-report.md#evidence)\n", encoding="utf-8"
        )
    (tmp_path / "final-audit/a0-phase-0-report.md").write_text("# Evidence\n", encoding="utf-8")
    return tmp_path


def test_audit_inventory_accepts_routed_growth_and_cycles(audit_tree: Path) -> None:
    # No date/name allowlist: a reviewed routing link admits a subsequent report.
    a0 = audit_tree / "final-audit/a0-phase-0-report.md"
    a0.write_text(a0.read_text() + "[Next](future-review.md)\n", encoding="utf-8")
    (audit_tree / "final-audit/future-review.md").write_text(
        "[Earlier](a0-phase-0-report.md#evidence)\n", encoding="utf-8"
    )
    _assert_final_audit_inventory(audit_tree)
    _assert_relative_rebuild_document_links(audit_tree)


@pytest.mark.parametrize("name", sorted(AUDIT_AUTHORITIES))
def test_audit_inventory_rejects_missing_authority(audit_tree: Path, name: str) -> None:
    (audit_tree / "current" / name).unlink()
    with pytest.raises(AssertionError, match="missing audit authority"):
        _assert_final_audit_inventory(audit_tree)


def test_audit_inventory_requires_a0_even_without_incoming_links(audit_tree: Path) -> None:
    for name in AUDIT_AUTHORITIES:
        (audit_tree / "current" / name).write_text("# Routing\n", encoding="utf-8")
    (audit_tree / "final-audit/a0-phase-0-report.md").unlink()
    with pytest.raises(AssertionError, match="missing required A0 report"):
        _assert_final_audit_inventory(audit_tree)


def test_audit_inventory_rejects_missing_routed_report(audit_tree: Path) -> None:
    (audit_tree / "current/final-audit-document-index.md").write_text(
        "[Required](../final-audit/missing-report.md)\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="missing routed audit document: missing-report.md"):
        _assert_final_audit_inventory(audit_tree)


@pytest.mark.parametrize("extra", ["orphan.md", "nested/orphan.md"])
def test_audit_inventory_rejects_unrouted_documents(audit_tree: Path, extra: str) -> None:
    path = audit_tree / "final-audit" / extra
    path.parent.mkdir(exist_ok=True)
    path.write_text("[Self](orphan.md)\n", encoding="utf-8")
    # A handoff export linking to it must not make it canonical/reachable.
    (audit_tree / "gpt_handoff").mkdir()
    (audit_tree / "gpt_handoff/index.md").write_text(
        f"[Export](../final-audit/{extra})\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="unrouted audit documents"):
        _assert_final_audit_inventory(audit_tree)


def test_audit_inventory_rejects_disconnected_cycle(audit_tree: Path) -> None:
    for name, other in (("one", "two"), ("two", "one")):
        (audit_tree / f"final-audit/{name}.md").write_text(f"[Other]({other}.md)\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="unrouted audit documents"):
        _assert_final_audit_inventory(audit_tree)


@pytest.mark.parametrize("target", ["missing.md", "a0-phase-0-report.md#missing-anchor"])
def test_audit_links_reject_missing_targets_and_anchors(audit_tree: Path, target: str) -> None:
    (audit_tree / "current/final-audit-document-index.md").write_text(
        f"[Invalid](../final-audit/{target})\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="missing"):
        _assert_relative_rebuild_document_links(audit_tree)
