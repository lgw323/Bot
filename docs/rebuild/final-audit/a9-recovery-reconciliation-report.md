# A9 bounded recovery evidence reconciliation

2026-10-04. **Supplied bounded recoveries PASS within their recorded scopes;
A9 remains BLOCKED (B1/B2/B3/D1).** This session inspected local files only.
No Pi/SSH, privileged action, deployment, restart, load/soak, new service,
credential, package, staging, commit or push occurred. A10/Integrated Audit/
Phase 11 and friend activation remain held.

Local HEAD is `769a00ab892edc7f98a1f9d947abd23d99c1056a`, not the operating
version. Entry has 11 modified and 59 untracked files (70 contents), empty index.
The operating identity recorded by the recovery receipts remains
`8e9018d4b8061cde6006eee47fa4103522f77718` /
`r-8e9018d4b8061cde-3dac82a792fad576`.

## Authority and documentary reconciliation

Read active-state, Phase 9 ledger and document index first, then the
[A9 audit](a9-phase-9-report.md), [local preparation](a9-local-preparation-report.md),
[historical Phase 9 report](../phases/phase-09/phase-9-report.md),
[B19](../baseline/19-testing-strategy.md#non-functional-verification),
[C2](../phases/phase-01/concurrency-failure-plan.md#stage-gates),
[B20 Phase 9](../baseline/20-migration-plan.md#phases),
[B13](../baseline/13-non-functional-requirements.md),
[recovery contract](../phases/phase-08/backup-restore-contract.md) and
[staging runbook](../../../deploy/runbooks/first-staging-install.md).
The original dedicated staging application/guild, sanitized data, clean Pi 5 /
Ubuntu 24.04 ARM64 / Ethernet, capacity acceptance and **at least 24h** representative
soak remain requirements. Neither seven days of operation nor either new smoke
waives B19/C2 or the staging contract. Historical E1/E2/D-series proof stays valid
within its original scope; no giant gate matrix is repeated here.

Before editing, reported that active-state BI's `baseline503/H2 latch` wording
could imply an established diagnosis. Corrected the current routing to distinguish
observed 503 from unproven cause. The user reports the condition since October 1;
the supplied October 4 receipts independently show both internal readiness endpoints
9010/9011 at 503/false before and after the runs. They do not prove uninterrupted
503 throughout those days. Public Watch9000 readiness200 and liveness200 do not
resolve internal readiness. H2's intended terminal policy, already examined in A8,
is not proof of the current incident's initiating cause. Older active/ready wording
is explicitly historical, not a current host observation.

No material conflict between the latest recovery PASS claims and their local
receipts was found. Bot `extraction.json` says prerequisite MISSING / Pi NOT_RUN
and has an earlier runner hash: inspection of preparation/finalization/sealing
scripts establishes that it is a preserved preparation-stage receipt, not the final
execution verdict. The final runner and transported payload match. Source comparison
initially rejected raw Git blob hashes; all 130 differences were exactly Git LF to
installed CRLF, consistent with the original preparation's newline-normalized check.
Do not call these installed hashes byte-identical Git blobs. A first local inspection
also assumed plain JSONL; Bot events carry `BOT_*` prefixes. Parsing the explicit
record prefix resolved this without changing evidence or any gate result.

## Evidence identities and bounded results

Original files remain at these local locations; no backup/DB bytes or secret values
were read or copied in this reconciliation. Only safe source, aggregate reports,
receipts and sanitized event records were inspected. These local/temporary evidence
paths are not promised to exist in another checkout.

| Evidence | Local location | SHA-256 |
| --- | --- | --- |
| Bot final report | `scratch/bot-recovery-20261004/final-report.json` | `79b906341ce0ff08f5b49738587c29a5aea9e0b8f0ed500a94866f9e209f17b7` |
| Bot streamed receipt | `scratch/bot-recovery-20261004/pi-receipt-streamed.json` | `bb42e17f5f411117fcf1a6608d9204245ea55860cffa56caf9059f0e276f162e` |
| Hanteok final report | `C:/Users/dlrjs/AppData/Local/Temp/hanteok-nofile1024-79fbb72aef494c3d9c36a2646c22c613/final-report.json` | `5fb6a5f3930c4ae62567875e53f29e118b3c247f82b4ea25909571f82217470e` |
| Hanteok fetched receipt | Same temporary directory, `pi-receipt.json` | `4b8a71059ecdffa52d644211d11a258cc5a0add0d5b154c5734c06fa6302535a` |

**Bot:** 12:52:45.153589-12:52:45.729649 UTC, 0.576060s for the recorded bounded
run, not end-to-end RTO. Independently recalculated all 17 final-report local-file
hashes/sizes, decoded the transport without executing it, compared embedded worker
bytes and 130 Python source hashes against operating Git content with the explicit
newline conversion above. The host receipt records 131 installed source entries;
this is not a fresh host inventory or a full dependency/ARM64 certification.

The latest completed archive selected then was
`20261004T120019976149-e5668d2b2e87475991ffc5c7cd3fb410`, created
12:00:20.185664 UTC, 281,505 encrypted bytes, SHA-256
`87d6b34a23ad3b9261db52993a8445f68f5218265e66ad7904480051fbd026cc`.
Runner inspection confirms ciphertext/metadata checks before restoration and again
after, a new private destination, and no canonical DB open. Receipt reports schema5,
integrity ok, zero FK violations, matching aggregate/data/metadata checksums and
application data-adapter open/read/close PASS. The restored file was 339,968 bytes;
this small copy does not measure representative candidate retention cost.

The streamed final record equals the saved local receipt. Worker278584 and SSH
exit0, reap/absence, independent after-check and service state/PID/restart/health
comparisons agree. Prerequisite hashes link the completed Hanteok run; overlap
checks found no other candidate. Gateway/Watch were not started. Operating DB
preservation is supported by the reviewed no-access path, not a live DB hash.
Peak RSS is **unmeasured/null**: the worker finished before the first one-second
sample. Private paths and child limits are not enforced filesystem/network isolation.
There was no separate readback of the persisted Pi receipt, no off-host backup
readback, no new backup generation, no sustained RPO/RTO or 180s budget proof.
Prior 12 synthetic preparation tests passed; their initial fixture failure/error
and initial SSH255 remain historical, not rerun or counted as new tests here.

**Hanteok (한턱):** 12:37:14.697621-12:37:19.380871 UTC. Its 21 preparation
tests are prior evidence. Final report, fetched receipt, fetched event/stdout/stderr
hashes and independent termination readback agree. Sealed runner/transport match;
14 recorded PDB/source checksum pairs and DLL linkage agree across local evidence.
The receipt records 500 installed files unchanged for release
`20260925-ux-3aaee34f`, archive SHA-256
`3aaee34f73b371b9199070df5d5c21582de7dbb99d09cf70fcd538ad9107ff62`.
This session did not re-read the installed archive, DLL/PDB or database.

Health/static200, protected endpoints401 and the reviewed nonexistent synthetic
invitation DB lookup404 passed. Child278112 exited0 after bounded success-finalize
SIGTERM; independent check confirms PID absent and port56905 absent. Original
artifact, recovery inputs and extra copy hashes, operating service state/PIDs/
restarts and parent/service/system limits compare unchanged in the receipts.
This is read-path smoke, not production restoration or write-path recovery.

Actual child NOFILE was1024/1024; inherited soft/hard1024/1048576. Sampled FD counts
were260 after health and287 after DB lookup, not a continuous maximum. This supports
that256 was artificially too low for this .NET smoke; **do not reuse an arbitrary
256 FD cap for future .NET tests**. It neither authorizes raising production limits
nor establishes1024 as a universal capacity or permits unbounded limits. The Bot's
separate short Python worker limit256 does not establish a .NET limit.

Historical failed smokes remain **PARTIAL**, not retroactively PASS: local
`hanteok-smoke-0fc7464c9e5741d081f0d8d24078fa42` and
`hanteok-observed-b87acad2004f46289d1997ef37e75b6e` final reports and receipts
all match the prior-local hash inventory (four files checked). Earlier historical
24h anomalies and short follow-ups in A9 remain preserved too.

## Smallest remaining sequence

1. **One local preparation increment, no host operations.** Freeze the intended
   candidate's source/export digest including any deliberate code deltas, dependency
   pins/lock and available ARM64 artifacts, sanitized config digest, harness source
   digest and scenario/data identity. Record missing ARM64 artifacts/ABI proof as
   missing; Windows/fake receipts cannot supply them. Extend existing test adapters
   only enough to drive actual candidate command/SQLite/music/Watch paths and collect
   the missing metrics. Keep deterministic unit cases separate from live voice/
   browser/provider checks. The current fake-label harness is not a load generator;
   don't rerun its completed42 tests as a substitute for this work. Reuse A2-A8
   evidence unless a changed path requires a targeted regression.
2. **Separately approve one read-only Pi diagnosis/suitability pass (bundle R below).**
   Resolve evidence gaps for the current503 and host isolation/headroom. Do not
   restart to clear the symptom. If a repair is needed, explain observed before/after
   behavior and seek its own approval. No representative load starts on a shared
   host with the present unexplained operating degradation.
3. **Review one concrete campaign packet, then bounded staging smoke.** Select a
   clean dedicated target, or explicitly document and accept a shared-host deviation
   without calling it clean-host conformance. Identify exact separate paths, ports,
   accounts/units, data, locks, credentials and destinations; prove isolation fits
   the unchanged operating pair. Existing staging tools reuse production paths/
   ports/names and require production inactive: they cannot be reused unchanged on
   this host. Never stop production to satisfy that guard. Obtain candidate ARM64
   build/ABI and real service/credential-mount evidence here if still missing.
4. **Only after smoke/diagnosis/isolation approval, run one finite representative
   campaign.** Normal, peak x2 of an observed basis (or explicit owner-approved
   capacity), bounded faults and >=24h soak, then independent reconciliation.
   Exercise changed lifecycle/SQLite/voice/music/Watch paths and candidate
   retention/freshness under concurrent synthetic writes and representative backup
   sizes/retained-point counts. Measure backup generation/validation/retention/
   encrypted publication and off-host readback separately from restore/application
   recovery. Observe scheduled points across the run for RPO<=6h and measure the
   approximately1h RTO objective; retain the unchanged180s backup budget. A fast
   single restore cannot close these gates. Submit measured acceptance against
   A9-B1/B2/B3/D1; no automatic production deployment or A10 follows.

User-reported seven-day operation may support unchanged host/platform and old-runtime
backup history to the extent receipts corroborate it. It does not exercise candidate
guardian/shutdown, SQLite, voice/music/Watch, retention or freshness changes. A0-A8
repository PASS remains scoped; these recoveries close no candidate host/load gate.

## Proposed approval bundles, not authorization

**R: next Pi action proposed for review.** One operator-approved read-only session
on the existing Pi, maximum10min, no retries beyond that window and no privilege
escalation. Read only operating release/manifest identity, named service properties
for Discord/Watch/backup timer/Hanteok/tunnel, relevant listener bindings, OS/ARM64/
Ethernet and aggregate CPU/RSS/FD/free-space/I/O headroom. Read the already-known
local health/metrics endpoints at most once per15s each, request timeout2s.
Read at most500 relevant structured journal entries since October1, locally extract
allowlisted timestamp/error-code/probe-stage/SQLite-code/latency counters; never
return raw logs, IDs, message content, URLs, credentials or command-line secrets.
Correlate to H2 policy without presuming cause. Inspect backup metadata availability/
freshness only where existing permissions permit; no archive decrypt or DB open.
If access needs sudo, a new credential or broader scope, stop that part and report
the exact missing access. Stop for identity change, unexplained new restart,
worsening health/resource pressure, inability to sanitize output or operator cancel.
Output one sanitized diagnosis/isolation receipt and the exact next packet. No
service writes, installs, configuration, reset-failed, backup trigger or remediation.

**C: later campaign approval must name a completed packet, not approve placeholders.**
Before requesting it, supply exact candidate/export/ARM64 artifact/lock/config/harness
hashes, target host/OS and dedicated-versus-shared decision, all owned paths/ports/
units/accounts, allowlisted providers and secret *locations* (never values), temporary
data/backup identities and separate off-host destination. Existing `Bot-Data/db-backup`
is not a staging write target. Name requested package transfers, new services,
credentials, ACL/polkit or route changes individually; they are separate security/
privileged approvals, not implied by local preparation or R. Prefer existing
capabilities; no new infrastructure solely for reporting.

The packet must contain owner-accepted realistic workload rates and concurrency,
normal/burst/fault schedule, pilot<=15min and a planned24h observation with a hard
26h execution ceiling including shutdown/evidence collection; no automatic extension
or retry. Use observed usage or explicitly approved small-community capacity.
The prior1command/s,5writes/s and1GiB/etc example remains UNAPPROVED, not a baseline.
Use B13's proposed ACK p95<1s/p99<2s, local command p95<2s/p99<5s, DB read/write
execution p95<25/50ms, loop lag p99<100ms and WS relay p95<250ms as the starting
SLO proposal for owner acceptance. Separate queue/lock wait and external-provider
time from execution; include sample denominators, failed/cancelled requests,
gaps, queue depth, task/child counts, RSS/CPU/FD, disk/log growth and backup-age
validity. Fill finite CPU/RSS/tasks/FD/I/O/disk/log caps and abort thresholds from
host headroom and a representative pilot; do not blindly copy small smoke caps.

Before starting, implement and review the observer and ownership/abort path. Abort
on operating identity/PID/restart/health change, unauthorized target, exceeded caps,
missed observability, unexpected DB failure, failed cleanup or operator cancel;
predeclared injected faults must have bounded recovery expectations and separate
counts. Abort stops/reaps only owned staging processes, verifies listener/task
absence and preserves evidence. No production restart/rollback/deployment and no
automatic deletion of old evidence. If safe containment or required measurements
cannot be delivered within the approved packet, return BLOCKED rather than broaden
scope. Shared-host acceptance requires an explicit recorded deviation; it does not
silently rewrite the clean-Pi or24h contract.

## Verification and handoff

Local-only receipt assertions PASS: 17 Bot file hashes/sizes,130 newline-reconciled
Git Python files, transported runners/workers, independent health/PID/exit and
Hanteok fetched-receipt hashes/events,14 recorded source checksum pairs and four
historical PARTIAL report/receipt hashes. Reproducer and sanitized output are in
ignored `scratch/a9-reconciliation-20261004/verify_evidence.py` and `verification.json`.
These are consistency checks of supplied evidence, not a newly witnessed Pi run.

Fresh documentation link and heading-anchor checks: **2 PASS in0.70s**, using the
existing offline/data-denying `a8r4-test-runner.py`, strict markers/config and the two
named tests in `tests/architecture/test_rebuild_documentation.py`. XML is retained
at `scratch/a9-reconciliation-20261004/docs-results.xml`. Historical preparation
logs independently show Bot12 tests OK and Hanteok21 tests OK; neither was rerun.
The current candidate diff also confirms changes in composition/platform/storage/
engagement/summary/music/watch/operations; local harness inspection retains its
`fake://a9/` guard and synthetic aggregates. No full application suite was rerun
for this documentation-only change. Prior known inventory/Deno/Linux/systemd/
audioop/A3 limits remain; no clean-suite claim.

Only this report and scoped active-state/Phase9-ledger/document-index routing change.
Historical reports, original contracts, local preparation, examples, runtime/tests,
other projects and all supplied receipts are preserved. No index write or commit;
parent reviews the entry-relative patch first. Rollback is removal of only this
report and reversal of those exact documentation hunks, preserving inherited edits.
Entry-relative preservation:67 inherited files byte-identical;3 routing documents
have reversible scoped deltas against saved entry bytes. Final status is11 modified /
60 untracked (one new report), index empty and HEAD unchanged. `git diff --check`
and `git diff --cached --check` pass; Git only emits existing LF/CRLF notices.
The exact owned four-file diff is `scratch/a9-reconciliation-20261004/owned.patch`;
the inherited untracked index is included only as its entry-relative delta, not as
a wholesale new file. No receipt, old report or unrelated change is staged.

**Decision:** approve local candidate/measurement preparation next; optionally approve
R exactly as bounded above. C remains unapproved until a concrete packet is ready.
Do not approve production deployment merely to acquire missing evidence.
