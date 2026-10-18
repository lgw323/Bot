# A9-LOCAL-M1 independent remediation verification

2026-10-04. **FAIL: new material saved-receipt validation defect A9-LOCAL-M2. STOP.**
The original M1 stale-import attack is independently GREEN. Fresh execution binding
works for that attack, but the added saved-packet verification cannot support its
claimed receipt-drift refusal. No blanket packet-identity acceptance or runtime A9
PASS is granted. Runtime A9 remains **BLOCKED B1/B2/B3/D1**. No silent fix.

Read root AGENTS and the compact audit authority/assigned Phase 9 routing, including
BL; retained the original audit's relevant B13/B19/C2/storage/engagement boundaries.
Reviewed the [remediation report](a9-local-m1-remediation-report.md), evidence,
manifest, seven-file owned.patch and actual code/tests. No applicable repository
skill or `.agents` directory; no external artifact/app workflow is relevant.

## M1 proof and current artifact

Reran the exact original independent probe without changes, SHA-256
`bb7a1f3c92918215b2da782d3fd8d4eb5f5c21d2d6aa3bd04205262632541867`:
**1/1 PASS, 4.39s**. Both stale-parent and reloaded-parent calls now execute the
changed adapter bytes in a new worker, produce PARTIAL/unexpected_fault at the
first operation, clean their temporary DBs and report zero remaining workers.
The original 0/1 RED receipt remains preserved.

The loader recompiles verified memory bytes for candidate/harness modules in a
fresh `-I -B` interpreter. Parent imports and timestamp/size-valid `.pyc` files do
not supply those modules. Module origin paths are labels for the compiled bytes;
the bootstrap string has its own digest. Capture corruption and capture-time
changes are refused; later source changes cannot replace frozen worker bytes and
prevent a current-source PASS. This is repository-source binding, not dependency
binary attestation or a hostile-code sandbox.

Delivered manifest SHA-256 independently matches:
`7ede81925d2122b395a9063b074dbf705d621cb4e5f2e804a3960fce4c3ddbcf`.
All **146 source hashes** and **37 compiled-module provenance entries** are present
in that intact artifact. Export:
`9abd0bc4e382bda5931149ae49d5c460a634682d4c5049f7c489d76ca703a5a6`.
The intact delivered manifest passes `verify_packet()`; no evidence shows its
actual measurement used incorrect candidate bytes.

## A9-LOCAL-M2: missing executed-module provenance is accepted

[Packet builder](../../../scripts/a9_candidate_packet.py), lines 300-312:
`verify_packet()` checks the hashes of whichever module entries remain, but does
not require a complete receipt or even the measured adapter's entry. Deletion
therefore evades the `any(...)` mismatch check. The worker-return validation at
lines 283-287 uses the same subset-only pattern. This is material to the newly
specified saved-packet identity/reuse boundary, not a new runtime application bug.

Independent reproduction used only an in-memory copy of the delivered manifest:

```python
original = json.loads(manifest_path.read_text())
packet.verify_packet(original)  # valid control: accepted
damaged = copy.deepcopy(original)
damaged["execution"]["modules"].pop("scripts.a9_candidate_adapter")
# Now 36 entries instead of 37; microphase still PASS.
packet.verify_packet(damaged)   # incorrectly returns normally
```

The expected refusal assertion failed: **0 PASS / 1 FAIL / 0 SKIP, 1.31s**,
`Failed: DID NOT RAISE ValueError`. No source, actual manifest or evidence file
was edited. The original artifact's externally recorded hash would detect such a
file alteration if separately checked; `verify_packet()` itself does not enforce
that binding. This finding does not allege a forged historical measurement.

Exact probe: `%TEMP%/test_a9_m1_receipt_independent.py`, SHA-256
`5cd8f1db2036e96a0268b9b22625e97e234a15f9bad5ac1122a5ddd74a0272f6`.
From repository PowerShell:

```powershell
$auditTempRoot = [System.IO.Path]::GetTempPath()
$auditProbePath = Join-Path $auditTempRoot 'test_a9_m1_receipt_independent.py'
.venv/Scripts/python.exe -B docs/rebuild/final-audit/a8r4-test-runner.py $auditProbePath --rootdir=$auditTempRoot --confcutdir=$auditTempRoot -q -s -x -p no:cacheprovider
```

Stopped functional testing at this first material finding. No repair or broadened
Music/Watch/security work followed it.

## Checks, limitations and retained history

- Fresh **83/83 PASS**, 43.52s: 81 candidate-packet/local-harness checks plus two
  documentation link/anchor checks, with the offline/data-denying runner and
  `-p no:cacheprovider`. Separate from the original 1/1 probe and new 0/1 probe;
  controls inside each probe are not additional pytest cases.
- These checks cover stale imports/pycache, frozen capture changes, real temp SQLite
  cancellation/rollback, worker crash, timeout/operator interrupt/reap, parent-pipe
  EOF, prelaunch cancellation, corrupt snapshots and denied external actions.
  Parent enforces a 10s worker deadline and bounded reap; normal measurement retains
  its 5s/1s bounds. Forced exit returns no certificate and may leave synthetic DB
  files, as disclosed. No OS quota, hard-killed-parent cleanup, kernel-hang or
  actual reparse-race guarantee is inferred.
- Twelve remediation receipt hashes/counts and all nine original receipt hashes
  match. Author results **483 PASS** and full **1673 PASS / 2 FAIL / 27 SKIP**
  (1702 cases) are retained, not independently rerun or added to fresh counts.
  Historical **1652 PASS / 3 FAIL / 27 SKIP** (1682 cases), including the artifact
  ordering failure, remains unchanged. Known inventory/Deno failures remain open.
- Installed pins do **not** all match. Worker distribution metadata reports
  bgutil-ytdlp-pot-provider 1.3.1, deno 2.9.7 and yt-dlp-ejs 0.8.0 pins with no
  installed distribution version; yt-dlp is 2026.7.4 versus pin 2026.8.19.
  These are four disclosed mismatches, not fresh executable/ABI investigations.
  Package versions and an interpreter hash are not wheel hashes or ARM64 proof.

## Preservation and next boundary

Independently matched the exact seven-file patch against entry bytes and current
files, all owned before/after hashes, **642/642 unowned entry files**, and the two
strict append-only documentation edits. The audit-entry snapshot covers 675
existing files, including implementation, inherited work, artifacts and receipts.
This audit adds only this report to the repository; existing implementation and
historical reports/manifest/evidence/ledger/active-state remain untouched.
HEAD `769a00ab892edc7f98a1f9d947abd23d99c1056a` and empty index are preserved.
No commit, staging, push, Pi/network/provider/credential/production-data access,
install, deployment or permission change. Synthetic probes/copies use OS temp.

**Next: separately scoped local M2 receipt-integrity remediation, then independent
verification.** Enforce complete measured-module provenance and bind the saved
execution receipt to its trusted artifact identity; a subset comparison cannot
establish completeness. Retain the original M1 GREEN and this missing-entry RED.
Do not begin a Watch packet, external campaign, A10, Integrated Audit or Phase 11.
External diagnosis/campaign still requires separate approval. Removing only this
report rolls back this audit's repository change.
