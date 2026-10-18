# A8R4 - A8-M4 backup age/RPO freshness remediation

Date: 2026-10-04. Entry HEAD `ecc7674a59150c280bca15031f51eb7ec1015a7a`,
branch `codex/rebuild-v2`. Local remediation only. **Phase 8 stays FAIL;
A8-M4 is remediated pending independent verification, not CLOSED.** M1/M2/M3
remain independently CLOSED. A9 remains separately BLOCKED (B1/B2/B3/D1).

Implementation commit: `0640f70b37a60c614f4658d4c7cce7f55b51d756`
(`fix: invalidate unavailable backup freshness observations`). The separate evidence
commit/final HEAD is returned in the handoff to avoid a self-referential report hash.

## Root cause and selected contract-preserving correction

The scheduled DB probe also sampled local `latest.json` mtime and cached a computed
age. The intended H2 terminal latch stops scheduling that task. Both age and RPO
therefore stayed at the last apparently healthy values indefinitely, and publication
or removal of metadata became invisible. The unchanged original A8T1 probe reproduced
actual age 25,320 seconds versus reported 120/RPO 0 before any implementation edit.

[C15 observability](../phases/phase-08/operations-contract.md#readiness-signals-and-observability)
requires backup age/RPO signals; [H2](../phase-10-full-sweep-report.md#minimal-repair-and-precise-safety-policy)
requires terminal recurrence at <=60 seconds to latch readiness and stop DB probes.
[A8T1](a8t1-backup-freshness-report.md) explicitly accepts truthful age or explicit
unknown while retaining H2. Existing code already represents missing observations
as age -1 / RPO 1. This remediation reuses that pair for an unavailable sampler,
rather than adding a metric, deadline, sampler, DB retry or recovery policy.

- Store the sampled mtime and calculate age at gauge observation, preserving the
  existing zero clamp and strict greater-than-six-hours threshold. A healthy sample
  still sees metadata replacement/removal on its normal five-second schedule.
- Return age -1 / RPO 1 before sampling, on missing/invalid mtime, when the task is
  finished/cancelled/failed, after stop, or while the policy is hard-latched. Even a
  new backup after hard latch remains explicitly unknown; no fresh stat is claimed.
- Gauge reads do no filesystem, DB or executor work. No new background task, capacity
  requirement, shutdown obligation, metric label or configuration is introduced.
- Preserve DB scheduling, readiness/liveness, the >60-second BUSY eligibility rule,
  retention/inventory/backup publication and all on-disk formats. The historical
  production source and pin are untouched. JSON metadata contents and remote backup
  validity are not newly inspected; the input remains local filesystem mtime.

Only `operations/adapters/probe.py` changes runtime behavior. Its `backup_age` read
interface remains available as a property; repository-wide references showed no
external writers. Operations contract, backup runbook and changelog explain the
existing unknown representation's application to unavailable observations.

## Reproduction, regressions and receipts

Use the existing `.venv/Scripts/python.exe -B` with
`docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider
-o junit_family=xunit1 --junitxml=<receipt>` and the selections below. Final
regression/full runs additionally promote RuntimeWarning and pytest unraisable
warnings to errors. The runner installs the root credential boundary, denies
operational data opens/SQLite connections and denies application socket/DNS calls.
Windows stdlib socketpair is permitted only for asyncio's internal wakeup plumbing;
there is no application network, external provider or service connection.

| Evidence | Result | Scope |
| --- | --- | --- |
| [Unchanged original RED](a8r4-original-red.xml) | 2 PASS / 2 FAIL / 0 SKIP | Original `a8t1-backup-freshness-probe.py`, before implementation; historical and current freshness failures, both healthy/latch controls pass |
| [New regression RED](a8r4-regression-red.xml) | 9 PASS / 18 FAIL / 0 SKIP | First 27 new regression identities, unchanged implementation |
| [Unchanged original after](a8r4-original-after.xml) | 3 PASS / 1 FAIL / 0 SKIP | Current original freshness and control now PASS; historical freshness deliberately remains RED, historical control PASS |
| [Focused affected contracts](a8r4-focused-green.xml) | 249 PASS / 0 FAIL / 0 SKIP | 29 new regressions, probe policy, operational telemetry/runtime, M1/M2/M3 retention/inventory suites |
| [Final new regressions](a8r4-regression-green.xml) | 30 PASS / 0 FAIL / 0 SKIP | Adds in-process HTTP live/ready/metrics proof; includes 2 actual temporary-filesystem cases |
| [Full suite](a8r4-full-results.xml) | 1592 PASS / 2 FAIL / 27 SKIP | 239.92s, two inherited inventory/Deno failures; audioop deprecation warning |
| [Final documentation](a8r4-doc-results.xml) | 2 PASS / 0 FAIL / 0 SKIP | Link/anchor checks after final documentation updates; identities already in full suite |

The two full-suite failures are `test_rebuild_documents_are_partitioned_without_loss`
(stale audit-document allowlist) and `test_pinned_provider_and_runtime_load_without_network`
(Deno unavailable). No full-suite green claim. The 27 opt-in Linux/systemd skips are
unchanged; no Linux/systemd execution was attempted here. Focused plus final new
regressions contain 250 distinct passing identities, all also in the full suite.
Including the two unchanged original **current** cases yields **1594 PASS / 2 FAIL /
27 SKIP / 0 XFAIL** distinct current identities. Historical comparison is separately
1 PASS / 1 expected contract FAIL; neither that negative control nor earlier RED or
overlapping reruns is added to the current union. [Count/hash evidence](a8r4-test-evidence.json)
records each receipt and deduplicated identity sets. XML trailing whitespace is
normalized before hashing/staging, without changing case results or assertions.

[Fresh numeric observations](a8r4-freshness-evidence.json) retain historical/current
healthy and latched results. Current latched age is -1/RPO 1 after seven synthetic
hours and after new metadata; DB calls remain exactly four, no pending factory.
Healthy controls report 25,320/RPO 1 then age 5 after publication. All fake futures
are finished/cancelled. The original A8T1 probe/assertions and historical source
are unchanged. No skip, xfail, weakened assertion or fixture outcome hides a failure.

The 30 new cases cover wall-clock passage, RPO boundary/future-time clamp, metadata
publication/removal, no metadata, OSError and invalid/nonfinite timestamp values,
healthy/hard states, task exception/cancellation/stop, cancellation while sampling,
cleanup and no extra DB/stat calls. Two use real temporary files and atomic replace;
HTTP checks use ASGI transport without sockets. The remaining dependencies include
temporary SQLite, encryption, restore and local filesystem retention regressions,
not production backups or real elapsed soak.

Harness-only corrections before implementation: the first async run failed setup
because this Python names its stdlib socketpair helper `_fallback_socketpair`
(27 setup errors); the guard now recognizes that helper. An initial new boundary
assertion compared fractional float arithmetic exactly; it now uses `pytest.approx`
for age while retaining exact RPO assertions. Fixture finalization was strengthened
to cancel all synthetic futures even on RED. Final pre-fix regression receipt above
was regenerated after those harness corrections. The original A8T1 test was never
adapted. Two changelog insertion attempts detected mixed newlines and failed before
writing; the owned insertion preserves the inherited bytes.
The first documentation link check ran before its own XML and the count receipt
existed (1 PASS/1 FAIL); after generating those artifacts the unchanged checks
passed 2/2. This was artifact ordering, not a product failure or waived assertion.

## Ownership, limits, rollback and stop boundary

[Entry inventory](a8r4-entry-inventory.json) records all 70 inherited contents
(11 modified / 59 untracked), exact hashes and empty index.
[Ownership verification](a8r4-ownership-receipt.json) confirms 66 exact hashes plus
four inverse-owned deltas (changelog, active-state, ledger, document index).
No `.agents` directory
or nested repository AGENTS/skill file exists; root AGENTS applies. `rg` is absent,
so bounded PowerShell/Python searches were used. An initial attempt to enumerate
the absent `.agents` directory expanded into denied inherited scratch directories;
no protected file was read and the search was replaced with explicit existence checks.

Owned staging must retain the inherited edits: clean source/tests/docs are staged
by exact path; tracked dirty files stage HEAD plus only the owned delta. The inherited
untracked document index gets only an appendix, recorded as a standalone patch rather
than adopting its contents: [exact appendix patch](a8r4-document-index.patch).
Original audit reports, exports, retention/inventory fixes
and production evidence are preserved.

Rollback: revert only the implementation commit's source/tests/contract/runbook and
owned changelog insertion, preserving unrelated working-tree changes. Revert the
separate evidence commit's owned routing/report additions if desired; inverse the
saved document-index appendix patch in the inherited file. No DB/data rollback.

Known inventory/Deno/Linux/systemd/audioop/A3 limitations, production-scale 180-second
backup budget, power-loss, host/ARM64 behavior and live RPO/RTO remain unresolved by
this local phase. Production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched. No SSH, network,
live/Pi access, actual DB/backup/archive manipulation, credential access, install,
service/security/configuration change, restart/deployment, push/force-push or other
project action is authorized or performed.

Default-sandbox Git index writes were denied by filesystem permissions. Approved
escalated Git staging/commits proceeded; the elevated process could not read the
private temporary patch, so an identical patch was copied into the workspace.
No automatic approval-review rejection occurred. No broad staging or index reset
was used. Staged diff/check were reviewed for each local commit.

All owned pytest/child sessions exited and tests drained their synthetic tasks,
executors and DB handles. The explicitly named A8R4 temporary workspace and the
three remaining default pytest directories attributable to these runs were removed
after checking their resolved Temp boundaries. Workspace staging helpers are removed
at completion; only committed evidence and the intended inherited index appendix
remain. No persistent service, background worker or pending write is left running.

**STOP after local remediation for separate independent A8-M4 verification.** That
verification must retain the unchanged RED negative control, healthy and unavailable
telemetry semantics, terminal recurrence/liveness/readiness, cancellation and zero
extra DB probes. It alone may close M4 and reconcile the Phase 8 gate. No independent
audit, A9 campaign, Integrated Audit or Phase11 begins here; friend activation HELD.
