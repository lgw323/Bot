# A8R3 release inventory remediation

Date: 2026-10-04. Branch `codex/rebuild-v2`; entry HEAD
`5e846ae6a08e8fda210e6e4a06c457387012604f`. Implementation commit
`0ac1ab55a0748320a56ff54809813663ac149943`.

**Local M3 remediation PASS; Phase 8 remains FAIL. M1/M2 remain independently
CLOSED; M3 remains OPEN pending independent verification.** This is the authorized
narrow remediation, not A8V3, a complete Phase 8 verdict, A9, Integrated Audit or Phase 11.

## Authority and entry boundary

Read actual Git HEAD/status/index, root AGENTS, current active-state, Phase 8 ledger
and document index, A8V2 report and exact RED, C13 deployment, C14 backup/restore,
C15 operations, original Phase 8 report, B20 Phase 8 exit/rollback and ADR-023/024.
Reviewed current filesystem/build/source, deployment adapter/transaction and relevant
fixtures/credential guard. No applicable nested AGENTS or repository `.agents` was
present; no specialized skill or delegation was needed. `rg` is unavailable, so
PowerShell and existing `.venv` Python were used without installation.

[Entry inventory](a8r3-entry-inventory.json): exactly 70 inherited files, 11 modified /
59 untracked, empty index. Repo truth matched the delegated HEAD. Original A8V2
[report](a8v2-phase-8-verification-report.md), [probe](a8v2-release-probe.py) and RED
receipt remain unchanged. Original probe SHA256:
`ca4079f1cf0f72ca0d9bc11aa258c104526ab59c06fc30eb740bd72aa1890e0c`.

## Root cause and minimum correction

C13 requires checksums of all payload files and rejection of missing, changed or
additional files. `ReleaseStore.validate` excluded every node whose basename was
`manifest.json`. Thus an unlisted `app/manifest.json` disappeared from the observed
set, passed equality, and was accepted by both activation and subsequent current reads.
Conversely, a legitimately inventoried nested manifest made the sets unequal and
could not publish. The unchanged RED reproduced the activation bypass before editing.

The validator now exempts only `path / "manifest.json"`, the release-root metadata
which cannot contain its own checksum. Recursive enumeration, containment/link checks,
checksum validation, exact set equality and the incomplete-release guard are retained.
Path equality uses the host filesystem path semantics; inventory keys remain canonical
relative POSIX strings as emitted by the builder. No basename blacklist, extension
restriction, directory inventory requirement or path normalization redesign was added.

The matching producer exclusion also needed a one-predicate correction: Builder used
`node.name != ".building"` and omitted nested `.building` payloads. This was surfaced
during investigation and reproduced before implementation. It now excludes only
`path / ".building"`. This adjacent scope is necessary to support legitimate reserved
names under the same exact-inventory contract; no publishing redesign occurred.
Only these two predicates and explanatory comments change runtime code.

Root lifecycle remains: `.building` marks admission; `candidate.json` is written after
the payload inventory; publish removes that candidate, writes root `manifest.json`,
removes the root marker, validates, and applies existing immutable modes. Nested
manifest/candidate/build-marker names are ordinary checksummed payload. Empty directories,
including a directory named `manifest.json`, remain allowed. Source selection, wheel pins,
manifest schema, release identity, permissions, retention M1/M2, transaction order and
one-attempt compatibility-gated rollback are unchanged. No published release was edited.

## Exact RED to GREEN and regressions

The original probe was executed unchanged against entry HEAD: ordinary extra control
PASS; nested manifest FAIL with `rejected=False, current=new`. The same file against
the correction has both cases PASS: rejection and `current=old`. No assertion, fixture,
skip, xfail or synchronization adaptation was made to that probe.

All 59 new cases were authored before the fix and executed unchanged on both versions:

- 36 cases: twelve unlisted relative paths across validate, activate and current reads;
  ordinary JSON, nested/capitalized manifests, manifest-named parent directory, application
  and three venv layouts, candidate metadata and build markers. Pointer bytes/target and
  temporary pointer cleanup are checked. Pre-fix: 18 PASS / 18 FAIL.
- 18 cases: manifest/candidate/build-marker names in source `src`, `tests`, `deploy`,
  Windows `Lib`, Linux `lib` and materialized `lib64` layouts. Real builder inventory,
  publication, activation, unchanged build reuse and idempotent publish; command runner
  is fake. Pre-fix: 6 PASS / 12 FAIL (six omitted `.building`, six listed manifests).
- Four listed nested-manifest change/removal cases, preserving old activation; all
  initially fail because the valid baseline nested manifest is incorrectly excluded.
- One manifest-named empty-directory positive control, PASS before and after.

New tests total **25 PASS / 34 FAIL -> 59 PASS**. All failures were contract failures;
the missing `.building` inventory entries appear as deliberate assertion-time KeyErrors.
No test-authoring failure, changed expectation or hidden skip occurred. The first boundary
run's console was yielded before completion; its completed XML supplies the exact counts.

## Fresh execution receipts

PowerShell, repository root, existing virtual environment, no dependency changes:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$strict = @('-q', '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning', '-p', 'no:cacheprovider', '--tb=short')
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v2-release-probe.py @strict --junitxml=docs/rebuild/final-audit/a8r3-original-red.xml
.\.venv\Scripts\python.exe -m pytest tests/integration/operations/test_release_inventory_contract.py @strict --junitxml=docs/rebuild/final-audit/a8r3-boundaries-red.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v2-release-probe.py tests/integration/operations/test_release_inventory_contract.py tests/integration/operations/test_build.py tests/integration/operations/test_filesystem.py @strict --junitxml=docs/rebuild/final-audit/a8r3-focused-green.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v2-release-probe.py docs/rebuild/final-audit/a8v1-backup-probe.py docs/rebuild/final-audit/a8v2-backup-probe.py docs/rebuild/final-audit/a8-retention-probe.py docs/rebuild/final-audit/a8v1-retention-probe.py tests/integration/operations tests/integration/data tests/unit/platform tests/architecture @strict --junitxml=docs/rebuild/final-audit/a8r3-regression-results.xml
.\.venv\Scripts\python.exe -m pytest tests/ @strict --junitxml=docs/rebuild/final-audit/a8r3-full-results.xml
.\.venv\Scripts\python.exe -m pytest tests/architecture/test_rebuild_documentation.py::test_heading_anchor_preserves_spaces_around_removed_punctuation tests/architecture/test_rebuild_documentation.py::test_all_relative_rebuild_document_links_resolve @strict --junitxml=docs/rebuild/final-audit/a8r3-doc-results.xml
```

Common flags were passed literally in executed argv. XML trailing whitespace is
normalized for Git only. Counts are distinct test identities, not repeated-run totals.

| Receipt | PASS | FAIL | SKIP | Evidence |
| --- | ---: | ---: | ---: | --- |
| [Original baseline](a8r3-original-red.xml) | 1 | 1 | 0 | Unchanged A8V2 activation probe; console 1.17s |
| [New boundaries baseline](a8r3-boundaries-red.xml) | 25 | 34 | 0 | 59 pre-fix cases; XML 10.227s |
| [Focused correction](a8r3-focused-green.xml) | 86 | 0 | 0 | Original2 + new59 + existing25; console 17.93s |
| [Affected regression](a8r3-regression-results.xml) | 823 | 1 | 0 | Operations/data/platform/architecture + audit probes; console 195.37s |
| [Full suite](a8r3-full-results.xml) | 1562 | 2 | 27 | Console 225.77s; known inventory/Deno failures and opt-in Linux skips |

The [machine-readable count/hash receipt](a8r3-test-evidence.json) records the final
distinct union: **1576 PASS / 2 known FAIL / 27 SKIP / 0 XFAIL**, 1605 unique cases.
Full suite contributes 1591 cases; fourteen audit cases outside `tests/` add fourteen
passes. The final [documentation link/anchor check](a8r3-doc-results.xml) is 2 PASS
in 0.40s, already in that union.
Baseline outcomes are not added to the corrected union; focused cases overlap regression.
M1 original4/remediation78/independent4 and M2 original2/remediation36/independent2
all pass in the affected regression. This retains scoped closure evidence without
conducting a new independent audit or reopening the remaining Phase 8 gate matrix.

## Evidence limits and independent boundary

New evidence is real temporary filesystem/checksum/build/atomic replacement execution
with fake venv/pip commands and modeled Windows symlinks. Linux-shaped venv directory
fixtures are supported-layout checks on Windows, not real Linux execution. Broader
regressions use synthetic SQLite/encryption/restore workers, fake external services,
disposable local Git repositories and offline/in-process transports. Root credential
guard, temporary DB routing and subprocess/opt-in Linux boundaries were inspected first.
No production DB, credentials or live external provider was used. No WSL was needed.

Known stale documentation inventory, missing Deno, Linux/systemd opt-in skips, audioop
deprecation and A3-N1/A3-I1 limits remain explicit; no clean full-suite claim. Real
Linux link/fsync/ownership/cgroup behavior, ARM64 packaging, power-loss durability and
live provider/Pi/RPO/RTO proof remain outside this remediation. M2's O(candidate count)
restore I/O still has no production-scale timing proof within the unchanged 180s backup
unit budget. No performance/service timeout policy was changed.

The complete remaining Phase 8 gate disposition remains A8V2's matrix. Regression
passes here do not independently close those gates. Next separate authorization:
independent unchanged M1/M2/M3 probes, inventory/path/reserved-name/build challenges,
then remaining Phase 8 gates. A0-A7 PASS retained; friend activation HELD and Integrated
deployment condition unmet. No A8V3/A9/Integrated/Phase11 work was performed.

## Ownership, rollback and safety

Owned runtime/test changes and CHANGELOG are in the implementation commit above.
Evidence/report and compact state/Phase 8 ledger deltas form a separate local Conventional
Commit. [Ownership receipt](a8r3-ownership-receipt.json) proves 67 inherited contents
byte-identical plus exact inverse reconstruction for CHANGELOG, active-state and ledger.
The untracked document index, exports and original audit evidence remain untouched.
Only HEAD plus owned deltas is staged for mixed files; no bulk staging/reset/push.
Staged diff and `git diff --cached --check` are reviewed before each commit.

Two CHANGELOG preparation attempts stopped before writing because inherited newline
bytes were mixed; insertion was corrected to preserve those exact bytes. Default Git
index writes were denied by the sandbox. Authorized `.git` escalation succeeded;
an escalated patch read from sandbox-owned Temp was denied, so the same owned patch
was briefly copied into the workspace and applied successfully, then removed. No
automatic approval rejection or broader permission/installation change occurred.

Rollback is a scoped revert of implementation `0ac1ab55a0748320a56ff54809813663ac149943`,
preserving inherited CHANGELOG edits; the evidence commit can independently revert
routing. No production rollback, cleanup, data change or remote history rewrite.
Exact final HEAD, empty-index check and owned-process completion are in the handoff.
All six pytest invocations completed; temporary DB/executor/restore children were
closed/reaped by their fixtures. No owned persistent worker/server/browser/WSL process
or pending test write remains, and no unrelated process was stopped.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` are distinct and untouched. No Pi connection,
actual release/backup/history cleanup, real DB reset/restore/migration, deployment,
systemd/Cloudflare/network/security change, live provider, credentials/data access or
MyFood/my_money work. All mutation fixtures are synthetic temporary paths.

**STOP A8R3 for supervisor review. Phase 8 FAIL; M3 pending independent verification.**
