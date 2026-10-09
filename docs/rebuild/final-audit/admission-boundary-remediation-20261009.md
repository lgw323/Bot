# Bounded installed-admission history remediation - 2026-10-09

Local implementation and evidence only; independent review is the next task.
No independent closure, candidate refreeze, deployment or operational acceptance.
The original [selection report](admission-selection-evidence-20261009.md) and
[complete diagnosis](admission-boundary-diagnosis-20261009.md) remain unchanged.

## Scope and governing clauses

The delegated owner instruction authorizes only this local history-boundary split
and narrowly guarded synthetic execution. AGENTS sections 1/4/7 require behavior,
data, test and inherited-work preservation. `.agents/skills` does not exist in this
checkout; no checkout skill was available or applied. Fresh current active-state,
ledger, document index, C13 and both admission reports governed this work.

[C13 Deployment Contract](../phases/phase-08/deployment-contract.md), **Dependencies
and source**, retains bounded code/test/deploy exports and sensitive-file exclusions.
**Transaction and failures** retains the approved installed subset, its conftest
cutoff, disabled bytecode/cache, the separate mandatory full source gate, bounded
subprocesses, warning/timeout/cancellation controls and existing caller xfail policy.
No new material exception or product behavior change was introduced.

`LocalDeployment.test` and `deploy/production/verify_candidate.py` already share
`installed_operations_args()`. Their bytes are unchanged in this session and the
existing command assertions pass. The only two exact precollection exclusions are
still `test_a9_local_harness.py` and `test_a9_candidate_packet.py`. Historical proofs
move outside the operations directory; no third module is excluded or skipped.

`build_initial.py` pins `7d596ade8c721931437560ad9e6828762018972c` and has fixed
Phase 9 host/bootstrap paths. Its activation, diagnosis and cache-repair callers
were inspected statically. The current first-staging-install runbook does not
route current candidates through that helper. Its old directory-wide command is
retained historical code, not a verified current-candidate path. No helper was
revived, redesigned or run against host paths; later reuse would need separate
review of the same current selection. Only its existing isolated early-exit test ran.

## Exact original-to-final obligations

All paths in this table are below `tests/integration/`. Original line numbers refer
to the preserved entry bytes of `operations/test_a9_bt1_independent.py`.

| Original mixed case obligation | Sole final owner |
| --- | --- |
| 171-172: exact normalized old configuration SHA-256 | `source_review/test_a9_bt1_history.py::test_prechange_rejection_and_routing` |
| 187-188: old parser raises ConfigurationError with the original exact message | Same source case |
| 205: old store fetch argv targets original production destination | Same source case |
| 192: current configuration load succeeds for approved synthetic isolated destination | `operations/test_a9_bt1_independent.py::test_current_isolated_configuration_and_fetch_routing` |
| 207-209: current store fetch argv targets exact REPOSITORY/ref | Same installed case |

The original `test_prechange_rejection_and_fixed_routing` becomes these two cases.
Every other function/fixture in that module has identical AST; all other 64 collected
cases remain installed, including real synthetic encrypted backup/download/restore/
cancellation. The 22 local-Git fixture cases and isolated-interpreter case also stay
mandatory installed tests. No assertion was weakened, dropped or duplicated between
lanes. `assertion-map.json` compares the original Assert/With AST nodes and records
the unchanged successful-load operation; `partition.json` maps every original node
ID to its final owner(s), with no missing or overlapping cases. Counts are observed,
not enforced quotas: **714 original cases -> 715 units = 588 installed + 127 source**.
The extra unit is the split; the original 126 measurement cases are unchanged.

## Execution boundary and results

All commands, JUnit XML, node IDs, phase outcomes, runner snapshots, archive/import
hashes and before bytes are in
[`scratch/admission-remediation-20261009-01/`](../../../scratch/admission-remediation-20261009-01/).
These are test materials, not a frozen or deployable release. `final-artifact.json`
binds the new extracted app outside the checkout. No original app/docs/scripts/Git
fallback is permitted; only the existing cached Python dependencies and task-owned
receipts are readable from the checkout after preloading the unchanged safety guard.

The original blanket subprocess denial belongs to the diagnostic runner, not either
active admission caller. A fresh unchanged mixed case reproduces that exact denial.
Actual installed execution now uses task-only `envelope.py`, with A8R4 data/credential/
external-network guards retained. It accepts only reviewed Git argv shapes in newly
owned disposable roots, explicit same-case local `remote.git` paths, and the exact
existing `-I` staging probe. Git gets a minimal environment, disabled system/global
configuration, credentials, prompts, hooks, signing and file monitors; init templates
are empty, all protocols are denied except explicit local file transport. No inherited
remote, shell, arbitrary command or production fallback is admitted. Synthetic Git
commit-tree/push operations affect only disposable local repositories, never project
refs or an external repository.

The child interpreter keeps `-I`, a minimal environment, and an added in-child audit
guard. Its four negative probes reject original-source reads, credentials, external
network and descendant processes before running the unchanged original probe code.
Twelve parent negative checks cover forbidden cwd/data paths, external/inherited
remotes, credential helpers/config environment, history commands, arbitrary Python,
shell, direct process bypass, credential reads and external network. Rejection probes
use validation/audit events before any forbidden operation. No OS permissions or
security settings were changed.

| Run | Outcome | Interpretation |
| --- | --- | --- |
| Historical complete diagnostic (unchanged prior report) | 563 PASS / 3 FAIL / 22 ERROR / 0 SKIP, 189.85s | All 25 failed/error cases were guard denials; preserved |
| Fresh original mixed case (`red-mixed`) | 1 FAIL / 0 PASS / 0 SKIP | Expected diagnostic subprocess rejection reproduced |
| First sandbox focus (`focused`) | TIMEOUT at 300s; 59 completed PASS bodies, remaining NOT_RUN/incomplete | Windows stdlib socketpair stall, not a completed admission result |
| `focused-v2` | 69 PASS / 2 FAIL / 22 ERROR / 0 SKIP, 2.50s | Harness Path/string mismatch |
| `focused-v3` | 93 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 43.09s | First focused green |
| `focused-v4` | 94 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 43.32s | Final focused regression including synthetic sensitive-file rejection |
| `source-measurement` | 61 PASS / 1 FAIL / 0 ERROR / 0 SKIP, 4.66s | Harness rejected original frozen-export provenance; stopped at first failure |
| `source-measurement-v2` | 127 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 57.72s | All 127 mandatory source cases, including 126 unchanged measurement cases |
| `source-full` | 7 PASS / 1 FAIL / 0 ERROR / 0 SKIP, 4.02s | Full source attempt: 1885 collected; 1877 NOT_RUN after guard rejected out-of-scope import-probe interpreter |
| `installed` | 587 PASS / 1 FAIL / 0 ERROR / 0 SKIP, 226.60s | Complete first attempt; synthetic .env fixture overblocked by runner |
| `installed-v2` | 588 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 232.96s | Complete final installed admission, every one of 588 cases attempted |
| `docs` | 2 PASS / 1 FAIL / 0 ERROR / 0 SKIP, 3.13s | Link/anchor checks PASS; existing frozen single-report inventory expectation FAIL |
| `docs-final-links` | 1 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 2.54s | Final links after authority routing update; overlaps prior docs link check |

Final installed run used 1078 actual local Git children and one isolated Python child. All 12 parent and four in-child boundary rejection probes passed. The final installed/source lanes are disjoint; focused runs overlap and must not be added to them. Collection and guard probes are not counted as behavioral cases. Full repository completion remains NOT_RUN; no clean whole-suite claim.


The first sandbox focus attempt stalled in Windows stdlib asyncio socketpair accept
and reached its unchanged 300-second bound. Subsequent guarded runs used the same
automatically approved outside-filesystem-sandbox workflow as prior audits; no access
denial was bypassed. The retained `focused-v2` failure was a runner Path-versus-string
comparison in the Windows audit event; `source-measurement` failed because the new
runner initially disallowed the original frozen-export fixture's exact read-only
HEAD provenance. Only runner handling was corrected, with all attempts preserved.
The full repository attempt encountered an out-of-scope subprocess denied by the
source runner; its coverage was not broadened to obtain green. No application defect
is inferred from any of these harness results.
The full-source attempt's existing `audioop` deprecation warning remains in its
transcript; runtime-warning and unraisable-exception errors were not suppressed.
The first complete installed attempt recorded 587 PASS / 1 FAIL: a new runner
credential-name rule also blocked `test_source_sensitive_artifacts_are_rejected`
from creating its existing literal `synthetic forbidden` file inside its own new
temporary source tree. The correction permits synthetic credential-named fixtures
only inside task-owned disposable paths; original/user credentials remain denied.
The full first attempt and exact runner snapshot are retained.

## Identity, preservation and reproduction

Branch remains `codex/rebuild-v2`; HEAD remains
`cb54da9948370db64133a0ead6c9df89d0b61055`. No fetch was performed, so remote freshness
is unverified. HEAD is provenance only; source and archive hashes bind dirty bytes.
The index and all refs remain unchanged. The exact modified/added files and full
before/after SHA-256 values are in `preservation.json`; `task-only.patch` is relative
to entry bytes, preserving inherited runtime/documentation changes. Original reports,
archives and evidence are unchanged. Excluded real-data/backup/archive paths were
checked by metadata only; their contents were not inspected.

- Extracted test archive: 375 files, 652209 bytes;
  SHA-256 `98e75a541c416ff4830517993adc8429b660705c5ede787abd73fbca6421de16`.
- Archive source identity: `15b74329d83810a02834ad8c04b08951d84a1d3efc9ca8bb5c2b583f04daed42`.
- Required-source working-file manifest: `bd944b774dca8ee5abe2eb793b7a9d818204a5ee26bd56516de49561d5ecefe4`.
- Existing packet export identity: `189c848f9960611989975ba3cee930f16b144385165d56d9aaa77844812438e8`.
- Existing archive inventory validator: PASS, unchanged, with empty expected comment
  solely for test inventory validation; no committed-release identity is claimed.
- SHA-256 of final task-only execution envelope: `f181c6283263195d26defe9bdea979027329ef62be1a7061427108c3f6078bc1`.

Core file SHA-256 values (routing/report hashes and before hashes are in preservation.json):

| File | Final SHA-256 |
| --- | --- |
| `src/discordbot/operations/adapters/admission.py` | `e6b01d2599ef771bf967cc48280b7c20189e7495c54fe7935020873325608a1d` |
| `tests/integration/operations/test_a9_bt1_independent.py` | `c8b9f78fff9472bc96f5ef223279608ec64dfd8c0426aa4b7c79c9e23cc06b9f` |
| `tests/integration/operations/test_admission_selection.py` | `7fc8fcbcd34d8c2e262ed2e3c3016d37c65e1d9bd41e647a93f8ec7524158e6c` |
| `tests/integration/source_review/test_a9_bt1_history.py` | `6a6a93e94e1b02f3c64f8a448e5c695d8ac466416a25fc86292bd64ce2b31a03` |
| `README.md` | `143c60b783de8ebb21a911587603e5ecf739d08d81ca7eebfdddb540942e7691` |
| `CHANGELOG.md` | `8eaabe24dfee7dc07e68f98a336c901a007a945ac4d8404c9c79ed4d39123070` |
| `docs/rebuild/phases/phase-08/deployment-contract.md` | `befaa40694735221886b5e900c9a8d92e2e661a2e5f0e20970d3ff0c54c5d442` |


Commands executed from the repository root (each test attempt uses a unique mode;
reproduction must use a new owned receipt directory rather than overwrite evidence):
This is execution history, not a script to apply again to corrected files. RED and
`split_test.py` require the saved entry bytes. Independent final verification should
rebuild an isolated test archive from reviewed current bytes and rerun the final
source/installed runners without reapplying the split. Saved runner snapshots identify
earlier attempts; later runner changes do not rewrite their outcomes.

```powershell
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/prepare.py entry
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/setup.py
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/prepare.py red
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py red-mixed
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/split_test.py
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/prepare.py green
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py focused
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py source_checks.py source-partition
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py focused-v2
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py source_checks.py source-measurement
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py focused-v3
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py source_checks.py source-measurement-v2
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/prepare.py final
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py installed
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py focused-v4
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py checks.py installed-v2
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/run_bounded.py source_checks.py source-full
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/verify.py partition
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/docs_checks.py
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/docs_checks.py docs-final-links
git -c core.safecrlf=false diff --check
git diff --cached --check
.\.venv\Scripts\python.exe -I -B scratch/admission-remediation-20261009-01/verify.py preservation
```

Remaining limits: complete full repository gate, independent review, current committed
release identity, reviewed dependencies/ARM64/ABI, installed manifest/configuration,
Linux behavior, target readiness and all 23 operational obligations remain open.
Original A9/A10 BLOCKED and Integrated administrative SCOPE-CLOSED retain their
meanings. No Pi/production/real backup/network/credentials/package install, project
commit/push, cleanup, deployment or refreeze occurred. MyFood/MyMoney were untouched.

**One next task: independent local verification of this patch, assertion/node-ID map,
synthetic execution envelope and complete source/installed receipts. Then stop for
owner review; do not combine this with closure, refreeze or deployment.** If rollback
is later requested, reverse only the entry-relative task patch while retaining all
evidence and inherited work. No rollback was performed.
