# A8 Phase 8 operations audit — FAIL

Date: 2026-10-03. Audited branch `codex/rebuild-v2`, HEAD
`d07412c968c2274948d1c9af3c2e835369226173`. One time-boxed audit only.
Entry checked at 03:39 UTC; material RED confirmed at 03:42–03:43 UTC.
Checkpoint began at 03:43 UTC, before the 03:48 checkpoint / 03:50 stop limits.

**A8-M1 MATERIAL OPEN:** incomplete release directories displace the required four
newest published releases from retention protection. No implementation fix was made.
Stop for supervisor review and separately authorized remediation. A0–A7 results are
not changed; A9, Integrated Audit and Phase 11 were not started.

## Authority and current-code comparison

Read current active-state, assigned ledger row and document-index routing first, then
all four Phase 8 documents (historical report plus C13 deployment, C14 backup/restore,
C15 operations contracts). Checked B20 Phase 8 exit/rollback row, ADR-023 and scoped
ADR-024, current decision/trace operations and later off-host overlays, relevant normal
deploy runbook, present implementation/tests and operations commit history.
Repository AGENTS.md applies; checkout `.agents` and `.agents/skills` are absent.
No skill requiring a separate workflow or sub-agent applies to this code audit.

C13, “Retention and evidence”, explicitly requires protection of current, rollback/
activation targets, **four newest published releases**, and every published release
younger than seven days. Incomplete candidates have a separate one-day grace.
Neither ADR-024 group/credential corrections nor later off-host backup authorization
changes this retention floor. The original Phase 8 report describes protected cleanup
as implemented; current tests do not establish that claim for mixed incomplete/published
directories. This audit does not dispute that the historical tests ran as reported.

Later differences are scoped historical changes, not automatically findings: off-host
backup was a port in Phase 8 and later gained an explicitly selected private Git adapter
and readback gate (`4f15a34`, `4abaaa2`); group/ACL corrections are recorded in ADR-024.
Their current complete correctness has not been independently audited here.

## Reproduced finding A8-M1

- `src/discordbot/operations/adapters/retention.py:18` slices all directories to four
  before filtering for published manifests. The public CLI cleanup path calls this
  function (`operations/adapters/cli.py`, cleanup branch).
- `src/discordbot/operations/adapters/deployment.py:169` independently counts all
  directories in its four-entry protection set. This is actual post-deploy retention.
- The standalone cleanup implementation dates to Phase 8 commit `4a0ddb2`; this is
  a missed original contract edge, not a newly introduced audit modification.

Exact synthetic arrangement: one active release, four newer valid published releases
aged 10–13 days, and zero or four still-in-grace incomplete `.building` directories.
Nine total directories remain below the sixteen-release admission cap. Each published
manifest passes the actual `ReleaseStore.validate` before cleanup. The active pointer
is older, so its independent protection does not consume the four-publication floor.

Both no-incomplete controls PASS. With four incomplete directories, both entrypoints
delete **all four** valid published alternatives while preserving active and incomplete
directories. Assertion output names `published-0` through `published-3`. This removes
the promised retained recovery alternatives; active release preservation alone does
not satisfy the four-publication contract. No production deletion occurred.

The probe uses existing synthetic manifest fixtures and the documented Windows link
model; `os.replace`, directory aging and deletion are real but confined to pytest
temporary paths. Its clock is fixed only to make age ordering deterministic. It invokes
real retention methods, not a reimplementation. No assertion weakening, xfail or skip.
The post-deploy method is invoked directly without running deployment or services.

## Fresh evidence

| Evidence | PASS | FAIL | SKIP | Scope |
| --- | ---: | ---: | ---: | --- |
| Existing focused operations tests | 64 | 0 | 0 | Seven files, strict runtime/unraisable warnings |
| Independent retention probe | 2 | 2 | 0 | Two controls and two A8-M1 RED cases |
| Distinct total | **66** | **2** | **0** | No repeats or historical results included |

Existing files: `test_assets.py`, `test_build.py`, `test_filesystem.py`,
`test_deployment.py`, `test_pipeline.py`, `test_recovery.py`, `test_retention.py` under
`tests/integration/operations/`. Result: 64 passed in 7.38s. Probe: 2 failed, 2 passed
in 1.52s. XML receipts: [focused](a8-focused-results.xml), [RED](a8-retention-results.xml).
RED XML traceback trailing whitespace was normalized for Git; assertions/results unchanged.
Exact executable probe: [a8-retention-probe.py](a8-retention-probe.py).

Commands (PowerShell, repository root):

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests/integration/operations/test_assets.py tests/integration/operations/test_build.py tests/integration/operations/test_filesystem.py tests/integration/operations/test_deployment.py tests/integration/operations/test_pipeline.py tests/integration/operations/test_recovery.py tests/integration/operations/test_retention.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -p no:cacheprovider --junitxml=docs/rebuild/final-audit/a8-focused-results.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8-retention-probe.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -p no:cacheprovider --junitxml=docs/rebuild/final-audit/a8-retention-results.xml
```

Before running, reviewed root credential-blocking conftest, temporary legacy DB fixture,
and all seven selected test files, including fake build commands/services, temporary
SQLite/generated keys and cleanup. No real package install, service or network call.
The separate probe uses only root credential guard and temporary filesystem fixtures.
Initial `rg` and `python` command aliases were unavailable; existing `.venv` Python was
used without installation. These command-discovery failures are not test failures.

## Gate disposition and exact resume boundary

| Gate | Current evidence / remaining work |
| --- | --- |
| Immutable identity, offline pins, source exclusion, build failure | Selected existing tests PASS; full source/export/bounds review still pending |
| Lock exclusion, pointer failure, tamper/path escape | Existing tests PASS; Windows link model only |
| Deploy order, rollback once, cancellation, initial-deploy failure | Existing synthetic tests PASS; full real runner/service/manual path review pending |
| Backup encryption, fallback, invalid data, promotion guards | Existing temporary SQLite tests PASS; broader cancellation/retention/remote/CLI review pending |
| Published release retention | **FAIL A8-M1**, two entrypoints; repair and unchanged independent rerun required |
| Units/timer/polkit | Static asset tests and selected source inspection only; actual systemd/polkit not run |
| Credentials/config, manual inbox, health/telemetry/audit bounds | Complete independent gate review/tests not run in this microphase |
| Later Phase 9/10 corrections and recorded E1/E2 recovery | Partial routing only; exact claim-to-evidence reconciliation pending, no inherited blanket PASS |
| Architecture/full regression | Not run after material stop; no clean whole-suite claim |
| Linux atomicity/fsync/permissions/cgroup, ARM64 and live/Pi RPO/RTO | Not run, no fresh host claim; use separately authorized isolated Linux proof and documentary reconciliation |

Do not resume remaining gates before supervisor review of A8-M1 and separately
authorized remediation. Repair scope should cover both retention entrypoints, preserve
current/rollback/activation and age/admission guards, and pass this unchanged probe.
Then perform fresh independent A8 verification and finish every pending gate above.
No second microphase is authorized by this report.

Known inventory and missing-Deno failures, existing Linux/systemd skips, audioop and A3
limitations remain unchanged. A7V2's 1402 PASS / 2 known FAIL / 27 SKIP and separate
2100 synthetic soak executions are historical A7 evidence, not fresh A8 coverage.

## Ownership, safety and rollback

[Entry inventory](a8-entry-inventory.json) records all 70 inherited contents:
11 modified / 59 untracked, empty index. Only A8 evidence and narrow current-authority
additions are owned. Document index remains unchanged. No product code, existing tests, schema, dependencies or contracts
were changed. Scoped preservation/exit evidence is in [a8-exit-evidence.json](a8-exit-evidence.json).
If uncommitted, remove only the listed new A8 files and reverse only AX / Phase 8 ledger additions; never reset shared documents. A local evidence commit, if made,
has its exact ID in the final handoff; no push or history rewrite is authorized.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and production pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched. No Pi/production
connection, real DB/backup/credential access, deploy, restore, systemd/Cloudflare change,
remote publication, release/history cleanup, PC shutdown or My Food work occurred.
Only synthetic fixtures were deleted by retention verification. Both owned pytest
sessions exited; no server/browser automation or persistent worker was started.
