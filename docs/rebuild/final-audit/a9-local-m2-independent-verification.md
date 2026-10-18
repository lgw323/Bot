# A9-LOCAL-M2 independent verification

2026-10-04. **PASS: A9-LOCAL-M2 independently CLOSED; M1 closure retained.**
This closes only the local executed-source/saved-receipt findings. Runtime A9
remains **BLOCKED B1/B2/B3/D1**. No runtime, Pi/ARM64, campaign or soak acceptance.
Historical FAIL reports and author pending-review records remain unchanged.

Reviewed root AGENTS, compact authority through BM and the previously established
Phase 9 boundaries; [M2 report](a9-local-m2-remediation-report.md), fresh
[manifest](a9-local-m2-manifest.json), [evidence](a9-local-m2-evidence.json), seven
owned hashes, entry-relative patch and actual verifier/loader/tests. No applicable
repository skill or `.agents` directory. No implementation changes during review.

## Independent proof

- **126/126 focused PASS**, 65.52s: packet and local harness regressions, including
  capture drift, stale imports/pycache, worker return validation, cancellation,
  timeout, crash, parent EOF, reap and ordinary DB cleanup.
- **20/20 independent PASS**, 19.97s, through `verify_packet(path.read_bytes())`
  on actual temporary saved JSON files. The valid delivered artifact and reordered
  JSON pass. All 37 individual module deletions and all 16 top-level field deletions
  are rejected. These loops are subchecks inside two tests, not 53 extra tests.
  Twelve cases verify required entries, empty map, missing package provenance,
  duplicate/renamed paths, wrong path/hash, extra entry fields, bootstrap binding
  and isolation types even after independently recomputing the checksum.
  Duplicate root, module-map and module-entry keys are rejected although ordinary
  `json.loads` would erase them. Two copied-source tests reject saved reuse after
  adapter/harness mutation. One fresh-measurement test validates source hashes,
  isolated-worker exit, all scenario checks, eight operations, zero remaining
  workers, normal cleanup and saved-file roundtrip.
- **Original M2 deletion attack: 1/1 PASS**, 0.65s. The intact fresh M2 packet is
  accepted; removing only the adapter entry is refused. Only the input manifest
  filename differs from the original probe's logical text; line endings/encoding
  also differ, so this is not claimed as a byte-identical original-probe GREEN.
  Original probe/assertions and RED receipt are preserved.
- **Exact original M1 attack: 1/1 PASS**, 3.70s. Unchanged probe SHA-256
  `bb7a1f3c92918215b2da782d3fd8d4eb5f5c21d2d6aa3bd04205262632541867`.
  Both stale-parent and reloaded-parent calls execute the changed frozen adapter,
  return PARTIAL/unexpected_fault at operation one, clean their temp DBs and report
  zero workers. Previously imported successful code cannot certify changed bytes.
- Final documentation link/anchor verification: **2/2 PASS** after this report was
  created. All runs used the existing offline/data-denying runner. Counts describe
  separate runs; overlapping behavior is not additional coverage. No full-suite
  rerun, provider request or service operation.

The independent saved-reader probe is retained at
`%TEMP%/test_a9_m2_saved_reader_independent.py`, SHA-256
`54c0e4c9f9e6d7995ac05a60ca1994d1141825c14d3bb94bc843037af63a7dee`.
Reproduce from repository PowerShell:

```powershell
$auditTempRoot = [System.IO.Path]::GetTempPath()
$auditProbePath = Join-Path $auditTempRoot 'test_a9_m2_saved_reader_independent.py'
.venv/Scripts/python.exe -B docs/rebuild/final-audit/a8r4-test-runner.py $auditProbePath --rootdir=$auditTempRoot --confcutdir=$auditTempRoot -q -s -x -p no:cacheprovider
```

Other fresh commands use the same runner with `-q -p no:cacheprovider`: the two
packet/harness test files; unchanged OS-temp M1 probe with temp root/confcutdir;
`scratch/a9-local-m2/test_receipt_green.py`; and the two documentation link/anchor
node IDs recorded in the remediation evidence. An initial audit utility compared
probe bytes too strictly and stopped on their line-ending difference; normalized
text comparison verified the filename-only logical change. This was not a product
failure or an additional pytest case.

## Why the repair meets the scoped contract

Worker return and saved reuse share receipt validation. A whole-packet checksum
covers observations, results and all provenance, not merely a subset of module
entries. Required packet/adapter/harness entrypoints and package provenance are
enforced separately; canonical name-to-path resolution, unique paths, source
hashes, bootstrap binding and strict execution-field types reject inconsistent
receipts even when their checksum has been refreshed. Raw JSON uses duplicate-key
rejection. Dict callers cannot recover duplicate keys already lost by another
decoder; saved-file callers must supply raw JSON, as documented and tested here.

M1's verified memory-byte loader, fresh isolated interpreter, separately hashed
bootstrap, 10s parent deadline and bounded reap remain. No new guard bypass or
measurement-identity regression was found. Forced exit still returns no certificate
and does not promise graceful temporary-DB cleanup. Kernel hangs, actual reparse
races, OS resource quotas and hard-killed-parent file cleanup remain outside proof.

The integrity model is accidental corruption/inconsistent identity. Checksums are
not signatures; a malicious writer consistently replacing and rehashing every
record is outside scope. No authentication infrastructure is required for closure.

Delivered manifest independently matches SHA-256
`387b6406aef0715be01aa0279c50e1babde94b2cf14db83d44e222d5cc12dad3`;
146 source files and 37 compiled modules match its frozen export
`573d85f550a705146c0f20a7fc1f360ab3b5b1ffdf1d6157da605db4f19a8eb7`.
Seven M2 receipt hashes/counts, nine original receipts and twelve M1 receipts match.
Author 41 relevant PASS and capture PASS remain separate historical runs.

Four dependency mismatches remain: no installed distribution version for pins
bgutil-ytdlp-pot-provider 1.3.1, deno 2.9.7 and yt-dlp-ejs 0.8.0; yt-dlp installed
2026.7.4 versus pin 2026.8.19. Distribution metadata/interpreter fingerprint does
not establish wheel hashes or ABI compatibility. Known inventory/Deno failures
remain open. Historical full-suite **1673/2/27** and **1652/3/27** PASS/FAIL/SKIP
records, including the artifact-ordering failure, are preserved without a clean
full-suite claim.

## Preservation and review boundary

All seven owned current hashes and four retained before-file hashes match. The
owned patch matches the four edits plus report/manifest; evidence JSON is the
separately hashed seventh file, as documented. Changelog/active-state edits are
strictly appended. The 699 safe-file audit snapshot remains unchanged. Original
preservation claims resolve to 670 prior safe unchanged hashes, four owned entry
files, one protected DB checked only by metadata, plus the subsequent independent
M1 report. Of the inherited 642 unowned entries, 641 retain exact hashes; the DB
has only unchanged size/mtime. This audit never opened or hashed that DB, and does
not convert metadata preservation into byte-integrity proof.

For scoped review/commit, M2 owns `scripts/a9_candidate_packet.py`,
`tests/integration/operations/test_a9_candidate_packet.py`, the M2 appendices in
`CHANGELOG.md` and `docs/rebuild/current/final-audit-active-state.md`, and
`a9-local-m2-remediation-report.md`, `a9-local-m2-manifest.json`,
`a9-local-m2-evidence.json` under this directory. This independent review adds only
this report. Preserve the underlying inherited deltas and every historical report;
do not stage the mixed whole tree. Entry-relative review evidence remains in
`scratch/a9-local-m2/owned.patch` and `owned-hashes.json`.

HEAD remains `769a00ab892edc7f98a1f9d947abd23d99c1056a`; index empty. No staging,
commit/push, runtime modification, credentials, Pi/network/services, installation,
deployment or permissions change. Rollback of this audit removes only this report.
**Next boundary: parent review and any separately authorized scoped commit.** No
automatic Watch/Music work or external campaign follows closure. External host
diagnosis/campaign still needs separate approval; A10/Integrated Audit/Phase 11 held.
