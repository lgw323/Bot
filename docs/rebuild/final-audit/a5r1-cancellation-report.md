# A5R1 - Summary cancellation notification remediation

2026-10-02. **A5R1 PASS (local remediation); Phase 5 remains FAIL.**
A5-M1 is remediated, not independently CLOSED. Stop for parent review; fresh A5V1
is recommended and was not performed. A6, Integrated Audit and Phase 11 not started.

## Scope, authority and cause

Entry HEAD `edfc03c7177cf115ad5c504fdc60b53ba4f17be8`, branch `codex/rebuild-v2`.
Implementation candidate: `40db561f95b01408139430829d374b1e39c5d95c`.
Read current active-state, ledger and index first, then the [original A5 FAIL and exact
probe](a5-phase-5-report.md), C7 Summary contract, ADR-020, C1/C2, F006-F010,
FR-026-030, historical Phase 5 report, AGENTS.md and scoped implementation/tests.
The parent's explicit A5R1 authorization supersedes the previous STOP only for this
bounded repair. There was no wider design ambiguity or product contract change.

`SummaryController.run` caught native `CancelledError` and awaited private feedback
before re-raising. A failing Discord send became `ResponderFailure`, escaped that
handler and reached the outer delivery-failure handler, which returned normally.
The original task therefore completed with `cancelled=False`, `cancelling=1`.

The cancellation handler now catches only the expected `ResponderFailure`, emits
the existing fixed `summary.response/delivery_failed` event, then re-raises the
original cancellation. A successful notification still precedes cancellation propagation.
Responder timeout still becomes the same delivery failure. A second native cancellation
still propagates; no broad catch/finally suppression or notification retry was added.
Other unexpected errors are not newly swallowed. Existing provider/UI error translations
remain unchanged.

## Exact RED to PASS evidence

The Python appendix in the original A5 report was extracted verbatim to
`$env:TEMP\discordbot-a5-cancellation-probe.py`. No synchronization adaptation,
assertion change, skip or weakening was made. Original runtime was still unchanged
when RED ran. For both successful and failed sends, the probe verifies provider
cancellation, no active supervisor work/reservations/results/views, one private send
and raw-error redaction before asserting native cancellation.

| Run | PASS | FAIL | SKIP / XFAIL | Result |
| --- | ---: | ---: | ---: | --- |
| Original A5 probe, unchanged runtime | 1 | 1 | 0 / 0 | 0.61s; failed send: propagated=false, cancelled=false, cancelling=1 |
| New 11 regression cases, before fix | 8 | 3 | 0 / 0 | 6.15s; failed/expired notification and completed-result handoff lose cancellation |
| Same 11 regression cases, after fix | 11 | 0 | 0 / 0 | 6.08s |
| Original A5 probe, unchanged after fix | 2 | 0 | 0 / 0 | 0.59s; both sends: propagated=true, cancelled=true, cancelling=1 |
| Full scoped Summary selection, after fix | 96 | 0 | 0 / 0 | 7.54s; original 85 plus new 11 |

Final disjoint evidence is **96 + 2 = 98 PASS / 0 FAIL / 0 SKIP / 0 XFAIL**.
The standalone 11-case rerun overlaps the 96 and is not added again.
One inherited `audioop` DeprecationWarning occurred in the 96-case run.

Commands, repository root, existing Windows Python 3.12 `.venv`:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a5-cancellation-probe.py" -c pyproject.toml --confcutdir $env:TEMP -q -s -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest tests/integration/summary/test_cancellation_delivery.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest tests/integration/summary/ tests/characterization/test_summary_contracts.py tests/characterization/test_component_contracts.py::test_f009_f010_fr028_fr029_preserve_summary_components tests/characterization/test_component_contracts.py::test_f010_fr029_correct_summary_topics_paginate_with_stable_ids -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

New matrix: native cancel / outer deadline / typed provider error crossed with
successful send / failed send / real two-second responder timeout (nine cases),
plus cancellation again during notification, and cancellation at completed-result
handoff with a failed notification. Barriers control interleavings; no random sleeps.
The timed-send cases exercise the existing actual two-second bound and join its
cancelled coroutine. Tests assert exact safe-message/private-send arguments,
single delivery-failure telemetry, no raw diagnostic leakage and released ownership.
All owned controller tasks are joined and views closed in finally; the synthetic
fixture stops the service/provider. The original probe installs the credential guard.

## Invariants and limits

- Preserve one private cancellation attempt when possible, no retry on uncertain
  delivery, public successful results, private errors/details and unchanged text/buttons.
- Preserve provider/request cancellation, result-handoff cleanup, reservations, views,
  modals, FIFO active 1/waiting 4, total 60-second budget and two-second Discord bound.
- ACL checks, source minimization, telemetry redaction, retention and UI bounds remain
  unchanged; existing synthetic coverage passes. No schema/state/dependency changes.
- Ordinary deadline/provider errors still complete through their safe private response;
  their failed/expired sends still report delivery failure once without a second send.

Focused tests preceded the complete Summary selection. The repair affects only the
cancellation handler; no broad/full-suite run was justified or claimed under this
microphase's explicit scope. Known inventory/Deno failures, audioop warning and A3-N1
MINOR/A3-I1 INFO remain disclosed. No new live Discord/Gemini/HTTP/Gateway/Pi proof,
provider quality/capacity guarantee or exhaustive interleaving claim is made.

## Git ownership and rollback

[Entry inventory](a5r1-entry-inventory.json) records all inherited **11 modified /
59 untracked files, 70 content hashes, empty index**. All 70 matched before the
first inherited-file edit. A temporary byte-for-byte snapshot supports preservation
checks after removing only the four owned changelog/authority/navigation deltas.
Original A5 report, A5 inventory and its already mixed document-index additions remain.

Implementation commit `40db561f95b01408139430829d374b1e39c5d95c` owns only the six-line
adapter change, new regression file and isolated changelog insertion. Evidence commit
owns this report/inventory, active-state AN append and Phase 5 ledger-row update only.
Its exact SHA is returned in the completion message. The untracked document index
keeps its separate A5R1 navigation append uncommitted with all inherited navigation.
Each commit receives a staged diff and `git diff --cached --check` review. Inherited
active-state/ledger/changelog changes are excluded using patches against HEAD.
Final expected residual is the same 11 modified/59 untracked and empty index.

Initial default staging could not write `.git/index.lock`; authorized scoped elevated
Git operations were used. A temporary patch had to be placed in the workspace and
normalized to LF before Git accepted it. These failed attempts made no commits or
unrelated index changes. The owned staging helper was removed; no inherited files,
history, production artifacts or backups were deleted. No bulk staging/reset or push.

Rollback: revert the evidence and implementation commits in reverse order after
review, preserving inherited work. The uncommitted A5R1 navigation append is separately
owned; remove only that append if rollback is requested. No DB restore or deployment.

Production was not accessed: recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`
and pin `r-8e9018d4b8061cde-3dac82a792fad576` stay distinct and unchanged. No real Discord
send/conversation ingestion, external AI call/charge, credential/permission change,
production DB write, restart, old-state restore, V1, concurrent writer, systemd,
Cloudflare, install or deployment. Friend activation HELD, Integrated Audit deployment
condition unmet, MyFood paused. A0-A4 PASS unchanged; Phase 5 remains FAIL.

**STOP A5R1 for parent review.** Recommend fresh independent A5V1 to rerun unchanged
M1 and challenge notification failure/timeout, cancellation ownership, cleanup and
adjacent success/error/privacy/limit paths before independently closing M1.
