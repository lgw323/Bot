# A9-LOCAL-M1 local identity remediation

2026-10-04. **Remediated pending independent verification; not CLOSED.**
Runtime candidate A9 remains **BLOCKED B1/B2/B3/D1**. This report supersedes the
local identity assurance in BK only. The original author packet/report/evidence
and [independent FAIL report](a9-candidate-local-independent-audit.md) remain
unchanged historical evidence. No runtime application code or accepted UX changed.
Read root AGENTS, compact authority through BK, assigned Phase 9 ledger/index,
B13/B19/C2 and storage/engagement contracts. No listed skill applies to this
repository Python remediation; no external artifact/app workflow was invoked.

## Exact reproduction and correction

Before implementation changes, reran the auditor's exact OS-temp probe, SHA-256
`bb7a1f3c92918215b2da782d3fd8d4eb5f5c21d2d6aa3bd04205262632541867`, through the
existing offline/data-denying runner with explicit temp root/confcutdir. Result:
**0 PASS / 1 FAIL**, 3.00s. Imported adapter hash
`6aa78d7d75b7aa1c31eeb4fc945a5b62935437a654f2147d39fbfe1f7a7ece99`, changed hash
`b59655a687070d2fdb72c7e1255ebb9f84b0a5d95568bbff529d5388d2de790f`.
The stale-loaded run falsely returned PASS, eight operations and unchanged source;
fresh reload returned PARTIAL/unexpected_fault. Both cleaned their synthetic DBs.

The unchanged probe subsequently passed: both calls actually executed the changed
adapter, returned PARTIAL/unexpected_fault at text_write, and cleaned their DBs
with zero remaining workers. This is author rerunning the independent reproducer,
not independent closure. Original RED and intermediate failures remain in receipts.

[Packet builder](../../../scripts/a9_candidate_packet.py) now captures verified
allowlisted bytes once. It sends those bytes and their hashes to a new `-I -B`
interpreter, which rechecks the export digest and compiles candidate and harness
modules directly from memory using a closed import loader. Its module provenance
map names each compiled source and hash. Neither parent `sys.modules`, a different
source path, nor a timestamp/size-valid stale `.pyc` supplies candidate code.
Module `__file__` names denote logical origins; code comes from the verified memory
map, not a mutable on-disk export. The exact executed bootstrap string is hashed
separately; the interpreter executable hash/flags and worker-installed dependency
versions are recorded. Package versions are not wheel/ABI or dependency-byte proof.

Changes during capture refuse execution. Changes after capture cannot replace the
worker's bytes; a mismatch at the final source comparison makes the packet PARTIAL. A saved
packet must pass `verify_packet()` before reuse; later source/config/scenario or
execution-receipt drift is rejected. Neither updated labels nor expected hashes
substitute for running the captured source.

The existing real temporary SQLite eight-step scenario, its actual observations,
fault classifications, rollback/cancellation oracles and normal cleanup are intact.
No changes to the adapter, local harness or `src/` are part of this remediation.

## Worker boundaries and remaining limits

- The existing 5s measurement/1s cleanup bounds remain; a separate 10s parent
  wall deadline terminates and reaps a stalled worker. Requests use an owned
  temporary file so pipe backpressure cannot block the parent before its deadline.
- Operator cancellation and KeyboardInterrupt kill/reap the owned process in
  `finally`. A child watchdog exits the entire worker on parent-pipe EOF; child
  subprocess creation is denied. The EOF case is directly tested.
- Worker launch, crash, corrupt snapshot, protocol and deadline failures return
  no measurement certificate. Exceptions retain only the synthetic run ID and a
  cleanup limitation. Forced exit may leave that run's synthetic DB/temp root;
  graceful DB cleanup is never asserted after a forced exit. Request/output files
  are context-owned and removed on ordinary exception/cancellation paths.
- Worker network and credential/operational-data guards are installed before
  candidate imports; only stdlib Windows asyncio socketpair construction is
  permitted. Environment inheritance is limited to named OS/temp/architecture
  fields, with dotenv disabled. Existing outer test guards remain in use.
- No OS resource quota, hostile-code sandbox, dependency artifact lock, parent
  hard-kill temp-file cleanup, kernel-hang recovery, actual reparse-point race
  exclusion, Pi/ARM64, representative workload or soak claim is made.

## Validation and evidence

Final receipts, exact commands, hashes, before/after ownership and preservation
checks are recorded in `scratch/a9-local-m1/` and [remediation evidence](a9-local-m1-evidence.json).
The [fresh manifest](a9-local-m1-manifest.json) records the executed source identity.
Focused checks: **81 PASS** (20 new, 61 retained), 40.20s. Storage/engagement,
build and architecture regressions: **483 PASS**, 37.10s, one existing audioop warning.
The unchanged auditor probe: **1 PASS**, 4.38s. Counts overlap with the full suite
and must not be added together.
An initial worker attempt failed before its certificate (one failing probe);
the watchdog now reads the raw pipe descriptor, avoiding a buffered-stream reader
at interpreter shutdown. The first expanded focused run had **73 PASS / 2 FAIL**:
worker platform identity omitted the Windows architecture environment field.
Retaining only the named OS architecture fields corrected the actual worker
metadata; assertions were retained. The intermediate **75 PASS** receipt precedes
the last six new checks and interpreter fingerprint. These are not final-source
counts and are not combined with the final 81 checks.
The old full-suite **1652 PASS / 3 FAIL / 27 SKIP** remains unchanged, including the
artifact-ordering missing-evidence-link failure; the earlier 1652/2/27 receipt and
the independent 63 PASS plus 0/1 identity probe are separate historical runs.
There is no assertion weakening, added skip or clean-suite inference.
Packet `microphase=PASS` denotes this bounded successful measurement only; it
does not close the finding or confer runtime A9 acceptance. The remediation
evidence status remains `REMEDIATED_PENDING_INDEPENDENT_VERIFICATION`.

Final-source full suite: **1673 PASS / 2 FAIL / 27 SKIP**, 340.80s, one existing
audioop warning. Failures are the unchanged audit-document inventory assertion
and missing Deno executable (`test_pinned_provider_and_runtime_load_without_network`).
No dependency install or inventory-test weakening was attempted. The historical
artifact-ordering failure is absent from this run because referenced artifacts
were generated before document validation; its original failing receipt remains.
After the full suite exited, standalone final packet capture passed (one check,
2.10s), with eight real composite operations, 22 worker completions, three awaiter
observations, all nine scenario checks, normal DB cleanup and zero remaining workers.

Fresh frozen export: **146 files**, SHA-256
`9abd0bc4e382bda5931149ae49d5c460a634682d4c5049f7c489d76ca703a5a6`.
Actual compiled source modules: **37**. Final manifest SHA-256:
`7ede81925d2122b395a9063b074dbf705d621cb4e5f2e804a3960fce4c3ddbcf`.
Config/scenario identities are unchanged from the historical scenario; the new
execution receipt identifies the fresh worker/bootstrap. Four existing dependency
pin mismatches remain: bgutil-ytdlp-pot-provider, deno, yt-dlp and yt-dlp-ejs.
Final link/heading verification after artifact assembly: **2 PASS**, 0.33s.

## Ownership, rollback and review boundary

Owned edits are the packet builder, its existing test file, and appended sections
in CHANGELOG and compact active-state. Three new remediation artifacts hold this
report, a fresh manifest and evidence. The exact delta against entry bytes and
before/after hashes are retained; inherited changes are not reset or staged.
All **642 unowned files** in the 646-file entry inventory remain byte-identical;
the two authority/changelog edits are strictly appended to their entry bytes.
All nine original test receipts also match their historical hashes. Source and
test edits have their full entry bytes retained, including inherited modifications.
Rollback applies the inverse owned patch or restores the recorded entry bytes
for those four edited files, then removes only the three new artifacts. It has
no data/service consequence. Historical report/manifest/evidence and the newly
supplied independent audit report must remain untouched.

**STOP for parent review and fresh independent verification.** No commit/push,
Watch/music expansion, Pi/SSH, external campaign, install/upgrade, credentials,
production data, deployment or permission changes. No A10/Integrated Audit/Phase11.
