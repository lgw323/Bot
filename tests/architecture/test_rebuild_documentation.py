from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
}


def _markdown_names(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("*.md")}


def _anchor(text: str) -> str:
    value = text.strip().casefold()
    value = re.sub(r"[`*_~]", "", value)
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"[ ]+", "-", value)


def test_rebuild_documents_are_partitioned_without_loss() -> None:
    assert _markdown_names(REBUILD_ROOT) == {"README.md"}
    assert _markdown_names(REBUILD_ROOT / "baseline") == BASELINE_DOCUMENTS
    assert _markdown_names(REBUILD_ROOT / "current") == CURRENT_DOCUMENTS
    for phase, expected in PHASE_DOCUMENTS.items():
        assert _markdown_names(REBUILD_ROOT / "phases" / phase) == expected


def test_all_relative_rebuild_document_links_resolve() -> None:
    failures: list[str] = []
    for document in sorted(REBUILD_ROOT.rglob("*.md")):
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("#"):
                continue
            linked_path = (document.parent / unquote(parsed.path)).resolve()
            if not linked_path.exists():
                failures.append(f"{document.relative_to(ROOT)} -> missing {target}")
                continue
            if parsed.fragment and linked_path.is_file() and linked_path.suffix.casefold() == ".md":
                linked_text = linked_path.read_text(encoding="utf-8")
                anchors = {_anchor(heading) for heading in HEADING.findall(linked_text)}
                if unquote(parsed.fragment).casefold() not in anchors:
                    failures.append(
                        f"{document.relative_to(ROOT)} -> missing anchor {target}"
                    )
    assert failures == []
