# A8V2 independent Phase 8 verification - FAIL

Date: 2026-10-04. Branch `codex/rebuild-v2`; audited entry HEAD
`b4a0e4d7b3a51fc8f10ebf5f26dca2212eb48763`. M2 implementation
`ca8078fc4b84e57b46a63ac534edc34480bce19f`.

**A8-M2 independently CLOSED; A8-M1 remains CLOSED. New A8-M3 MATERIAL OPEN.
Phase 8 remains FAIL.** Functional auditing stopped at the first new material RED.
No implementation fix, requirement change, A9, Integrated Audit or Phase 11 work.
The resumed October 4 supervision has no time cutoff.

## Authority and scope

Actual branch/HEAD matched the briefing. Index was empty. The
[entry inventory](a8v2-entry-inventory.json) records exactly 70 inherited files,
11 modified / 59 untracked, with byte hashes before audit edits. Root AGENTS.md
governs; no `.agents`, `.codex` or nested AGENTS at the relevant audit/test ancestors
exists. No specialized skill or delegation requirement applies; no sub-agent used.
Initial `rg` and `python` aliases were unavailable, so the existing `.venv` Python
and PowerShell were used without installation. An initial absent `.agents` directory
lookup attempted broader enumeration and returned access denials; protected scratch
contents were not read. Subsequent lookups used explicit existence checks and UTF-8.

Read active-state, Phase 8 ledger and document-index routing, original A8/A8V1 and
A8R2 reports/exact probes, C13 deployment, C14 backup/restore, C15 operations,
historical Phase 8 report, B20 exit/rollback, ADR-023/024 and scoped deploy/backup/
restore runbooks. Reviewed current recovery, release/filesystem/build/source,
deployment transaction/CLI, service/timer/polkit, credentials/manual/audit and remote
adapter code. Original contracts remain the comparison baseline.

ADR-024's explicit group/ACL correction and Phase 10's approved private Git adapter,
independent remote readback and E3 four-hour timer supersede their historical scope.
They do not waive verified local retention or exact release inventory. Recorded
E1/E2 publication/recovery and E3/E4 activation/observation belong to the distinct
production source/pin below. They are neither current-code tests nor fresh host proof.

## M2 independent closure and M1 preservation

The original [M2 probe](a8v1-backup-probe.py) remains byte-identical, SHA256
`0ea8cf50a6806392f671d025c332ceb1d81dd3a97f005b38a13b574d2ef3497a`.
[Negative-control runner](a8v2-baseline-runner.py) loads only the pre-M2 operations
recovery adapter from `01d848555cfbf35115523752982a7ddb711ce09f` into process memory,
after the credential guard. Other dependencies are current. This is an exact old
adapter control, not a full historical checkout. No source replacement/index change.

Fresh baseline **1 PASS / 1 FAIL** reproduces all eight valid prior archives deleted,
seven rejected corrupt orphans plus one new valid archive retained. Fresh current
**2 PASS** passes the unchanged assertions. All 36 remediation boundaries independently
reran and passed, including real encrypted semantic/schema rejection, ordering/pins,
I/O/cancellation/publication faults, capacity and partial-prune failure.

Review confirms validation completes before pruning is planned and before success
audit/latest publication. Corrupt candidates do not consume the eight-point floor;
rejected artifacts remain. Operational faults propagate before deletion. Prior latest
and the new snapshot are additionally pinned, including clock regression. Locally valid
remote-failure orphans remain eligible, consistent with C14. No backup codec/schema,
candidate ordering, retention threshold or remote policy is redefined.

[Two new independent cases](a8v2-backup-probe.py) both PASS:

1. Instrument actual restore validation across nine archives. Each private candidate
   is removed before the next; all nine validations finish while the prior pointer
   and archives still exist. Success audit precedes latest, then exact pruning.
   Independently restore all eight survivors afterward.
2. Cancel while the real restore worker holds a completed synthetic private DB. Release
   the bounded test barrier, reap the actual worker and propagate cancellation. Every
   prior byte/latest remains, with no rehearsal plaintext/sidecars left behind.

M1's original four, remediation 78 and independent four cases all PASS unchanged.
The original M1 probe SHA256 remains
`b45b2bbc410be8f9f713d4cc020ab2b84dc0946d5f5146fbed1fbad1bef8b9e1`.
Its pre-M1 negative control was not rerun in A8V2; A8V1's baseline stays historical.
No evidence reopens M1; M3 below is a separate release-integrity requirement.

### Resource and timing limits

Retention performs sequential full restore/application checks, adding O(number of
candidate records) decrypt/SQLite work under the shared operation lock. No parallel
candidate fanout or retained plaintext accumulation occurred in the independent case.
Create's 65-entry admission guard bounds normal candidate admission; direct `retain`
has no separate directory admission guard. Default candidate restores use a 64 MiB
input limit, 120s restore request, 10s startup and 10s inspect budgets, plus cleanup.
Those are per-candidate bounds, not one total 180s backup deadline. Hashing also performs
local I/O; stalled filesystem/worker termination is not proved by these tests.

The existing backup unit still has 180s start / 30s stop budgets; remote transport has
its own 90s total budget. Normal eight-archive revalidation plus snapshot/remote work
has no measured production-scale fit in that service budget. The bounds do not establish
an RPO/RTO or throughput PASS. Timeout before local latest leaves the prior publication
and local/possibly remote orphan evidence; after mutation, uncertain outcomes still
need operator reconciliation. No production benchmark or timing change was attempted.

## New A8-M3: nested manifest basename bypasses release inventory

**MATERIAL, OPEN.** C13 Layout and identity requires the release manifest to reject
missing, changed or additional files. `ReleaseStore.validate` at
`src/discordbot/operations/adapters/filesystem.py:198` excludes every file whose basename
is `manifest.json`, instead of excluding only the release-root manifest. At lines
200-201, inventory comparison therefore cannot detect an unlisted nested manifest.
`activate` calls this validator at line 207 and then replaces current at line 215.
`current` also accepts the resulting release through the same validator.

[Exact minimal probe](a8v2-release-probe.py) creates two synthetic complete releases,
validates the new one, activates old, and writes one extra JSON file absent from the
new release's manifest. Only the extra filename differs between the two cases:

| Extra file | Expected | Actual |
| --- | --- | --- |
| `app/settings.json` | Reject; current remains old | PASS: rejected, current old |
| `app/manifest.json` | Reject; current remains old | FAIL: accepted, current new |

[RED receipt](a8v2-release-results.xml): `rejected=False, current=new`.
The two cases use the real validation/activation implementation and real atomic
replacement; only symlink creation/resolution uses the existing Windows fixture.
The same exclusion predicate is present in original Phase 8 commit `4a0ddb2`.
This is an original missed integrity boundary, not an A8R2 regression.

Severity follows from a required pre-activation integrity gate accepting a release
whose contents are outside its reviewed checksum inventory. No malicious code execution,
runtime consumption of this synthetic JSON, production compromise or ability for the
runtime account to write immutable releases is claimed. The defect is not cured by
the ordinary-file control passing or the deploy owner being trusted: C13 explicitly
requires detection of accidental release additions. No scoped waiver was found.

Required separate remediation: make the metadata exclusion path-specific and test
nested names across validation/activation and legitimate built inventories. Do not
weaken exact inventory equality or edit published production releases. Preserve this
unchanged RED probe for the next independent verification. No fix was made here.

## Fresh commands and unique evidence

PowerShell, repository root, existing virtual environment:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$strict = @('-q', '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning', '-p', 'no:cacheprovider', '--tb=short')
.\.venv\Scripts\python.exe docs/rebuild/final-audit/a8v2-baseline-runner.py docs/rebuild/final-audit/a8v1-backup-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v2-m2-baseline-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-backup-probe.py docs/rebuild/final-audit/a8-retention-probe.py docs/rebuild/final-audit/a8v1-retention-probe.py tests/integration/operations/test_backup_retention_contract.py tests/integration/operations/test_retention_contract.py @strict --junitxml=docs/rebuild/final-audit/a8v2-focused-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v2-backup-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v2-backup-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v2-release-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v2-release-results.xml
```

Common flags above were repeated literally in executed argv. XML trailing whitespace
is normalized only for Git. No test-authoring failures, fixture/assertion revisions,
xfails or skips occurred.

| Receipt | PASS | FAIL | SKIP | Evidence type |
| --- | ---: | ---: | ---: | --- |
| [Old M2 adapter](a8v2-m2-baseline-results.xml) | 1 | 1 | 0 | Separate negative control; console 4.69s |
| [Focused current](a8v2-focused-results.xml) | 124 | 0 | 0 | M1 86 + M2 original2/remediation36; console 123.93s |
| [Independent backup](a8v2-backup-results.xml) | 2 | 0 | 0 | Real temporary SQLite/encryption/restore and worker; 5.93s |
| [Independent release](a8v2-release-results.xml) | 1 | 1 | 0 | Real filesystem/validator with Windows link model; 0.47s |
| **Distinct current union** | **127** | **1** | **0** | 128 unique cases; zero XFAIL; no overlaps |

Baseline results are not added to the current union. Historical A8R2 affected760/1,
full1503/2/27 and distinct1513/2/27 were not rerun or counted as fresh evidence.
Full suite was not run after new material RED, per the explicit stop instruction.
Known inventory and missing-Deno failures, Linux/systemd skips, audioop deprecation
and A3-N1/A3-I1 remain. There is no clean full-suite claim.

## Remaining Phase 8 gates

| Gate | A8V2 disposition / next evidence boundary |
| --- | --- |
| Release retention | PASS scoped: M1 remains CLOSED, 86 fresh cases |
| Backup retention/publication validation | PASS scoped: M2 CLOSED, original2 + remediation36 + independent2; live timing unmeasured |
| Immutable release identity/inventory/activation | FAIL: new M3; ordinary extra control passes, nested manifest bypasses actual activation guard |
| Offline pins/source export/build failure/dependency rollback | PARTIAL: code and existing tests reviewed; broader independent execution stopped at M3 |
| Lock/pointer/tamper/path escape | PARTIAL: Windows activation probe only this phase; full existing/Linux checks not freshly rerun |
| Deploy order/one rollback/cancellation/initial failure | PARTIAL static: application and LocalDeployment/CLI reviewed; remaining synthetic pipeline/manual/service checks not freshly run |
| Restore fallback/encryption/promotion | PARTIAL: M2 invokes real isolated restore; broader existing promotion/CLI/fallback suite not freshly rerun |
| Service/timer/polkit | PARTIAL static: independent units, four-hour persistent timer, 180s backup budget/narrow polkit read; no fresh asset suite or real unit execution |
| Config/credentials/manual/health/telemetry/audit bounds | PARTIAL: inspected relevant implementation; complete independent execution pending |
| Later corrections/E1-E4 | Documentary scoped supersessions retained; historical exact-release evidence is not current behavior proof |
| Architecture/full regression | NOT RUN after material stop; known failures retained |
| Linux filesystem/group/credential/cgroup, ARM64, power-loss, live RPO/RTO | UNRUN; fresh host proof BLOCKED by authorization. WSL not needed before stop and not started |

No required unrun gate is marked PASS. Remaining local gates resume only after separate
M3 remediation and independent review. Approved isolated WSL can support Linux local
behavior, not Pi/systemd/ARM64/power-loss or production SLO proof. Any necessary live
gate needs separately authorized exact host/release/actions, maintenance/rollback and
data boundaries; this audit does not work around the prohibition.

## Ownership, safety, cleanup and rollback

Owned work is this report, three audit Python files, four XML receipts, inventory/
ownership receipts and compact BB/Phase8 deltas in two mixed authority files. Original
reports/probes, inherited document index/exports and runtime/tests/dependencies/schema
are unchanged. [Ownership receipt](a8v2-ownership-receipt.json) verifies 68 inherited
files byte-for-byte and inverse reconstruction of the two mixed files: all70 preserved.
Only HEAD plus owned deltas is staged for those files; inherited work is not bulk-staged.
Staged diff and whitespace are reviewed before the authorized local Conventional Commit.
Exact final commit/HEAD and residual index status are in the handoff; no push.

Rollback is a scoped revert of the A8V2 evidence commit preserving inherited edits.
No product/data rollback is performed. Functional RED is deliberately retained as
audit evidence, outside the standard `tests/` collection; no passing test is weakened.

Root pytest credential guard and temporary fixtures were inspected before execution.
All four pytest sessions exited. The independent worker test releases its barrier and
reaps the task/worker in `finally`; fixture DBs/executors close, no pending test write
or owned persistent server/browser/WSL process remains. No unrelated process stopped.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched. No Pi/production
connection, actual archive/release/history cleanup, real DB access/restore/reset/migration,
credential copying, deploy/service/routing/network/security change, live provider or
MyFood/my_money work occurred. All mutation probes use synthetic temporary paths.

**STOP A8V2. Next: supervisor review of M3, separate authorized remediation, then
independent M1/M2/M3 and remaining Phase8 gates.** A0-A7 PASS unchanged; friend
activation HELD and Integrated deployment condition unmet. No A9/Integrated/Phase11.
