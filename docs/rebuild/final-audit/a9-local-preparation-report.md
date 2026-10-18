# A9 local campaign harness preparation

2026-10-04. **Preparation PASS; campaign readiness PARTIAL; A9 BLOCKED.**
This is the single authorized local preparation milestone, not an A9 acceptance
rerun, target-host campaign, deployment, or authorization to start A10.
Entry/candidate HEAD: `dc48b1ce66c63f36abdc2957d60d62bc387b725d`.
Final local commit identity is returned in the handoff; its parent is this entry SHA.

## Reviewed scope and existing tooling

Read actual Git/index state, root AGENTS.md, available skill catalog, active-state
through BH, A9 ledger/index routing and [A9 report](a9-phase-9-report.md).
No nested AGENTS.md or tracked SKILL.md applies to scripts/tests/docs; no skill
was needed for this repository code change and no subagent was spawned.
Reviewed [B19](../baseline/19-testing-strategy.md), B20 Phase 9, B13 host/capacity
boundary, C2 stage gates and [operations contract](../phases/phase-08/operations-contract.md)
plus the first-staging-install runbook. Their clean Pi 5 / Ubuntu 24.04 ARM64 /
Ethernet / dedicated staging / peak x2 / at least 24-hour acceptance remains open.

Static inspection confirms `deploy/staging/observe.py` uses `/var/lib/discordbot`,
health ports 9010/9011, fixed service names and requires production
`discord-bot.service` inactive at installation and on every observation iteration.
`local_discord.py` uses the same persistent DB/backups root and port9010;
`build_initial.py` uses the same root for source, wheels, DB and state. Operations
contracts reserve Watch9000/9001 and health9010/9011. These are not automatically
safe shared-host tools. None was run against a service, and production was not
stopped to satisfy a staging guard. No changes to those tools or runtime code.

## Delivered and bounded

- [Harness](../../../scripts/a9_local_harness.py): standard library only, explicitly
  identified `fake://a9/<32-hex-run-id>` with matching new direct child of canonical
  OS temp. No default destination, environment configuration loading, real provider
  dispatch, DB, socket, subprocess, thread, server or service capability.
- [Tests](../../../tests/integration/operations/test_a9_local_harness.py): 42 checks
  for sample/percentile counts, empty samples, tick gaps, all built-in fault types,
  target rejection, budgets, interruption, error paths and cleanup ownership.
- [UNAPPROVED example](a9-local-example.UNAPPROVED.json): human review only. Strict
  config shape rejects this document; it was never applied. It contains the future
  campaign proposals separately from local test limits.

The fake generator emits music/watch/command/engagement operation labels at bounded
ticks, with optional double operation count. It does **not** stream music, host a
Watch room, simulate two browsers, execute a Discord command or perform engagement
DB writes. p95/p99 measure fake dispatch overhead with successful sample counts;
they do not measure ACK, DB wait/execute, event-loop lag, queues or WS relay SLOs.
Expected injected provider-timeout/DB-busy/slow-peer outcomes count separately from
successful latency; unexpected injected faults abort. These classifications do not
diagnose the real H2 DB latch or retrospectively classify historical anomalies.

Hard configuration maxima: 32 ticks, multiplier2, 256 recorded operations,
65,536 output bytes, interval<=0.1s and requested duration<=5s. Runtime checks stop
at the operation/output/time budget, free-space floor, target change or operator
abort. There is one sequential fake operation at a time and no owned workers.
Memory is bounded by the operation/sample cap; this is not OS CPU/RSS/task/I/O quota
enforcement. Timing and filesystem checks assume the local OS remains responsive;
there is no guardian for hung kernel I/O or arbitrary injected test callbacks.
The harness is deliberately not an executable long-soak runner.

Output is a bounded temporary JSONL, deleted with its newly owned empty directory.
Only the allowlisted aggregate is returned to the caller. There is no recursive
deletion: extra files cause explicit cleanup failure, and replaced directory identity
or links cause cleanup refusal. Tests clean their own deliberate leftover fixtures.
Path checks are safeguards for this trusted local synthetic workflow, not a claim
of protection against a malicious process racing filesystem operations.

## Fresh checks and limits

Commands use existing `.venv/Scripts/python.exe -B` and the unchanged
`docs/rebuild/final-audit/a8r4-test-runner.py`. That runner denies operational
data reads and application network access; root conftest blocks dotenv and removes
inherited application settings. Temporary DB/fake providers, offline temp Git
transport and short reaped synthetic children were inspected; real Linux/systemd
checks remain opt-in and skipped on Windows. The Windows asyncio internal socketpair
exception is a local wakeup mechanism, not a provider or service connection.

- Focused: harness plus staging observation/entrypoint tests, **44 PASS** in0.60s.
  [Receipt](a9-local-focused-results.xml). New harness tests account for42;2 are
  existing regressions. Initial37 tests passed before additional guard coverage.
- Expanded first run:43 PASS/1 test-fixture failure. Windows refused renaming a
  directory containing the open JSONL. [Initial receipt](a9-local-initial-results.xml)
  retained; no production defect or gate result inferred. Corrected test models a
  changed inode explicitly; symlink/junction refusal likewise uses fake path flags.
  Actual Windows link replacement and POSIX rename behavior are not claimed verified.
- Full suite: **1634 PASS / 2 known FAIL / 27 SKIP**,275.54s;
  [receipt](a9-local-full-results.xml). Failures are the pre-existing final-audit
  Markdown inventory allowlist and missing local Deno executable. No install or
  unrelated test repair attempted; audioop deprecation remains. No clean-suite claim.
- Final documentation link/anchor checks: **2 PASS**,0.27s;
  [receipt](a9-local-doc-results.xml). A prior command used a nonexistent anchor
  test selector and collected no tests; corrected after reading actual test names.
  [Selection-error receipt](a9-local-doc-selection-error.xml) is excluded from counts.
- Real-clock smoke ran2 ticks/8 fake operations in the focused suite; all other
  new timing/fault checks are deterministic virtual-time logic checks. No long soak.

Exact commands, receipt hashes, counts, failures and inherited-content preservation
are in [evidence](a9-local-preparation-evidence.json). Full-suite and focused counts
overlap and must not be added together. No fresh Linux/WSL or ARM64 evidence.
Trailing whitespace in two failure receipts is XML-entity escaped for Git checks;
decoded XML is identical, and evidence retains both original and final hashes.

## Unapproved work and next boundary

The CPU1core/RAM1GiB/tasks128/read4MiB/s/write1MiB/s/footprint6GiB/log64MiB/
free-floor20GiB and normal1stream/1room2clients/1command/s/5writes/s, peak-double
numbers are **review proposals only**, not approved SLOs, observed usage, capacity
facts or enforced limits. Pending: shared-host deviation, resource/workload/SLO
acceptance, separate staging services/application/guild/credentials/live origin,
separate off-host backup destination and any actual target-host/24h operation.
Same-host WSL does not satisfy the original clean Pi acceptance; WSL was not used.
Existing `Bot-Data/db-backup` is strictly excluded from a future campaign target.

The reported production baseline503/latched DB probe must be resolved before load;
no current production observation or diagnosis was made, and no reset/restart is
authorized here. A9-B1/B2/B3/D1, current ARM64/service proof, representative workload,
24h soak, actual recovery-budget/RPO/RTO and owner sign-off remain open.
A0-A8 PASS stays within existing scopes. Recorded production source
`8e9018d4b8061cde6006eee47fa4103522f77718` / pin
`r-8e9018d4b8061cde-3dac82a792fad576` is untouched.

## Ownership and rollback

Entry had70 inherited contents (11 modified/59 untracked), with empty index. Owned
appendices in active-state and CHANGELOG are staged from HEAD plus only their exact
new delta; all inherited edits remain unstaged. Preservation evidence compares68
unchanged hashes plus2 exact inverse-owned appendices. No inherited untracked file
is added. Only named harness/tests/example/report/receipts and owned appendices
belong to the local Conventional Commit. Staged diff and whitespace are reviewed.
Default sandbox denied the Git index write; the scoped escalation could not read
the sandbox temporary patch. Copying that exact patch into the workspace allowed
the authorized scoped staging. No automatic approval-review rejection occurred.
Rollback: revert this single preparation commit, preserving pre-existing edits;
no data/service rollback is needed. No push/reset/bulk staging/history cleanup.

All owned tests and child work finish before handoff. Campaign scratch directories
are removed; explicit full-suite temp root is removed after resolved-path validation.
Evidence receipts remain in the repository. No SSH/Pi/network/provider/production
DB/data/credentials, live releases/backups, installs/security/service/routing changes,
MyFood or my_money actions. **STOP; A9 remains BLOCKED. No load, Pi or A10 follows.**
