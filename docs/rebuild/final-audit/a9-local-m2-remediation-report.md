# A9-LOCAL-M2 local receipt integrity remediation

2026-10-04. **REMEDIATED PENDING INDEPENDENT REVIEW; NOT CLOSED.**
Runtime A9 remains **BLOCKED B1/B2/B3/D1**. Only packet verification, tests and
scoped documentation changed. The [M1 independent report](a9-local-m1-independent-verification.md),
its missing-provenance FAIL and all earlier reports/receipts remain unchanged.
Root AGENTS, current authority through BL, Phase 9 ledger/index, B13/B19/C2 and
storage/engagement boundaries were reviewed. No listed skill applies to this
repository remediation; no external artifact/app workflow was used.

## Exact RED and current-source GREEN

Before edits, the original independent probe ran unchanged through the existing
offline/data-denying runner: **0 PASS / 1 FAIL, 1.44s**. Valid saved M1 packet:
37 modules, accepted. Copy with only `scripts.a9_candidate_adapter` removed:
36 modules, still PASS, incorrectly accepted. The expected exception failed with
`DID NOT RAISE ValueError`. Original probe SHA-256:
`5cd8f1db2036e96a0268b9b22625e97e234a15f9bad5ac1122a5ddd74a0272f6`.
The new RED receipt is `scratch/a9-local-m2/exact-red.xml`.

After remediation, the same assertions and deletion attack pass: **1 PASS, 0.78s**.
Only the probe's input filename changes from `a9-local-m1-manifest.json` to the
[fresh M2 manifest](a9-local-m2-manifest.json). Probe SHA-256:
`2fe0e8bc7c71ab149b04e82dd26db838c23d5eef03e812c120a2db9390e8dd9f`.
This is an author rerun with a fresh-source fixture, not a byte-identical original
probe GREEN or independent closure. The historical M1 manifest is not rewritten;
it cannot pass the current-source check after verifier/test bytes change, and
pre-M2 receipts also lack the required checksum. Never retrofit a checksum onto
old evidence to claim a fresh measurement. The repository regression uses the
same attack without a fixture-specific module count.

The original M1 stale-import probe remains byte-identical (SHA-256
`bb7a1f3c92918215b2da782d3fd8d4eb5f5c21d2d6aa3bd04205262632541867`):
**1 PASS, 4.54s**. Both stale-parent and reloaded-parent measurements execute the
changed adapter and return PARTIAL/unexpected_fault on operation one, clean their
temporary DBs and report zero remaining workers.

## Explicit integrity contract

- Worker return and saved-packet reuse call one receipt validator. Required
  compiled entrypoints are the packet builder, measured adapter and local harness;
  package parents must also have provenance. These follow the execution protocol,
  not the observed number 37 or fixture hashes.
- Every module entry has exactly a path and hash. Names must be valid identifiers
  in the frozen loader's namespaces, resolve to its exact package-first canonical
  source path, have unique paths and match the captured source hash. Missing,
  extra, renamed, aliased, malformed and mismatched entries fail closed.
- A worker-generated `receipt_sha256` covers the entire packet except that field,
  including the complete measured module map, source, config, scenario, execution
  metadata and observations. Any deletion/addition of even an otherwise optional
  valid module changes it. The parent validates before accepting the receipt,
  then recalculates after its own exit/source/guard bookkeeping. The saved check
  requires the checksum, current source identity, export and bootstrap binding,
  strict exit/isolation/parent-guard types and unchanged-source flag.
- Raw JSON passed to `verify_packet()` rejects duplicate object keys, including
  repeated module names; worker response decoding uses the same strict decoder.
  Existing dict callers remain supported. A dict already decoded by ordinary
  `json.loads` cannot retain evidence of duplicate JSON keys; use raw JSON for
  saved-file validation. Reordering keys does not change canonical identity.

This is **local integrity checking, not cryptographic authentication**. No signing,
key infrastructure, external attestation or broader trust system was added. A
writer who consistently rewrites all records and recomputes checksums is outside
this boundary; the checksum is not an independently trusted signature. Required
entrypoint/schema/path/binding checks remain independently enforced even if that
checksum is recomputed. There is no hardcoded expectation that all allowlisted
source files execute, or that exactly 37 modules must execute in every scenario.

M1 frozen-byte loading, isolated interpreter, 10s parent deadline, bounded reap,
EOF guard and normal 5s/1s measurement/cleanup paths remain. Forced termination
still returns no certificate and does not guarantee synthetic DB cleanup. No
hostile-code sandbox, dependency binary proof, OS quota, parent hard-kill cleanup,
kernel-hang, Pi/ARM64 or representative workload guarantee is inferred.

## Validation and exact artifacts

- Focused packet/harness: **126 PASS, 80.92s** (81 retained plus 45 M2 cases).
  Negative coverage includes removal of every measured module, required entrypoints
  even with a recomputed checksum, entry schemas, added/duplicate/renamed paths,
  source/bootstrap binding, JSON duplicates, and worker-return refusals. Existing
  frozen capture, stale pycache, cancellation, crash, timeout and cleanup checks pass.
- Relevant SQLite concurrency/lifecycle, engagement events/failures/birthdays and
  import architecture: **41 PASS, 5.87s**, isolated temporary data/fakes only.
- Fresh capture/verify: **1 PASS, 1.94s**; 146 source files, 37 compiled modules,
  eight operations, normal cleanup and zero remaining workers. Two final document
  link/anchor checks are recorded in the evidence. Counts are separate runs;
  attack/capture controls are not extra pytest cases.
- No giant full-suite rerun: this verifier-only change is covered by the focused
  suite and relevant regressions. Historical **1673 PASS / 2 FAIL / 27 SKIP** and
  **1652 PASS / 3 FAIL / 27 SKIP** remain historical, including the earlier artifact
  ordering failure. Known document-inventory and Deno failures remain open.

Four dependency mismatches remain accurately disclosed: bgutil-ytdlp-pot-provider
pin 1.3.1, deno pin 2.9.7 and yt-dlp-ejs pin 0.8.0 have no installed distribution
version; yt-dlp installed 2026.7.4 differs from pin 2026.8.19. Metadata is not a
fresh executable/ABI investigation. No install or dependency adjustment occurred.

SHA-256 identities:

| Artifact | SHA-256 |
| --- | --- |
| `scripts/a9_candidate_packet.py` | `249606fff08388e0e88bfd37bae3b796512169b267e406ed968728154e2c14b5` |
| `tests/integration/operations/test_a9_candidate_packet.py` | `e066a4ad3a9f00b0538e3b6ffca4569b53fc8f11d01f006686d95ea66387137a` |
| `a9-local-m2-manifest.json` | `387b6406aef0715be01aa0279c50e1babde94b2cf14db83d44e222d5cc12dad3` |
| Frozen source export | `573d85f550a705146c0f20a7fc1f360ab3b5b1ffdf1d6157da605db4f19a8eb7` |

[Evidence and ownership](a9-local-m2-evidence.json) records exact commands, receipt
hashes and all seven owned deliverable paths. `scratch/a9-local-m2/owned.patch`
is the entry-relative delta, with before bytes for the four existing files.

## Preservation, rollback and STOP

The 675-file prior inventory and the subsequently added independent M1 report
are preserved except the four authorized edits. Of the original 675, 670 unchanged
safe files are byte-checked; four edited files have retained entry bytes, and the
protected `docs/rebuild/bot_database.db` is not opened or hashed. Its size/mtime
remain unchanged (metadata-only evidence, not a new byte-integrity claim).
Similarly, the inherited 642 unowned set has 641 exact hashes plus that protected
file's metadata-only check. All historical reports/manifests/evidence and prior
test receipts remain byte-identical. CHANGELOG and current active-state changes
are strictly appended. HEAD `769a00ab892edc7f98a1f9d947abd23d99c1056a` and empty index
remain unchanged; no staging, commit or push.

Rollback restores only the four recorded entry files (preserving any later edits
by applying the inverse owned delta) and removes only the three new M2 documents.
It has no application data/service consequence. Scratch evidence can be retained;
no historical receipts or unrelated working-tree changes are removed.

**STOP for independent review of M2; the finding is not CLOSED.** No Watch packet,
music/runtime features, Pi/SSH/network, credentials, production data, installs,
deployment or permission changes. No A10, Integrated Audit or Phase 11. Runtime
A9 remains BLOCKED; independent verification is the next separately scoped step.
