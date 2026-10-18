# A8V1 independent Phase 8 verification - FAIL

Date: 2026-10-04. Audited branch `codex/rebuild-v2`, entry HEAD
`957df6a5d4b19d793ebfebb844e477bb2452ad83`. A8R1 implementation
`403c453855e1b39126efb8d72390737aba5e5def`.

**A8-M1 independently CLOSED. New A8-M2 MATERIAL OPEN. Phase 8 remains FAIL.**
Stopped functional auditing at the first new material RED, as instructed. No implementation
fix, assertion relaxation, contract redefinition, A9, Integrated Audit or Phase 11 work.
The October 4 instruction has no time cutoff; yesterday's expired cutoff was not reused.

## Authority and original/current comparison

Verified Git HEAD/branch, empty index and exactly 70 inherited files (11 modified,
59 untracked), recorded in [entry inventory](a8v1-entry-inventory.json). Root AGENTS.md
applies; no checkout `.agents`, `.codex` or nested AGENTS governing the edited audit
paths exists. Scratch export instructions are outside this scope. No applicable skill
or delegation requirement; no sub-agent used. Initial `rg`/`python` command aliases
were unavailable; PowerShell and existing `.venv` Python were used without installation.

Read active-state, assigned ledger row and document index, original A8 report/probe,
A8R1 report and code diff, B20 Phase 8 exit/rollback row, C13 deployment, C14 recovery,
C15 operations and historical Phase 8 report. Reviewed ADR-023/024, relevant open
questions/trace, backup/restore/normal-deploy runbooks and latest Phase 10B authority.

Original Phase 8 completion is explicitly repository/synthetic evidence. B20 requires
deployment/dependency rollback and restore drill; C13-C15 specify the invariants. Later
ADR-024 corrects Linux group/read/credential handling. Phase 10 explicitly selects the
private Git off-host adapter/readback and E3 four-hour timer; those scoped changes do
not waive local verified-backup retention. The current backup runbook still requires
eight validated alternatives and says never to remove latest or its valid predecessor
to clear capacity. No retention waiver was found.

Historical E1/E2 are recorded encrypted publication/readback and independent recovery
of an exact artifact; E3/E4 cover boot/timer activation and bounded observation on the
recorded production release. They are not tests of corrupt-orphan local retention and
not fresh October 4 live evidence. The earlier C14 statement that no remote adapter
exists is historical scope superseded by those explicit Phase 10 changes, not a new
runtime defect. No production receipt/data rehash or live observation was performed.

## A8-M1 independently closed

The original [four-case probe](a8-retention-probe.py) remains byte-identical, SHA256
`b45b2bbc410be8f9f713d4cc020ab2b84dc0946d5f5146fbed1fbad1bef8b9e1`.
[Baseline runner](a8v1-baseline-runner.py) imports the credential guard first, then
loads only the two original retention/deployment adapters from pre-remediation
`f34ef43e8edee503ead5aa5d2e9f8e297450adec` using local `git show` into process memory.
All other dependencies and the test are current; this is a targeted negative control,
not a full historical checkout run. It writes no source/index/working-tree replacement.

Fresh baseline: **2 PASS / 2 FAIL**. Both incomplete-candidate paths delete all four
published alternatives. Fresh current: **4 PASS**, within the 142-case focused run.
The 78 A8R1 boundary cases independently reran unchanged and passed.

Code review confirms both paths now share publication-marker eligibility: manifest
file and no `.building`, matching completed Builder publication. It does not redefine
publication as a fresh checksum scan of every retained release. Directory mtime remains
the established ordering/age input, and pins are unioned with the four-publication floor;
current can count among those four. This is not four extra releases beyond every pin.
Old rollback evidence is deliberately replaced by the successful deployment's new
rollback record; activation intent and actual current remain independently protected.

The existing 78 cases cover empty/candidate-only/building/manifest-building, counts
0/1/3/4/6, one-second/exact one-day/seven-day boundaries, invalid intents, nested links,
old pins, no current and the 16-directory admission cap. Added [four independent cases](a8v1-retention-probe.py)
mix six publications and six interleaved fresh/expired candidates with creation/name
order different from mtime, current inside/outside the floor, two older pins and two
consecutive cleanup calls. Both entrypoints leave the exact expected set and all kept
publications validate. These four cases PASS. No new release-retention defect established.

## New A8-M2: invalid backup records displace verified recovery alternatives

**MATERIAL, OPEN.** `Backups.retain` in
`src/discordbot/operations/adapters/recovery.py:69` sorts every metadata filename and
slices the first eight before validating any archive. `create` calls it after publishing
the new latest (`:58`). Invalid/orphan metadata therefore consumes the verified-alternative
floor and causes destructive deletion of older valid encrypted recovery points (`:74`).
This module is byte-equivalent after newline normalization to original Phase 8 commit
`5b32140`; this is a missed original contract boundary, not an A8R1 regression.

[Exact independent probe](a8v1-backup-probe.py) uses the real Backups/DataRecovery,
temporary SQLite, generated encryption key, real encryption/restore/audit/filesystem:

1. Create eight normal encrypted backups and independently restore each into its own
   fresh temporary DB. All eight are recoverable before the fault.
2. Inject seven remote publication failures with an in-process fake. Each failure
   naturally leaves its local encrypted artifact/metadata and preserves prior latest;
   no network is used. Corrupt only those seven orphan ciphertext files, modeling the
   corruption/partial-artifact boundary explicitly required by C14.
3. Independently try each orphan with real restore. All seven are rejected. All eight
   prior verified archives still exist before the next successful backup. Directory
   inventory remains below the 65-entry admission cap (31 entries before final create).
4. Make one normal successful local backup and independently restore it. Retention now
   deletes **all eight** older verified archives, retaining **seven rejected corrupt
   archives plus one valid new archive**. Expected at least seven prior valid survivors
   (eight verified points including new); actual zero. The no-orphan control retains
   seven prior valid archives and passes.

This is additional loss caused by retention, beyond the explicitly injected corrupt
orphans. It is not a demand for unlimited history, more than eight alternatives, a
new remote policy, or a claim that all archives can survive arbitrary corruption.
The newest valid snapshot survives, but the promised recovery alternatives and valid
predecessor disappear. No production archive was inspected, changed or deleted.

Probe result **1 PASS / 1 FAIL / 0 SKIP**. [RED XML](a8v1-backup-results.xml)
preserves the assertion: `kept 0 prior verified + 1 new; kept 7 independently rejected
corrupt publications instead`. No implementation correction was attempted. Stop here
for supervisor review and separate A8-M2 remediation; rerun this unchanged probe during
independent verification and retain M1 coverage.

## Fresh commands and counts

PowerShell, repository root, existing virtual environment; no installation:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$strict = @('-q', '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning', '-p', 'no:cacheprovider', '--tb=short')
.\.venv\Scripts\python.exe docs/rebuild/final-audit/a8v1-baseline-runner.py docs/rebuild/final-audit/a8-retention-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v1-baseline-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8-retention-probe.py tests/integration/operations/test_retention_contract.py tests/integration/operations/test_retention.py tests/integration/operations/test_filesystem.py tests/integration/operations/test_build.py tests/integration/operations/test_deployment.py tests/integration/operations/test_pipeline.py tests/integration/operations/test_recovery.py @strict --junitxml=docs/rebuild/final-audit/a8v1-focused-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-retention-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v1-retention-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-backup-probe.py @strict --junitxml=docs/rebuild/final-audit/a8v1-backup-results.xml
```

These reproduce the exact executed argv; common flags were repeated literally in the
actual invocations. No test-authoring failures or revised assertions occurred.
The initial authority-file preparation stopped at a line-ending precondition before
writing; byte-preserving append/replacement then succeeded. A ledger column assembly
mistake was corrected before staging; it did not affect test evidence or inherited bytes.

| Receipt | PASS | FAIL | SKIP | Scope |
| --- | ---: | ---: | ---: | --- |
| [Baseline](a8v1-baseline-results.xml) | 2 | 2 | 0 | Separate targeted old-adapter negative control, 2.26s |
| [Focused current](a8v1-focused-results.xml) | 142 | 0 | 0 | Includes original4 and remediation78; 31.51s |
| [Independent retention](a8v1-retention-results.xml) | 4 | 0 | 0 | Current mixed ordering/pins/idempotence, 3.80s |
| [Independent backup](a8v1-backup-results.xml) | 1 | 1 | 0 | Current control + new M2, 3.76s |
| **Distinct current union** | **147** | **1** | **0** | No overlaps, zero XFAIL |

Historical A8R1 714 PASS/1 known inventory FAIL and full 1467 PASS/2 known FAIL/27 Linux
SKIP (distinct1471/2/27) were not rerun or added to these counts. Standard full suite
was not run after new material RED under the explicit stop instruction. Known inventory,
missing Deno, Linux/systemd skips, audioop deprecation and A3-N1/A3-I1 limitations remain;
there is no clean full-suite claim. XML trailing whitespace is normalized only for Git.

## Remaining original A8 gates

| Gate | A8V1 disposition and remaining boundary |
| --- | --- |
| Published release retention | PASS scoped; M1 CLOSED, original/boundary/independent cases above |
| Immutable identity/offline pins/source exclusion/build failure | PARTIAL: build tests PASS; Builder/SourceBuilder inspected; full export/bounds/real runner review unfinished at material stop |
| Lock/pointer/tamper/path escape | PARTIAL: filesystem tests PASS, actual Windows lock and modeled links; Linux durability/ownership not inferred |
| Deploy order/one rollback/cancellation/initial failure | PARTIAL: deployment and real local pipeline tests PASS with fake commands/services; complete CLI/manual/real service review still pending |
| Backup/restore/encryption/fallback/promotion | FAIL M2; existing recovery tests PASS but miss invalid-record retention; temporary real restore proves both pre-fault validity and invalid-orphan rejection |
| Units/timer/polkit | PARTIAL static: read runtime/backup assets and asset assertions; independent process units, 4h persistent timer and180s budget remain; no new asset test run or real systemd/polkit claim |
| Credentials/config/manual/health/telemetry/audit bounds | PARTIAL: C15/source routing inspected; comprehensive independent scoped tests/review stopped at M2 |
| Later corrections and E1/E2 | PARTIAL documentary reconciliation: explicit remote adapter and ADR-024 supersessions retained; historical exact-release proof cannot close current M2 or replace fresh tests |
| Architecture/full regression | NOT RUN in this microphase after material stop; known failures retained |
| Linux fsync/power-loss/permissions/cgroup/ARM64/live RPO/RTO | BLOCKED for live proof by this task's authorization; WSL was not started before material stop |

After separately authorized M2 remediation and independent verification, finish the
remaining repository/synthetic gates in a new microphase. If Linux-only tests are needed,
reuse only the approved isolated WSL environment with synthetic fixtures and no installs.
That can support Linux local behavior, not Pi/systemd/ARM64/power-loss or production SLOs.
Fresh host gates require explicit separate approval naming the target host/release,
read-only checks or permitted service/backup/restore actions, maintenance/rollback and
data boundaries. This task neither requests such actions now nor bypasses the prohibition.

## Preservation, commit, safety and cleanup

Only this report, three audit-only Python files, four XML receipts, entry/ownership
receipts and compact AZ/Phase8 authority deltas are owned. Original A8/A8R1 evidence,
document index, exports, runtime/tests/dependencies/schema and all other inherited bytes
are preserved. [Ownership receipt](a8v1-ownership-receipt.json) records hashes and
inverse reconstruction of the two mixed authority files. Stage HEAD plus owned deltas
for those files, never the whole inherited working copy; staged diff/check and final
index/status are verified before handoff. Local Conventional Commit only, no push.
Rollback is a scoped revert of this evidence commit, preserving inherited authority
edits; no runtime/data rollback is part of this audit. Exact final commit is in handoff.
Initial staging met the managed read-only `.git` boundary. Scoped escalation was
authorized; its first attempt could not read the sandbox temporary patch, so the same
patch was placed in ignored task scratch and staging succeeded. These were filesystem
access errors, not an automatic approval-review rejection. The staged whitespace check
also prompted removal of one owned trailing blank line before commit.

Root test credential guard was inspected before tests; synthetic fixtures use temporary
DB/archive/release paths and generated keys. Build/service commands are fake. Baseline
uses local Git objects only. Windows link modeling retains real replace/aging/removal,
but does not prove Linux fsync/power-loss. All four pytest executions exited; fixture
DB/executor cleanup completed without strict runtime/unraisable warning failures.
No persistent worker/server/browser/WSL process was started; no pending test writes remain.
No unrelated process was inspected or stopped. MyFood and other projects untouched.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and unchanged. No Pi connection,
production data/credentials, deploy, real restore/migration, actual release/backup/history
cleanup, systemd/Cloudflare/network/security change, live provider or shutdown action.
A0-A7 PASS retained; friend activation HELD and Integrated deployment condition unmet.

**STOP A8V1. Next: supervisor review of A8-M2, separately authorized remediation, then
fresh independent M1/M2 and remaining Phase8 verification.**
