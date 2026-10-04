# A8R1 release retention remediation

Date: 2026-10-04. Branch `codex/rebuild-v2`; entry HEAD
`f34ef43e8edee503ead5aa5d2e9f8e297450adec`.

**Local remediation PASS; Phase 8 remains FAIL. A8-M1 is OPEN, remediated pending
independent verification.** This task stops for parent review. A8V1, A9, Integrated
Audit and Phase 11 were not performed.

## Authority and scope

Actual HEAD/branch, empty index and inherited 11 modified / 59 untracked files
matched the delegation. Read repository AGENTS.md, current active-state, ledger,
document index, original A8 report/probe, all Phase 8 contracts/report, B20 Phase 8,
ADR-023/024 and relevant decision/trace/runbook routing before remediation.
No applicable nested AGENTS.md, checkout `.agents`/`.codex` or code-specific skill
was present. No sub-agent was used. No authority contradiction was found.
The October 4 resumption supersedes yesterday's elapsed stop window; no new cutoff
was supplied. TUF connectivity was not needed for local synthetic verification.

C13's retention contract governs: current, rollback/activation targets, four newest
published releases, all published releases younger than seven days, one-day grace
for incomplete candidates, and the unchanged sixteen-directory build admission cap.
Later permission/off-host changes do not waive these requirements. Original audit
evidence and contracts remain unchanged; historical implementation PASS is not
independent audit closure.

## Root cause and implementation

Standalone cleanup sliced all directories before checking for a manifest.
Post-deploy retention independently sliced all directories with no publication
filter. Four newer unfinished builds displaced all four old published recovery
alternatives in both paths. Their duplicated policies also differed on incomplete
grace and activation-intent protection.

The narrow fix changes only two adapters and adds one test module:

- `retention.py` filters publication markers before selecting four: a manifest file
  exists and `.building` is absent, matching `Builder.publish`'s completion markers.
  A manifest plus `.building` is still incomplete; candidate-only and empty
  interrupted directories are unpublished. The same classification selects the
  seven-day or one-day grace.
- Directory mtime descending remains the existing ordering and age source; no
  manifest timestamp reinterpretation or release-ID ordering was introduced.
  Current may count among the newest four; this is a union of protections, not
  four additional releases after every pin. Older explicit targets are additive.
- `LocalDeployment.retain` keeps the same durable rollback record and delegates
  deletion to existing `cleanup_releases`. It now reads current plus both intent
  files before deleting. Existing rollback replacement semantics and conservative
  protection of referenced targets despite an expired `protected_until` remain.
- Protection pins here mean existing current/rollback/activation references;
  no new pin-file format or production-pin lookup is introduced. Full checksum
  validation at activation/current and nested-link validation before deletion remain
  in `ReleaseStore`; retention classification is not a new full integrity scan.

No schema, backup/Music format, dependency, CLI response, service configuration,
permission, network/security setting, contract threshold or admission cap changed.
No general operations redesign was needed. Shared operations callers remain under
their existing kernel lock; the helper does not acquire a second lock.

## Fresh evidence

| Evidence | PASS | FAIL | SKIP | Interpretation |
| --- | ---: | ---: | ---: | --- |
| [Original unchanged probe, RED](a8r1-original-red.xml) | 2 | 2 | 0 | Both mixed-candidate paths delete all four alternatives |
| [Initial boundary RED](a8r1-boundaries-red.xml) | 30 | 48 | 0 | Includes one incorrect capacity-message regex |
| [Corrected boundary RED, unchanged implementation](a8r1-boundaries-red-corrected.xml) | 31 | 47 | 0 | Exact final 78-case module before code fix |
| [Focused GREEN](a8r1-focused-green.xml) | 82 | 0 | 0 | Original4 + new78, unchanged assertions/fixtures from corrected RED |
| [Operations/data/platform/architecture regression](a8r1-regression-results.xml) | 714 | 1 | 0 | Known documentation inventory failure only |
| [Final standard full suite](a8r1-full-results.xml) | 1,467 | 2 | 27 | Known inventory + missing Deno; existing Linux skips |
| **Distinct final current-code union** | **1,471** | **2** | **27** | Full suite plus four original probe cases; repeats excluded |

Final [documentation/anchor check](a8r1-doc-results.xml): 2 PASS in 0.92s,
already included in the full-suite union. All final selections have zero XFAIL. Full final run: 115.74s, exit 1. Regression
is a subset of the full suite; 78 new cases are already in that suite. XML test-case
identities verify the union instead of adding overlapping counts. The original
probe's four cases all pass in focused GREEN. Its entry SHA256 remains
`b45b2bbc410be8f9f713d4cc020ab2b84dc0946d5f5146fbed1fbad1bef8b9e1`.

Known full failures are `test_rebuild_documents_are_partitioned_without_loss`
(stale single-audit-file expectation) and
`test_pinned_provider_and_runtime_load_without_network` (missing release-local Deno
executable). Neither was skipped, weakened, installed around or repaired here.
The temporary missing-link failure from the initial full run is resolved in the
final full run. No fresh material runtime failure remains in these selections.

New tests cover both entrypoints with 0/1/3/4/6 published alternatives and four
newer candidates of each kind (building, candidate-only, empty, manifest-building);
creation/name order differs from mtime ordering. They also cover one second before,
exactly at and one second after the one-/seven-day boundary, current within/outside
the floor, old rollback/activation references, expired intent protection, invalid
intent before deletion, nested-link rejection, no current, and sixteen protected
directories refusing admission without launching a build command. Release fixtures
are validated where complete. All deletion is confined to temporary synthetic roots.

The initial new-test RED run had one test-authoring mistake: its capacity-error
regex said `retention`, whereas the existing message is `release capacity reached;
retain rollback evidence before cleanup`. Corrected to the actual fixed prefix,
then reran the entire new module on unchanged implementation before fixing code.
No product assertion, fixture, skip or xfail was weakened to obtain GREEN. The
original A8 probe was never edited. The first full run also found a temporary
missing ownership-receipt link in this in-progress report (1,466 PASS / 3 FAIL /
27 SKIP). The receipt was then completed and the full suite rerun; the initial
receipt is preserved separately as [initial full result](a8r1-full-initial-results.xml). The first CHANGELOG insertion attempt stopped
at a byte-prefix assertion (mixed existing line endings), before writing; a scoped
byte-preserving insertion then succeeded. Initial Git staging was denied by the
managed read-only `.git` sandbox; the already-authorized scoped staging/commit
succeeded through tool escalation. There was no automatic approval rejection.

Commands use the existing Windows virtual environment without installation:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
# Common options on every run:
# -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8-retention-probe.py
.\.venv\Scripts\python.exe -m pytest tests/integration/operations/test_retention_contract.py
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8-retention-probe.py tests/integration/operations/test_retention_contract.py
.\.venv\Scripts\python.exe -m pytest tests/integration/operations tests/integration/data tests/unit/platform tests/architecture
.\.venv\Scripts\python.exe -m pytest tests/
```

The two standalone boundary RED runs used `--tb=short` then `--tb=no`; focused
GREEN/regression/full use `--tb=short`. Each run also specifies the linked
`--junitxml=docs/rebuild/final-audit/a8r1-*.xml` receipt path. XML traceback trailing
whitespace is normalized for Git only; outcomes and assertion content are retained.

## Isolation and evidence limits

Root conftest blocks repository dotenv reads and clears inherited application
settings before collection. Legacy/data fixtures use temporary DB/SQL paths.
Operations fixtures use generated test keys, fake services/build commands and
disposable local Git repositories; no external transport is used. Full-suite
process/network call sites and opt-in Linux guards were reviewed. Local child
processes run synthetic probes, offline version commands or browser JS harnesses.
No live provider, Discord, Gemini, YouTube, SSH/Pi or real service was contacted.

This is Windows synthetic filesystem/adapter evidence. The inherited symlink model
retains real `os.replace`, aging and removal, but does not establish Linux
fsync/power-loss/ownership or systemd behavior. WSL was not needed or started.
Known documentation inventory/Deno failures, existing Linux/systemd skips, audioop
deprecation and A3-N1/A3-I1 limitations remain explicit. No clean full-suite, live,
production, independent Phase 8 or remaining-gate PASS is claimed.

## Ownership, rollback and stop boundary

Implementation commit: `403c453855e1b39126efb8d72390737aba5e5def`
(`fix: preserve published release retention floor`). Separate local evidence commit
contains this report, entry/ownership receipts, XML results and two authority deltas;
its final HEAD is supplied in the handoff to avoid a self-referential commit hash.

[Entry inventory](a8r1-entry-inventory.json) records all inherited 70 paths/hashes.
The CHANGELOG insertion, active-state AY append and Phase 8 remediation cell are
the only owned changes in mixed files. All other inherited bytes, including the
untracked document index, original A8 probe/report and exported handoff, are
preserved. Scoped staging uses HEAD plus owned deltas for mixed files, never bulk
staging or reset. [Ownership receipt](a8r1-ownership-receipt.json) records byte
reconstruction and original-probe identity. Final residual status/index and commit
IDs are verified in the handoff.

Rollback is a scoped revert of the implementation commit, preserving inherited
CHANGELOG work; revert the separate evidence commit only to undo its routing.
No production/data rollback, remote push or history rewrite is involved.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched. No Pi/production
access, deploy, real DB/backup/release/history deletion, credentials, systemd,
Cloudflare or network/security changes occurred. MyFood/my_money were untouched.
Friend activation remains HELD and the Integrated Audit deployment condition unmet.

All seven functional pytest executions exited, including both full runs. No
persistent server/browser/WSL process was started. Final documentation/link checks,
scoped staged-diff review, byte-preservation and residual-index verification are
completed before handoff. No task-owned worker or pending test write is retained;
only synthetic test fixtures and local evidence were created. The initial CIM
listing was sandbox-denied; scoped read-only escalation then identified the remaining
six Node processes as unrelated application/automation work, not repository test
harnesses. No Python/pytest/ffmpeg worker remained. No unrelated process was stopped
and no files in other projects were accessed. Unrelated processes
are not stopped. No PC shutdown is issued.

**STOP A8R1 for parent review.** The next separate authorized boundary is independent
A8 verification: rerun the original unchanged probe on the final candidate,
independently challenge eligibility/order/protection and both entrypoints, then
complete every remaining gate listed in the original A8 report. A8-M1 may only be
closed by that independent verification; A0-A7 retain their independent PASS.
