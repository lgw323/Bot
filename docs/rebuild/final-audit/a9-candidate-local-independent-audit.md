# A9 local candidate packet independent audit

2026-10-04. **FAIL: material measurement-identity defect A9-LOCAL-M1. STOP.**
This verdict concerns the new local packet only, not a newly demonstrated runtime
product defect. Runtime candidate A9 remains **BLOCKED B1/B2/B3/D1**. The author's
local PASS is not independently accepted. No implementation fix was made.

Authority: root AGENTS; compact final-audit active-state/common STOP rules and
BI/BJ/BK; assigned Phase 9 ledger/index; relevant B13/B19/C2 and storage/engagement
contracts. `.agents` is absent; no applicable nested repository skill was found.
Read the local report, manifest, evidence, implementation/tests, owned patch and
actual nine-file delta. Existing unrelated work is outside this audit's scope.

## Material finding and reproduction

[Packet builder](../../../scripts/a9_candidate_packet.py), imports and lines 88-101:
`build_packet()` hashes disk files before/after execution but never binds those
bytes to the Python modules already imported into that process. A file changed
after import and before the first identity read can be certified as measured even
though the old code runs. Comparing two disk snapshots cannot detect this case.
The existing source-drift test changes the second identity result; it does not
exercise this gap. Source/export/harness identity is an explicit packet requirement.

Reproduced entirely in a new OS-temp export containing just the manifest's 146
allowlisted files. No implementation file in the repository was changed:

1. Prepend export and export/src to Python's module search path. Set `GIT_DIR` to
   the repository's `.git` solely for the builder's read-only `git rev-parse HEAD`.
2. Import packet and adapter; assert their `__file__` and the storage module's
   `__file__` are in the export.
3. In the exported adapter only, insert
   `raise RuntimeError("AUDIT_CHANGED_CODE_EXECUTED")` immediately before
   `return await self.app.message(100, 10, event, "abc", self.app.clock.now())`.
4. Call `build_packet()`. It reports **PASS**, `source_unchanged_after_run=true`,
   eight completed operations, and the hash of the changed adapter.
5. Reload the adapter with `importlib.reload(adapter)` and build again. The same
   certified export now reports **PARTIAL**, `unexpected_fault` at `text_write`.
   Both runs clean their temporary DBs, report zero remaining workers, and leave
   no extra Python threads. The second run is an internal control, not a separately
   counted pytest case.

Imported adapter SHA-256:
`6aa78d7d75b7aa1c31eeb4fc945a5b62935437a654f2147d39fbfe1f7a7ece99`.
Changed adapter SHA-256:
`b59655a687070d2fdb72c7e1255ebb9f84b0a5d95568bbff529d5388d2de790f`.

Exact independent probe retained at
`%TEMP%/test_a9_independent_identity_probe.py`, SHA-256
`bb7a1f3c92918215b2da782d3fd8d4eb5f5c21d2d6aa3bd04205262632541867`.
From the repository in PowerShell:

```powershell
$auditTempRoot = [System.IO.Path]::GetTempPath()
$auditProbePath = Join-Path $auditTempRoot 'test_a9_independent_identity_probe.py'
.venv/Scripts/python.exe -B docs/rebuild/final-audit/a8r4-test-runner.py $auditProbePath --rootdir=$auditTempRoot --confcutdir=$auditTempRoot -q -s -p no:cacheprovider
```

Result: **0 PASS / 1 FAIL / 0 SKIP, 3.37s**. The failing assertion requires the
stale-loaded run not to claim PASS. An initial invocation without explicit temp
root/confcutdir produced **one collection error, zero executed tests** because
pytest attempted to scan a denied ancestor directory. That invocation is retained
here and is not counted as a contract failure or successful test.

This proves a false-certification path, not that the delivered packet definitely
executed stale code. Its present disk hashes match; its runtime identity assurance
is nevertheless insufficient. No further functional audit or remediation followed
the material reproduction.

## Evidence that did verify

- **63/63 focused tests PASS**, 5.46s, zero skips: the unchanged candidate-packet
  and local-harness files (61 tests), plus the documentation link and heading-anchor
  tests (2). Ran with the existing offline/data-denying runner and `-p no:cacheprovider`.
  No giant full-suite repeat. This is separate from the one independent failing case.
- Real candidate calls replace fake labels: temporary SQLite bootstrap, engagement
  writes/dedupe/profile, actual second-connection SQLITE_BUSY/retry, failed write
  rollback, barrier-controlled precommit cancellation, fake birthday delivery and
  shutdown. The write lane is drained before cancellation's persisted XP read.
  Classification requires the actual busy error code; wrong errors are rejected.
- Eight composite operations are distinct from **22 worker completions plus three
  awaiter observations**. Five successful operation samples each have n=1; the
  three expected fault samples remain outside successful percentiles. Queue and
  execution timing are real observations; execution includes SQLite lock wait.
  These samples do not establish SLOs, representative load or provider latency.
- Reviewed new-root/fake identity/config refusal, bounded operations/output/observer
  storage, deadlines, cleanup and failure preservation. Focused tests cover ordinary
  timeout/drain, replacement refusal and no recursive deletion. Cooperative bounds,
  no kernel-hang guardian, and modeled Windows link races remain disclosed limits.
  Candidate targets are new synthetic temp DBs. No network/provider, credentials,
  real DB, Pi, install, security changes or deployment was used in this audit.
- **146/146 source hashes**, canonical export digest, **8/8 artifact hashes** and
  **9/9 receipt hashes/counts** match. Export digest:
  `42e5cdfe289dba5180a245f0a03e9bde6f83832835c787e3a5afa5202615a43c`.
  Independently regenerated the nine-file unified delta from entry appendices,
  HEAD harness and new files: it exactly matches `scratch/a9-candidate-local/owned.patch`.

The extra historical full-suite failure is **not concealed**. Original XML and
evidence retain **1652 PASS / 3 FAIL / 27 SKIP (1682 cases)**, including the missing
`a9-candidate-local-evidence.json` link. Its unchanged link/anchor tests now pass.
The two inventory/Deno failures remain known unresolved limitations; the earlier
1652/2/27 receipt is separately retained. No clean full-suite result is inferred.
Artifact generation must finish before final document validation; fixing that
ordering does not repair the loaded-code identity defect. Four dependency-pin
mismatches and missing ARM64/artifact/soak evidence remain explicit.

## Preservation and exact next boundary

All **71 inherited contents** verified: 69 byte-identical and two recovered exactly
by removing only the owned changelog/active-state appendices. Audit-entry snapshot
covers 231 relevant existing files, including source, owned files, inherited work,
receipts and owned.patch. This audit adds only this report to the repository; it
does not rewrite the author report/manifest/evidence, ledger, index or active-state.
HEAD remains `769a00ab892edc7f98a1f9d947abd23d99c1056a`; index empty; no commit/push.
Temporary source copies/probe stay under normal OS/pytest temp retention.

**Next: separately scoped local A9-LOCAL-M1 identity remediation, then independent
reverification and final artifact/link verification.** Bind execution to a frozen
source export and fresh interpreter/import provenance (or an equivalent demonstrable
binding), with this stale-import negative control. Do not silently refresh hashes
around already-loaded code or convert this audit into a fix. No Watch/Music packet,
external campaign, A10, Integrated Audit or Phase 11 begins here. External host
diagnosis/campaign still requires separate approval under the recovery report's
R/C boundaries. Rollback of this audit is removal of this report only.
