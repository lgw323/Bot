# Bounded admission selection correction - 2026-10-09

**Implemented and self-tested; overall installed admission remains FAIL/BLOCKED.**
The authorized two-module classification resolves the original collection errors.
A further mandatory module requires Git history, triggering the explicit scope
stop. No third exclusion, assertion change, skip, fallback or independent closure.
No deployment, final release, Pi/SSH/network/API, real data/credential access,
installation, service action, commit/push/reset or cleanup was performed.

## Authority and change

The supervisor's current assignment authorizes ONLY
`tests/integration/operations/test_a9_local_harness.py` and
`tests/integration/operations/test_a9_candidate_packet.py` as mandatory SOURCE
measurement-tool regressions, rather than installed-runtime admission modules.
This implements the distinction already in C13 deployment contract lines 60-61
and `LocalDeployment.test`: approved installed subset and mandatory full source
development/commit gate. Earlier [freeze](candidate-freeze-evidence-20261009.md)
and [support-boundary diagnosis](packaging-support-boundary-20261009.md) remain
unaltered historical evidence. Current authority, AGENTS and both reports were read.

Changed files (exact before/after SHA-256 values are in `preservation.json`):

- `src/discordbot/operations/adapters/admission.py`: shared exact file-path selection.
- `src/discordbot/operations/adapters/deployment.py`: use that selection.
- `deploy/production/verify_candidate.py`: use the same selection.
- `tests/integration/operations/test_admission_selection.py`: four new regressions.
- `README.md`, `docs/rebuild/phases/phase-08/deployment-contract.md`, `CHANGELOG.md`:
  classification, both mandatory lanes, commands and bounded change record.
- This report. All inherited edits are preserved; `task-only.patch` is relative
  to entry bytes, not HEAD, so it excludes unrelated dirty work.

The two exact `--ignore` paths act before import/collection. There are no glob,
marker or filename-prefix exclusions. Source tests and their assertions are
unchanged. Builder/SourceBuilder payload roots, archive validator, release identity,
sensitive-file exclusions, warnings, 300-second admission deadline, cancellation
code, and the production verifier's `xfail_strict=true` remain unchanged. The
LocalDeployment command retains its prior xfail behavior. No `.git`, docs, scripts
or root conftest was added to runtime. The conftest *cutoff boundary* remains;
there is no `tests/integration/operations/conftest.py` file in this snapshot.

## Fresh results and explicit stop

All receipts are under
[`scratch/admission-selection-20261009-01/`](../../../scratch/admission-selection-20261009-01/).
Commands, transcripts, JUnit XML, import origins and byte hashes are retained.
Collection is never counted as behavioral PASS.

| Run | Fresh outcome | Interpretation |
| --- | --- | --- |
| `red-collection` | 584 collected; 2 collection ERROR; 0 SKIP | Original missing `scripts` failures reproduced from unchanged original bytes |
| `green-collection` | 588 collected; 0 ERROR | Corrected exact selection in isolated extracted app; collection GREEN only |
| `selection-regression` | 4 PASS / 0 FAIL / 0 SKIP | Both caller command controls, exact exclusions, pre-import poison and synthetic partition/future-name coverage |
| `source-partition` / `partition.json` | PASS: 714 = 588 installed + 126 source; empty overlap/missing sets | Actual collected node-ID sets, not a count quota |
| `source-measurement-v4` | **126 PASS / 0 FAIL / 0 SKIP**, pytest 61.47s | Both unchanged source modules, every case executed |
| `green-admission-v2` | **58 PASS / 1 FAIL / 0 SKIP**; 529 remaining NOT_RUN in this admission attempt | Stop at first additional repository-history dependency |
| Full repository `pytest tests/` | **NOT_RUN** after the explicit scope stop | Still mandatory; focused source PASS does not replace the full source gate |
| Independent review, Linux/ARM64 installation, operational/live gates | **NOT_RUN** | No closure or deployment inference |

The four new tests explain the increase from historical 584 installed / 126 source
to observed 588 / 126. Across behavioral runs, the four focused selection cases are
distinct from the 58 admission passes and 126 source passes. All 714 relevant cases
remain required; no case was converted to SKIP or removed.

The installed failure is
`test_a9_bt1_independent.py::test_prechange_rejection_and_fixed_routing`, line 169:
it calls `git show <fixed-HEAD>:src/discordbot/operations/adapters/configuration.py`
from extracted app. Line 197 also requests historical `git_backup.py`.
The executed failure is **PermissionError from the existing subprocess-denial
guard**. A real Git command was not executed, so no real Git exit code is claimed.
Source inspection establishes the additional Git-history dependency; the archive
has no `.git` and cannot obtain history through original-source fallback. That
module remains in admission. Changing its classification or provenance fixture
exceeds the authorized two-module boundary, so no such repair was attempted.

The 126 source passes cover generator budgets/nearest-rank percentiles, abort and
ownership, candidate atomic work, receipt integrity/provenance, dirty-byte drift,
stale imports/bytecode, process timeout/cancellation/parent-pipe loss, worker
network/descendant denial and source-path containment. The final source run used
the established A8R4 guards plus only read-only `git rev-parse HEAD` and the exact
guarded frozen-byte worker. Windows required an automatically approved execution
outside the filesystem sandbox for this bounded source run; the same guards and
300-second outer bound remained active.

Earlier attempts are retained in `summary.json`: an evidence-runner Windows audit
argument parsing error occurred before pytest; buffered sandbox admission/source
attempts were interrupted without final results; another sandbox source attempt
stalled at its first SQLite candidate case and was interrupted after the guarded
retry completed. These incomplete attempts receive no final PASS credit. No
application change was made for the stall. The earlier `green-admission-v2` command
receipt must be read with preserved `checks-execution-v2.py`: that script appends
`-vv --maxfail=1` to its recorded base pytest arguments. Later command receipts
record those arguments directly. `*-process.json` records outer argv and deadline.

## Identity, isolation and preservation

The original failed source-freeze ZIP remains 677840 bytes, SHA-256
`b7b4b3fff5ddc00a5cc9beaad9302d91777f042e116745b0a533eba80811ccbd`.
All original freeze and both support-diagnosis evidence directories were fingerprinted
at entry and checked unchanged. Excluded operational/archive files were compared
by size/mtime only; their contents were not read. HEAD, branch, refs and raw index
are unchanged. Existing dirty/untracked paths remain. Diff checks passed.

The new `green.zip` is **isolated test material only, not a deployed/final release**:
374 files, 650993 bytes, SHA-256
`169fd3089d7e3bef00cbe19929bcee5a8f6f88e8c928ffb86e8bb081e5ee23eb`.
Its sorted source identity is
`ec109856f353cd3b0c56e3ef5cc4f2956f82f127d13af32907ed00f05b8c8a78`.
The existing archive inventory validator accepts it unchanged using an empty
expected comment only for inventory validation; no commit identity is claimed.

The source lane's current-file manifest identity is
`42c10b3d5262a80a70af04cb962867abb1b8f2c5d8fb46b11ef819527bfb9446`;
its existing packet export identity is
`c001beb0a34a9a7590c63212e97951b5fe3eb6d1f3885c79d97ed9911ec2ab8e`.
Both bind actual working bytes, including uncommitted changes. HEAD is supplemental
provenance only. `*-source.json`, `*-artifact.json`, `*-imports.json`, `partition.json`
and `preservation.json` provide exact inventories, reviewed/changed identities,
test membership and unchanged-after-run checks.

Installed runs use a new OS-temp extraction outside the repository, clear Git and
Python path overrides, disable bytecode/cache/plugin autoload, preload the original
safety guards, then deny original-tree reads except cached venv dependencies and
owned receipts. All imported application modules originate in the extraction and
match archive hashes. No scripts modules were imported. Extracted bytes remained
unchanged. Synthetic fixtures alone create/clean their own temporary data.

## Reproduction and handoff

Commands below were executed from the repository root. For a new independent run,
copy the helpers to a fresh owned receipt directory; never overwrite these outputs.
`prepare.py` derives repository root from that directory's depth. Keep the same
guards and current hash manifests; do not substitute original-source imports.

```powershell
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/prepare.py entry
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/prepare.py red
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/checks.py red-collection
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/prepare.py green
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/run_bounded.py checks.py green-admission-v2
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/run_bounded.py checks.py green-collection
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/run_bounded.py checks.py selection-regression
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/source_checks.py source-partition
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/run_bounded.py source_checks.py source-measurement-v4
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/verify.py partition
.\.venv\Scripts\python.exe -I -B scratch/admission-selection-20261009-01/verify.py preservation
git -c core.safecrlf=false diff --check
git diff --cached --check
```

Next independent review should inspect the task-only patch, both caller command
tests, node-ID partition, source XML/provenance, archive/import hashes, preserved
controls and the additional failing module. A separately authorized decision is
needed for that Git-history dependency; no additional exclusion is authorized here.
Full source regression and complete installed admission remain open. ARM64 wheels/
lock/ABI, truthful committed release identity, installed manifest/configuration,
target readiness and all 23 operational obligations remain open as previously
recorded. Original A9/A10 BLOCKED and Integrated administrative SCOPE-CLOSED retain
their meanings. Pi remains offline for owner hardware work; Phase11 cleanup is
deferred. Stop here for review, without self-certified independent closure.

If rollback is later requested, reverse only `task-only.patch` against the recorded
entry bytes; preserve inherited edits and all evidence. No rollback was performed.
