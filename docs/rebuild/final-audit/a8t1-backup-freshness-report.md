# A8T1 - scoped backup telemetry audit reopening

Date: 2026-10-04. Audited HEAD `3dc37e05c811d337b5515d00cbdd6841916a1b4d`,
branch `codex/rebuild-v2`. **A8-M4 MATERIAL OPEN; Phase 8 FAIL for the reopened
backup telemetry freshness gate only.** Supervisor accepted this material finding
and authorized records, synthetic evidence and a reviewed local commit; no fix.
The current ledger and A8 reports had no M4 or later material ID at entry.

## Finding and gate ownership

`operations/adapters/probe.py:37` stops scheduling after `policy.hard`. Backup
metadata sampling lives in the same factory (`:67-73`); `gauges()` returns cached
`backup_age_seconds` and derives `backup_rpo_exceeded` from it (`:85-86`). A hard
probe therefore freezes both metrics, including a falsely reassuring RPO zero,
without an observation timestamp or stale/unknown indication. The input is
`latest.json` filesystem mtime, not independently verified remote backup freshness.
New metadata publication is also invisible after the latch.

This is the telemetry portion of A8V3's **Manual/health/telemetry/audit** row in the
[prior complete gate matrix](a8v3-phase-8-verification-report.md). The wrong value
appears while the process can still serve metrics. This materially misrepresents a
named operational safety signal; readiness remains false, so it is not evidence
that pair readiness or deployment acceptance can be bypassed.

| Gate/finding | Current disposition |
| --- | --- |
| A8 backup age/RPO freshness, within Manual/health/telemetry/audit | FAIL; new A8-M4 MATERIAL OPEN |
| Other manual, health, identity, audit and bounded-telemetry assertions | Prior evidence retained; not reopened or freshly re-certified |
| A8-M1 release retention, M2 backup retention, M3 release inventory | Independently CLOSED; closures and original evidence unchanged |
| Other A8V3 gate rows and their host/performance limitations | Prior evidence retained unchanged |
| A0-A7 | Prior PASS retained |
| A9 | Separately BLOCKED, B1/B2/B3 and D1 unchanged; no host/soak waiver |

## Governing contract and intended terminal policy

- [C15 Readiness, signals and observability](../phases/phase-08/operations-contract.md#readiness-signals-and-observability)
  requires five-second supervised DB samples, stale readiness failure after 15s,
  and backup age/RPO observability. [B17 Health model](../baseline/17-observability.md#health-model)
  distinguishes process liveness from dependencies and requires dependency status
  and last-success timing; its alert policy includes backup RPO violations.
- The later [H2 precise safety policy](../phase-10-full-sweep-report.md#minimal-repair-and-precise-safety-policy)
  expressly allows one fully classified configure-stage BUSY, two healthy probes
  within 15s, then terminal handling for recurrence within 60s. It says terminal
  failure latches readiness and stops further probe scheduling. Current policy
  accepts another bounded BUSY only when elapsed time is **greater than** 60s.
- That latch and absence of automatic recovery are **intended**, not A8-M4.
  H2 does not waive backup telemetry freshness or authorize a frozen healthy RPO.
  Preserve H2 unchanged. Do not enable retries, reset the latch, change journal
  mode, extend thresholds or reinterpret the contract to make the audit pass.
- [Health troubleshooting](../../../deploy/runbooks/health-troubleshooting.md)
  says reset/restart only after correcting the cause. Fresh process construction
  creates a fresh policy; the current object never clears `hard`. No automated
  recovery or operational restart is authorized here. B17 permits responsive
  liveness during dependency failure. Public Watch readiness uses `service.ready()`;
  internal Watch readiness additionally checks `probe.ready()` and listeners.

## Reproduction and negative control

The [retained discovery evidence](a8t1-discovery-evidence.json) copies the original
temporary results and source-script hashes. The [portable probe](a8t1-backup-freshness-probe.py)
adapts that driver to repository-relative paths, independently loads historical
policy from local Git, adds a healthy control and explicit freshness assertions.
`probe.py` and `probe_policy.py` are unchanged between recorded production source
`8e9018d4b8061cde6006eee47fa4103522f77718` and the audited candidate (newline-normalized).
The historical module uses current supporting interfaces; this is not a full
historical checkout execution. Historical/current policy and factory are exercised.

| Synthetic sequence, both sources | Observed result |
| --- | --- |
| BUSY at 5s, healthy at 10/15s, BUSY at 20s | contention, recovered, hard failure; four calls, no next factory; ready false |
| Advance clock by seven hours; driver now healthy | Actual metadata age 25,320s; reported 120s; RPO exceeded 0 |
| Publish new synthetic metadata after hard | Reported age still 120s, stat calls remain four |
| Negative control: healthy fourth probe, then execute pending healthy sample at advanced time | Correct age 25,320s and RPO 1; new metadata sampled five seconds later reports 5s |

The control isolates sampling cessation: the same clock, metadata and unchanged
metric formula work while samples continue. It does not modify production logic
or claim seven hours of real elapsed soak. The actual factory and done-callback
run through synchronous fake Futures, clock, driver and executor; no asyncio loop,
socket, real backup, DB or background worker is needed. Every Future is completed
or cancelled and every pending synthetic handle is discarded before return.

Prior discovery also ran six real temporary SQLite journal/transaction cases with
two connections in one process: DELETE+EXCLUSIVE produced configure BUSY5 and clean
close; the other five passed, and all six passed after release. This establishes
a possible cause, not the live lock holder, transaction duration or journal mode.
That six-case receipt is retained prior evidence, not part of fresh test counts.
Discovery's initial Windows asyncio socketpair was blocked by its own no-network
guard; the driver was made synchronous, then its fake cleanup ordering corrected.
Those harness failures were not application findings or platform approval denials.

## Fresh validation and reproducibility

From the repository root, use existing `.venv/Scripts/python.exe -B -m pytest -q
-p no:cacheprovider -o junit_family=xunit1` with these explicit selections:

- `docs/rebuild/final-audit/a8t1-backup-freshness-probe.py`: two policy/control PASS,
  two expected freshness contract FAIL (historical and current). **Not a green audit.**
- `tests/integration/operations/test_probe_policy.py::test_one_busy_requires_two_healthy_probes_and_a_60_second_window`,
  `::test_other_classes_never_get_transient_policy`, and
  `::test_generic_repeated_stale_and_expired_are_hard`: 13 PASS.
- `tests/architecture/test_rebuild_documentation.py::test_heading_anchor_preserves_spaces_around_removed_punctuation`
  and `::test_all_relative_rebuild_document_links_resolve`: two PASS.

[Behavior XML](a8t1-probe-results.xml), [documentation XML](a8t1-doc-results.xml),
and [fresh observations](a8t1-freshness-evidence.json): **17 PASS / 2 FAIL / 0 SKIP**
distinct cases, including both historical and current cases. No broad/full suite.
Execution additionally installed the root credential guard and rejected socket
connect/bind/DNS and operational-data opens. There was no external call or install.
This small record-only addition does not resolve inherited inventory/Deno/Linux/
systemd/audioop/A3 limitations, production-scale backup timing or A9 blockers.

## Ownership, rollback and stop boundary

[Entry inventory](a8t1-entry-inventory.json) records 11 modified / 59 untracked,
empty Git index and all 70 inherited hashes. [Ownership receipt](a8t1-ownership-receipt.json)
verifies 67 exact contents plus three reversible owned authority changes. Only the
new A8T1 evidence/report and this append/Phase8-row change are commit-owned. The
inherited untracked document index receives a compact link appendix in the working
tree; [its exact appendix patch](a8t1-document-index.patch) is committed instead of
adopting the entire inherited file. Tracked authority staging uses HEAD plus only
the owned deltas, preserving inherited unstaged content. Staged diff/check are
reviewed before the local Conventional Commit; its exact hash is in the handoff.
Rollback: revert only that audit commit's owned changes with inherited work preserved,
and reverse the saved index appendix patch if still present. No data rollback.

No implementation, policy, production source/pin, DB, service, credentials,
dependencies, exports or other projects changed. Prior historical reports are
untouched; this later overlay supersedes only the affected A8 PASS claim. Test
processes exited, owned temporary test data removed, and no pending worker remains.

**STOP for separate A8-M4 remediation authorization, then independent verification.**
Remediation must provide truthful age/RPO freshness or explicit unavailable status
while keeping the H2 terminal latch intact. Live backup freshness, lock ownership,
current DB usability and user impact are unknown; supplied live diagnostic context
is not independently refreshed here. A9 remains BLOCKED; no A10/Integrated/Phase11,
fix/deploy, SSH, restart, push or production action starts in this microphase.
