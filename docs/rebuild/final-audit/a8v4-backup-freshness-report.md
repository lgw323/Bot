# A8V4 - independent backup age/RPO freshness verification

Date: 2026-10-04. Audited entry HEAD `26d9d5c25e60fd1a0c73c25b4eab60b27075d14a`,
branch `codex/rebuild-v2`; M4 implementation `0640f70b37a60c614f4658d4c7cce7f55b51d756`.
The final local audit commit hash is supplied in the handoff, avoiding a self-reference.

**A8-M4 independently CLOSED; Phase 8 PASS restored for its original repository
operations scope.** M1/M2/M3 remain CLOSED. No new material finding. A9 remains
separately BLOCKED on B1/B2/B3/D1. This is neither production acceptance nor a
clean full-suite claim.

## Authority and contract interpretation

Read root AGENTS, active-state through BG, Phase 8/9 ledger rows, document index,
[original A8T1 finding and unchanged probe](a8t1-backup-freshness-report.md),
[A8R4 remediation](a8r4-backup-freshness-report.md), and the
[A8V3 complete gate matrix](a8v3-phase-8-verification-report.md#complete-scoped-gate-disposition).
No applicable nested AGENTS, local skill, `.agents` or `.codex` directory was found;
no specialized skill or subagent was needed. `rg` is unavailable; bounded Python and
PowerShell reads were used. Repository status matched the assignment.

The original C15 text was read from pre-M4 `ecc7674a59150c280bca15031f51eb7ec1015a7a`,
not inferred from remediation documentation. It requires supervised five-second
sampling, stale readiness failure after 15 seconds, and backup age/RPO signals.
[B17](../baseline/17-observability.md#health-model) permits responsive liveness during
dependency failure and distinguishes unknown dependency observations. Later
[H2](../phase-10-full-sweep-report.md#minimal-repair-and-precise-safety-policy) allows
only fully classified configure-stage numeric BUSY5, two consecutive healthy probes
within strictly less than 15 seconds, and another bounded BUSY only after more than
60 seconds. Terminal failure latches readiness and stops further DB scheduling.
That deliberate policy is preserved, including no automatic recovery.

M4 required truthful observation or explicit unknown; it never required actual
current backup age after sampling stops. The existing pair `backup_age_seconds=-1`
and `backup_rpo_exceeded=1` now means unavailable knowledge and a fail-closed RPO
signal. RPO 1 alone is **not proof that a known archive is older than six hours**.
The age sentinel disambiguates unknown from a measured age over the threshold.
[The operator runbook](../../../deploy/runbooks/backup-verification.md) explicitly
explains that distinction and publication after latch. This closes the false-safe
cache without changing H2 or inventing a new recovery deadline or retry policy.

While a sampler task is active, age advances with the wall clock from the last
observed local filesystem mtime. Replacement/removal becomes visible at the next
normal sample, not immediately. Gauge reads never stat metadata, invoke DB work,
submit executor work or schedule a task. A completed/cancelled/failed task, stop,
hard latch or absent/invalid timestamp returns unknown. Exactly six hours remains
RPO 0; strictly greater becomes 1; the preexisting future-mtime zero clamp remains.
Readiness on generic task termination retains the existing 15-second stale rule;
M4 does not add a new immediate readiness latch for arbitrary task exceptions.

The signal does **not** parse JSON, validate an archive, attest remote publication,
or prove recoverability. A malformed JSON file with a valid mtime still produces
a local-age observation, as before; an independent test makes that boundary explicit.
Malformed/nonfinite timestamp values are separately fail-closed. This is the
original A8T1 input definition, not a new waiver of backup validation contracts.

## Independent baseline/current proof

[Baseline runner](a8v4-baseline-runner.py) loads the exact pre-M4 probe and policy
from local Git into memory, with current supporting interfaces. It runs the
unchanged original A8T1 assertions; no worktree source, fixture or assertion is
replaced. This is an old-module negative control, not a full historical checkout.

| Same synthetic BUSY/healthy/healthy/BUSY sequence | Pre-M4 and production-history module | Current candidate |
| --- | --- | --- |
| Four DB probes; terminal readiness false; no next factory | Preserved | Preserved |
| Seven synthetic hours later; actual metadata age 25,320s | Cached 120s / RPO 0, contract RED | Unknown -1 / RPO 1, PASS |
| Publish new metadata after terminal | Cached 120s remains | Unknown stays -1; no extra stat/DB |
| Healthy control at advanced time | 25,320s / RPO 1 | 25,320s / RPO 1 |
| Next healthy sample after new metadata | Age 5s | Age 5s |

[Numeric observations](a8v4-freshness-evidence.json) preserve events, counts,
timestamps, pending handles and completed-future assertions. Original probe bytes
and H2 policy remain unchanged. Both history and baseline deliberately retain their
freshness failures; no xfail/skip or assertion weakening makes them green.

The first baseline loader replaced only the class, leaving its globals detached
from the original driver's asyncio substitution. That produced two harness errors
plus the historical expected failure ([initial receipt](a8v4-baseline-harness-error.xml)).
The loader now binds the entire historical module, so the unchanged driver patches
the correct globals. The corrected baseline is 2 PASS / 2 expected contract FAIL;
the current run is 3 PASS / 1 historical expected FAIL. No implementation defect
was inferred from the loader mistake and no product change was made.

## Actual HTTP, lifecycle and unaffected gates

[Seven independent cases](a8v4-contract-probe.py) use actual ProcessRuntime,
TaskSupervisor, bounded executor, temporary filesystem atomic replacement, and
the production `health_app` via ASGITransport. The DB driver is synthetic; only
the five-second sleep is replaced by explicit permits. Actual task scheduling,
completion callbacks, cancellation and runtime shutdown execute normally.

They verify HTTP startup unknown, wall-clock aging with no additional DB calls,
the exact six-hour boundary, metadata replacement/removal, classified BUSY
recurrence, late malformed publication/removal after latch, and cancelled,
exceptional, stopped and runtime-shutdown task termination. Latched HTTP remains
live and readiness 503; metrics expose -1/1 after seven synthetic hours without
another probe. Each fixture drains tasks/executor and asserts clean shutdown.
The separate malformed-JSON control demonstrates the local-mtime-only boundary.

Source review confirms both production Discord and Watch compositions pass
`settings.backups / "latest.json"`, `probe.gauges`, and their existing readiness
predicates into the same internal HTTP adapter. No sockets/listeners or real
composition credentials are opened. Public Watch readiness remains a distinct
service predicate; no public route behavior is redefined by this audit.

The unchanged 30 remediation regressions additionally cover unavailable/no-path
metadata, OSError, bool/string/None/NaN/infinite mtime, future-time clamp, blocked
metadata cancellation, and exact stat/probe counts. M1 original4+independent4,
M2 original2+independent2, and M3 original2 run unchanged alongside their 78/36/59
remediation cases and H2/health/runtime/telemetry checks.

Only the probe, its new regression file and backup runbook differ under the
operations/composition/deploy/test scope since pre-M4. Policy, composition,
retention, inventory, publication, recovery, service configuration, schemas and
formats are unchanged. A8V3's unaffected gate evidence is retained in its original
scope; its Linux results are prior evidence, not newly executed in A8V4.

## Receipts and reproducibility

Use existing `.venv/Scripts/python.exe -B`, `PYTHONIOENCODING=utf-8`, and the
unchanged [guarded runner](a8r4-test-runner.py). Common flags are `-q --tb=short
-p no:cacheprovider -o junit_family=xunit1 --basetemp=<new task-owned Temp path>
--junitxml=<receipt>`. Current independent/focused/full runs also use
`-W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.
The runner installs the root credential boundary, denies operational data access,
and rejects application socket/DNS calls. Windows asyncio's stdlib wakeup socketpair
is the sole plumbing exception; HTTP is in process, not a bound server.

- Baseline runner with `a8t1-backup-freshness-probe.py`: [2 PASS/2 expected FAIL](a8v4-baseline-results.xml).
- Guarded runner with the same original: [3 PASS/1 historical FAIL](a8v4-original-results.xml).
- Guarded runner with `a8v4-contract-probe.py`: [7 PASS](a8v4-independent-results.xml).
- Focused selection: `test_backup_freshness`, `test_backup_retention_contract`,
  `test_operational_telemetry`, `test_probe_policy`, `test_release_inventory_contract`,
  `test_retention_contract`, `test_runtime` under `tests/integration/operations/`, plus
  `a8-retention-probe.py`, `a8v1-retention-probe.py`, `a8v1-backup-probe.py`,
  `a8v2-backup-probe.py`, `a8v2-release-probe.py` under this audit directory.
- Full selection: `tests/`.
- Final documentation: the unchanged `test_heading_anchor_preserves_spaces_around_removed_punctuation`
  and `test_all_relative_rebuild_document_links_resolve` in
  `tests/architecture/test_rebuild_documentation.py`.

[Prior receipt check](a8v4-prior-receipt-check.json) independently recomputes all
seven A8R4 XML hashes/counts and its focused/regression union of 250 passing
identities (30 new regression identities), rather than trusting the report.
Full A8R4 is confirmed as 1592 PASS / 2 FAIL / 27 SKIP; its two failures are the
stale rebuild-document inventory and unavailable Deno.

| Fresh evidence | Result | Distinctness |
| --- | --- | --- |
| [Focused contracts](a8v4-focused-results.xml) | 264 PASS / 0 FAIL / 0 SKIP | 250 existing test identities, including all 30 M4 regressions, plus 14 unchanged M1-M3 audit probes |
| Independent real-task/filesystem/HTTP cases | 7 PASS / 0 FAIL / 0 SKIP | New identities outside `tests/` |
| Unchanged original current cases | 2 PASS | Historical pair excluded from current totals |
| [Full suite](a8v4-full-results.xml) | 1592 PASS / 2 known FAIL / 27 SKIP | 231.42 seconds; includes all 250 focused repository identities |
| Final link/anchor checks | 2 PASS | Already included in full suite |

[Count/hash receipt](a8v4-test-evidence.json) deduplicates by classname and test
name. The fresh current union is **1615 PASS / 2 FAIL / 27 SKIP / 0 XFAIL**;
264 focused + 7 independent + 2 original-current are 273 passing current cases
before adding the nonoverlapping full-suite cases. Historical comparison is
separately 1 PASS / 1 expected contract FAIL. Pre-M4 baseline and the initial
loader failure are diagnostic runs, not current-case successes or extra identities.
Numeric observation replays are supporting evidence, not additional tests.

The two fresh full-suite failures are exactly
`test_rebuild_documents_are_partitioned_without_loss` (stale audit inventory
allowlist) and `test_pinned_provider_and_runtime_load_without_network` (Deno
unavailable), matching the prior receipt. The 27 Linux/systemd opt-in skips and
one audioop deprecation warning remain. No skip/xfail was added or used to close M4.
XML trailing whitespace is normalized before hashing without changing results.

## Ownership, limits and stop boundary

[Entry inventory](a8v4-entry-inventory.json) records empty index, 11 modified /
59 untracked paths and all 70 inherited hashes. The previous A8R4 preservation
receipt is independently verified as 66 exact contents plus four inverse-owned
document deltas. A8V4 verifies its own preservation as 67 exact hashes plus three
inverse-owned authority deltas in `a8v4-ownership-receipt.json`. This audit owns
only new A8V4 tests/evidence/report and compact
active-state/Phase8-ledger/index appendices. The inherited untracked document index
is not adopted into Git; only its exact appendix patch is committed. Tracked mixed
authority files stage HEAD plus the audit's own deltas; unrelated working bytes
remain unstaged. Staged diff and whitespace checks precede a local Conventional
Commit. No source implementation or existing test/assertion is edited.

Rollback is a scoped revert of the A8V4 audit commit with inherited work preserved,
plus reversing its saved untracked-index appendix patch. No data rollback applies.
Production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched.
No SSH/Pi, network/live provider, production DB/config, restart/deployment, install,
security change, actual backup cleanup, push/reset/bulkstage or other-project action.

Known inventory/Deno/Linux/systemd/audioop/A3 limits remain explicit. Synthetic
clocks are not elapsed soak; small temporary SQLite/encryption/restore tests do not
prove the 180-second production backup budget, host/ARM64 behavior, power loss,
live backup validity or RPO/RTO. No clean full-suite or live acceptance claim.
A0-A7 and unaffected A8V3 gates retain their previous scope. A9 remains separately
BLOCKED on B1/B2/B3/D1 regardless of M4 closure; friend activation remains HELD.
STOP after A8V4 for supervisor review. No A9 campaign, A10, Integrated Audit or
Phase11 starts; any such work requires a separate assignment and appropriate scope.

All seven pytest sessions (including the initial baseline loader failure) exited; the
independent fixtures drained real tasks, executors and HTTP clients. Named A8V4
Temp directories were removed after verifying their resolved Temp boundaries.
No persistent service, test worker or pending test write remains. The temporary
staging patch is removed after the local commit; final residual/index checks are
reported with its exact HEAD in the handoff.
