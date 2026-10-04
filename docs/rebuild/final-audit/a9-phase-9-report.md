# A9 - independent Phase 9 staging audit

Date: 2026-10-04. **Verdict: BLOCKED; repository/synthetic checks PASS, required
staging acceptance only PARTIAL.** No new MATERIAL implementation defect was
reproduced. Missing evidence is not a successful gate or an implementation FAIL.
STOP for supervisor review; no remediation, A10, Integrated Audit or Phase 11.

Audited branch `codex/rebuild-v2`, entry/code HEAD
`27c02140576a5ff288ee4d0f47d7e5d9c885dc2f`, including inherited working-tree contents.
Production remains a distinct recorded identity:
`8e9018d4b8061cde6006eee47fa4103522f77718` /
`r-8e9018d4b8061cde-3dac82a792fad576`. No current production observation occurred.

## Scope reconstructed from current authority

Entry [inventory](a9-entry-inventory.json) confirms **11 modified / 59 untracked
files, 70 inherited contents, empty index**. Root AGENTS.md applies; no .agents or
.codex directory or nested AGENTS.md/SKILL.md was found in the inspected source,
deploy, tests and documentation trees. No subagent or external skill was invoked.

Routing was read in the required order: active-state through BD, Phase 9 ledger
row, document index, original contracts, historical report, scoped later evidence,
then relevant current implementation/tests. Historical handoff exports are not
authority and were not modified. A0-A8 PASS stays within its documented scopes.

Governing requirements are [B20 Phase 9](../baseline/20-migration-plan.md#phases),
[B19 non-functional verification](../baseline/19-testing-strategy.md#non-functional-verification),
[B13 NFRs](../baseline/13-non-functional-requirements.md),
[B11 acceptance](../baseline/11-prd.md), and
[C2 stage gates](../phases/phase-01/concurrency-failure-plan.md#stage-gates).
They require dedicated staging application/guild, sanitized data, clean Pi 5 /
Ubuntu 24.04 ARM64 / Ethernet, idle/normal and peak-times-two (or explicitly approved
capacity) load, fault profiles, at least 24-hour soak, SLO/security/runbook/data
reconciliation approval. B13 numbers are proposals to calibrate on that host,
not already measured production guarantees. ACK p95/p99, local command latency,
DB wait versus execution, event-loop lag, queue pressure and WS relay percentiles
are different measurements from HTTP health latency or last DB probe samples.

[D22](../current/open-questions.md) Q-B02/B06/B08 and Q-H08/Q-M09/M12 preserve
RPO <=6h, approximate RTO 1h, dedicated staging and measured capacity. D23
ADR-016/022/023/024 supplies host, media and operations boundaries; Phase 8's
deferral of host proof does not waive Phase 9's host gate. Feature contracts C3-C15
are dependencies, not a request to repeat A2-A8. The scoped
[trace](../current/requirement-test-trace.md#phase-9-actual-arm64-staging-overlay)
and [historical Phase 9 report](../phases/phase-09/phase-9-report.md) were compared
with their actual test/tool paths. C2 is directly applicable although omitted
from the old Phase 9 ledger governing-ID list; this audit adds that routing ID.

## Required versus verified gates

HISTORICAL means recorded host/user evidence reviewed here, not rerun or silently
transferred to current HEAD. PARTIAL/BLOCKED means the full gate remains open.

| Gate | Required proof | Admissible evidence and disposition |
| --- | --- | --- |
| G1 host / packaging | Clean target Pi inventory, exact ARM64 dependencies, offline immutable build and exercised ABI | HISTORICAL Phase 9 Pi/Ubuntu/Ethernet and 59-wheel build; later 10B provider package change and recorded exact 8e release. Current pins have 61 entries, including Deno/EJS and updated yt-dlp. No fresh ARM64 build/ABI for audited HEAD. PARTIAL. |
| G2 permissions / security | Actual service credential mounts, UID/group/WAL access, least privilege, loopback/internal isolation | HISTORICAL Phase 9 namespace/polkit probes and E3/E4 scopes/routes; fresh mode/ACL positive and rejection tests pass. Windows ACL bytes are not a systemd mount. PARTIAL for current candidate. |
| G3 lifecycle / operations faults | Actual independent processes, stopped/start recovery, coherent identity, failed deploy rollback, reboot and recovery | HISTORICAL Phase 9 synthetic peer + real Watch stop/reboot, smoke-fault rollback and split/missing-peer rejection. A8V3 separately verified current repository operations. New guardian/worker code is not the historical synthetic Discord peer. No current installed-pair or Music checkpoint/voice crash-recovery proof. PARTIAL. |
| G4 bounded concurrency / failure isolation | Summary queue, DB concurrent writes/snapshot, slow peer/caps, Music lifecycle and resource cleanup | Fresh 72 dependent checks PASS using barriers/fakes/temp SQLite and bounded synthetic children; fresh 56 operations/probe/tool checks PASS. Verifies exercised repository paths, not actual combined-host throughput. Repository subgate PASS; host fault/load profile PARTIAL. |
| G5 workload / SLO / capacity | Idle/normal, burst/peak x2 or approved capacity; command/ACK/DB/loop/queue/WS percentiles and resource measurements | Phase 9 640 loopback health requests at concurrency 8 and 69 Pi fake-adapter tests do not measure that workload. E4 records no Watch sessions/clients. No measured peak basis, alternative approved capacity, complete percentile set or owner SLO acceptance found. BLOCKED. |
| G6 soak | At least 24h representative staging workload, no unbounded memory/task/file growth, anomaly disposition | Later 10A actually observed 86,400.135s / 1,438 samples on old synthetic pair. DB failures +12/+17, health missing once and disk free -955,363,328 bytes remain recorded. Corrected 300.171s observation and later 1,800.628s E4 are shorter and different releases/workloads. No clean current representative 24h proof. BLOCKED. |
| G7 live feature / dedicated staging | Dedicated application/guild, approved credentials/origin, actual voice/interaction/browser and safe data | Historical Phase 9 explicitly lacked credentials. Later authorized 10B D-series 30/30 proves scoped Gateway/sync/Summary/human audio/TTS/public Chrome behavior for 8e only. It is production evidence, not proof the dedicated-staging requirement was performed or explicitly waived. No blanket Q-B08 waiver found. PARTIAL; supervisor must resolve acceptance. |
| G8 public Watch path | Approved TLS/public origin, internal ports private, multi-client/reconnect/close behavior | Later Gate30 and E3/E4 establish historical sole loopback9000 origin with internal9001/9010/9011 private. D5/D6/D7 cover real reconnect/multi-client/admin close within recorded limits. Acceptance of refresh changed explicitly for Gates23/26 only. Historical scoped coverage accepted; no current route inspection. |
| G9 recovery / off-host / timing | Encrypted recovery, independent reconciliation, retained points, sustained RPO and RTO under representative size | E1 publication/read-back and E2 independent decrypt/application/schema/count/semantic checks are genuine recorded later evidence; canonical unchanged. E3 enables 4h timer. Synthetic 24h backup age stays below4h; E4 age rises ~503 to2304s without a new backup. Neither proves sustained production RPO/RTO, current retention-scan cost, or fit in unchanged180s backup budget. PARTIAL/BLOCKED for timing. |
| G10 update policy | Approved source/ref and deliberate update behavior | Original absent remote/ref is superseded by recorded approved manual FF push/pins. Later explicit policy keeps auto-update and manual polling OFF. Do not demand enabling it as an A9 prerequisite; no network-update claim or authorization is inferred. Policy disposition resolved; unexecuted automatic-update path remains disclosed. |
| G11 runbook / reconciliation / sign-off | Safe operational procedures, isolated reconciliation and owner acceptance of measured staging exit | Historical operations drills and 10A/E1/E2 reconciliation supply scoped evidence. Local observer guards and error retention independently PASS. No evidence-based acceptance of G5/G6/G9 for current candidate; historical cutover authorization is not a Phase 9 SLO waiver. BLOCKED. |

Power-loss durability remains unproved. It is a retained host/recovery risk, not
something inferred from fsync, reboot or Windows fixtures; no destructive power-loss
test was authorized or added. Actual systemd scopes, ARM64 packaging and production
backup/RPO/RTO remain separate from the 97 real Linux checks in A8V3.

## Findings and contradictions

**A9-B1 - missing workload/SLO acceptance (required evidence blocker).** B19/B20/C2
require the host workload above. No complete profile, peak basis, calibrated
percentiles or approval closing that requirement was located in the scoped current
authority. Normal health/readiness and human functional success do not supply it.

**A9-B2 - soak closure unsupported (required evidence blocker).** The original
60.159s observation is candidly short. Later 24h collection is real historical
evidence, but its report explicitly distinguishes collection completion from clean
soak PASS. The noisy routine logging was repaired in `63c7722`; a five-minute
recheck and E4 do not establish long-term behavior after that or subsequent changes.
Later exactly classified BUSY handling does not retrospectively diagnose the old
unclassified failures. Fresh tests preserve hard failures, limited BUSY recovery
and the distinction between elapsed collection and acceptance.

**A9-B3 - current host/recovery boundary (required evidence blocker).** No current
candidate installed-service/ARM64 proof or representative backup-budget/RPO/RTO
receipt exists in this audit. E1/E2 successfully exercised an older release and
specific artifact; they are not erased and are not extrapolated to sustained
recovery guarantees. A8-M1/M2/M3 closures remain intact, including the explicit
unmeasured cost of validating retained archives under the 180-second budget.

**A9-D1 - unresolved completion routing discrepancy.** Active-state already
records that overall 0-10 implementation completion and the Phase 9 report's
LOCAL/SYNTHETIC VERIFIED / LIVE GATES OPEN have different scopes. Parent Phase 10
final wording claims health/SLO/observation exit satisfaction, but its supplied
measurements do not discharge G5/G6/G9. This is not a new verdict on A10 and does
not invalidate 30 functional PASS receipts. A9 is BLOCKED until the supervisor
explicitly reconciles the unmet requirements/evidence; no silent waiver was made.

Later supersessions are limited: approved 10B cutover and provider repair,
private Bot-Data off-host destination, public Watch route, manual-only update
policy, and Gates23/26 user-approved refresh acceptance. Their exact scopes are
in [P1](../current/phase-10b-active-state.md), [P2](../current/phase-10b-gate-ledger.md),
the [10B runbook override](../phases/phase-10/cutover-runbook.md#current-phase-10b-full-sweep-override-2026-09-19)
and [parent report](../phases/phase-10/phase-10-report.md). They do not explicitly
replace dedicated staging, peak-times-two, 24h workload or production RPO/RTO proof.
Historical pending wording in original reports is not itself a new runtime defect.

No old soak anomaly was reproduced here and no implementation fix was attempted.
No new assertion was weakened, test skipped, failure retried into PASS or fixture
distorted. A9-D1 is a retained authority/evidence discrepancy, not proof of a new
broken production invariant.

## Current implementation and later-regression review

- `deploy/staging/local_discord.py` requires a synthetic marker, uses actual
  SQLite/runtime/listeners and labels `/health/staging` as external_integration=false.
  It deliberately substitutes Gateway and is not production Discord proof.
- `lifecycle_probe.py` samples six times with ten-second waits and compares peer
  PIDs; its ~60s label matches the historical claim. `observe.py` bounds collection,
  rechecks synthetic marker/production-inactive state each iteration and retains
  errors. `inspect_observation.py` reports gaps and sampled bounds, not percentiles.
- Current `configuration.private_mode/read_secret` retains the exact service-only
  ACL validation from opened fd; immutable modes and bytecode guard retain ADR-024.
  Their fresh tests use mode/ACL bytes, fake command runner and temporary source.
- Later `ProbePolicy` admits only configure-stage primary SQLITE_BUSY5 with clean
  close, valid prior readiness and at most one per60s; it requires two scheduled
  healthy probes before15s. Other failures stay hard. Current policy tests and
  telemetry tests preserve this narrower later classification, without claiming
  the old24h error's cause. Full-sweep report sections on probe contention describe
  the subsequent reproduced subtype and explicitly retain retrospective uncertainty.
- Compared production source to HEAD: composition guardian/shutdown, storage,
  engagement, Summary cancellation, Music session/UI, Watch terminal cleanup and
  operations retention/inventory have changed through A2-A8 remediation. Fresh
  dependency tests cover relevant load/lifecycle paths; A0-A8 findings/closures are
  not regraded. Historical installed-release proof cannot certify all these changes.
- Phase 9's59 pin assertion was accurate at that time. The later `7da55db` pin diff
  changes yt-dlp and adds Deno/EJS; old59-wheel evidence is not a current61-wheel
  claim. Known local missing-Deno evidence remains explicit.

## Fresh verification and reproducibility

Repository root `.venv/Scripts/python.exe -B -m pytest`, `--strict-markers
--strict-config -q -o junit_family=xunit1`, with the named files and corresponding
`--junitxml` below. Root conftest blocks repository dotenv reads before collection;
DB fixtures redirect to temporary paths. Providers/sockets/service commands are
fakes; Music child ownership cases substitute short Python children and reap them.

| Receipt | Selection | Result |
| --- | --- | --- |
| [Focused XML](a9-focused-results.xml) | operations/test_staging_entrypoint, test_staging_observation, test_credential_acl, test_build, test_final_readiness_tools, test_operational_telemetry, test_probe_policy (`.py`) | 56 PASS, 2.56s |
| [Independent XML](a9-independent-results.xml) | [a9-staging-probe.py](a9-staging-probe.py) | 7 PASS, 0.21s |
| [Dependent XML](a9-regression-results.xml) | integration/data/test_concurrency; summary/test_requests and test_lifecycle; watch/test_runtime and test_lifecycle; music/test_lifecycle (`.py`) | 72 PASS, 8.06s; audioop warning |
| [Documentation XML](a9-doc-results.xml) | Relative links and heading anchors | 2 PASS, 0.24s |
| **Distinct current union** | 135 behavioral + 2 documentation; disjoint identities, no historical counts added | **137 PASS / 0 FAIL / 0 SKIP / 0 XFAIL** |

Independent checks reject unsafe initial boundaries, stop on marker removal or
production activation, retain partial/error evidence, preserve missing-health and
failure-growth aggregates, and distinguish no samples from success. They execute
production observation functions with temporary synthetic records and patched
systemd/clock/sample calls; no real service or elapsed24h claim.

[Machine evidence](a9-test-evidence.json) records exact identities, commands and
receipt hashes. Full suite was not rerun: no product implementation changed and
the unresolved gate requires unavailable host/workload evidence, not broader unit
coverage. A8V3's **1589 distinct PASS / 2 known FAIL / 27 SKIP**, including97 real
Linux checks, remains **prior evidence**, not A9's fresh total. Known stale inventory
allowlist, missing Deno, Linux/systemd opt-in skips, audioop deprecation and A3-N1
stale wording/A3-I1 empty historical Watch-table limits remain. No clean full-suite,
new Linux, live provider or production acceptance claim is made.

## Preservation, commit and next boundary

Only A9 report/probe/inventory/XML/JSON and owned BE/Phase9 authority deltas change.
The untracked document index, exports, runtime, dependencies, historical reports and
all unrelated inherited contents remain intact. [Ownership receipt](a9-ownership-receipt.json)
checks68 exact inherited hashes and2 inverse-owned documentation changes. The index
stages only new A9 files and HEAD plus owned authority deltas, preserving inherited
unstaged edits. Staged diff and `git diff --cached --check` are reviewed before one
local Conventional Commit; final commit SHA is returned in handoff. Default sandbox
denied the first Git object write before index mutation; the authorized scoped
escalation succeeded, with no automatic approval-review rejection. Rollback is a
scoped revert of this audit commit while preserving inherited edits; no data rollback.

All four pytest sessions and their owned workers finished. No WSL workspace was
created: the already validated WSL environment cannot establish target ARM64,
systemd mounts or representative live SLO, and repeating it would not close the
blockers. The focused temporary directory was already absent after pytest retention; the
remaining three A9 pytest directories were identified by their test names, resolved
inside the temporary root and removed. No existing workspace/cache was manually removed. No persistent server/browser/service,
pending worker write, package install, push/reset/bulk stage or approval rejection.

No Pi/production access, deployment, real backup/release/history cleanup, real DB
reset/restore/migration, systemd/Cloudflare/network/security changes, production
credentials/data, external provider, MyFood or my_money operation occurred.

**Next:** supervisor review of A9-B1/B2/B3 and D1. To close A9, supply existing
sanitized exact-candidate receipts if available, or separately authorize a concrete
nonproduction Pi/staging campaign: dedicated credentials/guild/origin, reviewed
workload and accepted capacity/SLO thresholds, finite >=24h soak with diagnostic
coverage, current packaging/service proof and representative recovery budget/RPO/RTO
measurement. Secret values must stay operator-managed; host/service/network/long-run
actions need explicit approval outside this local audit. No such action is requested
or started here. **A9 remains BLOCKED; A10/Integrated/Phase11 do not start.**
