# Local committed release-candidate freeze - 2026-10-09

**Local source/lock freeze only; not installed or deployment-ready.** The delegated
owner instruction authorizes reviewed local commits and source export, and stops
before target execution. This report and the detached final manifest identify the
new candidate; neither dirty baseline HEAD nor production identifies it.

## Authority, entry and provenance

Read root AGENTS, current active-state/ledger/document-index, C13 deployment/source
contract, C14 backup contract, the operational register and the ARM64 independent
review and referenced manifests. `.agents/skills` is absent. No applicable nested
AGENTS is tracked. Related visible tasks were idle/not loaded; this is a bounded
concurrency observation. Entry/final byte and index checks supplement it.

Entry branch: `codex/rebuild-v2`; HEAD
`cb54da9948370db64133a0ead6c9df89d0b61055`; **25 modified / 100 individually
enumerated untracked files**, empty index. No fetch or remote freshness claim.
Entry index SHA256:
`567e4ee312ef2b1baf37cf249a4e6437cd3679044a0eaff6b8aa5af216374268`.
The freeze receipts are in `scratch/release-freeze-20261009-01/`, a fresh ignored
directory. Original work and earlier archives remain in place.

| Local commit | Reviewed responsibility and provenance |
| --- | --- |
| `5daca299d80a2ab531f71ab9161cfa6cbd224f79` | Backup destination policy, final current/history tests, C14/runbook/changelog and BT1 author/reviewer evidence; BT1-V1 independent PASS and later admission split evidence |
| `2d9523ab7b7746d4a8bb9e81a47ab6a17ee1c410` | Exact shared installed selection, both callers, selection tests, README/C13/changelog hunks and admission evidence chain; historical independent 588 installed / 127 source PASS |
| `2c581116a0e4fd3f818d300d38966d24d703dc0b` | Canonical source-only import adapter, rejection tests and author/reviewer evidence; bounded independent tooling PASS |
| `168d72802acee6e8d861ebfa7e33560a06938f0f` | A2-N1 inventory checker, negative tests and independent closure evidence; fixed partitions and authority reachability retained |
| `ea43fd4a708cb064fd36a17701590fb63ff1a9ba` | Inherited synthetic Watch trace fixture only; present in the exact reviewed source maps and historical canonical source suite; no fresh browser execution claim |
| `c78d06cf73199f1b19c154fc36617807f4993dbc` | Three approved required-extra pins, C13/changelog clauses, ARM64 preparation/review and historical Windows regression report |
| `d05c135d0d992c11c0e10bbf2ad3aaf4cdcfe3e0` | Representation-only preservation of original reviewed pin bytes so the committed export satisfies the unchanged wheel lock |

The final documentation commit adds this report, only the new routing notices in
the two tracked audit authorities, and a zero-context patch for the inherited
untracked document index. Its full commit ID and the resulting export are recorded
in the detached manifest, avoiding self-reference. Each commit body records
validation provenance and a scoped revert approach. No commit includes unrelated
Watch drivers, invitation material, handoff archive, operational data or caches.

Existing reports remain historical, including old pending-review and blocked text.
Runtime/source/test bytes were not repaired or rewritten in this task. The old
BT1 review `.diff` remains untracked: its valid context-space lines fail the general
staged whitespace check, and changing that historical artifact would invalidate
its recorded raw identity. Its original contents are retained locally.

## Source and exact lock identities

The [independent ARM64 review](arm64-independent-review-20261009.md) remains the
authority for the **64-wheel static PASS**. Fresh comparison verified all 377
reviewed current raw source hashes and all supplied manifest/lock hashes.

| Identity | SHA256 |
| --- | --- |
| Reviewed raw 377-file source map | `3f99198f63a585848d1236f9b654a9c1a50b7a5e1de914a8866800556a87173d` |
| Original source-manifest file | `555db02aa2341f833e503e48a387f991a2bda935827d7d4e138fb4900f96467b` |
| Original artifact-manifest file | `edac5243e4aec7780bd127c99ad6a772ebfc40ba671f5031769b885009b7fcf6` |
| Raw committed pins | `3fe9f232fa36041c77db9da3de60d0c8f732e693bed708697c5296e4786c431f` |
| Unchanged wheel lock | `bd1ffa96253a4d84b8f229cee226699c54fd3f50ca74b82fa3255adb29093bac` |
| Unchanged dependencies.lock and requirements.lock | `58d3c6fbe0e7cec5d3340d8c625fef32355b8643a0a2240bf7c218ab6b0f70d9` |
| Committed equivalents of the 377 reviewed inputs | `03bc73c3fa46518bd96d66fedbda6e07f6bdd05608690774738efb5a2350e74c` |
| Exact 373-file committed export map | `4095dbf2e12e8d7d8cc2eb17db2c99a700e0fd9748037fa1ec47da48d9ef3a75` |

Map hashes use sorted compact UTF-8 JSON `{relative_path: raw_sha256}`, without a
final newline. File hashes use raw bytes. All 64 wheel files were freshly hashed:
**66,338,086 bytes**, matching the unchanged canonical lock. The two text locks
equal independent reconstruction from that lock; pin names and versions agree.
No publisher query, download, wheel extraction, install or wheel code execution.

### Git newline representation

The checkout has `core.autocrlf=true`. Across the 385 input union (377 reviewed plus
eight unchanged tracked payload supplements), 68 files differ only by CRLF-to-LF
conversion; the comparison manifest records both hashes and the relation per file.
No semantic source difference is concealed by a matching aggregate hash.

Pin policy needs stricter raw equality because `verify_wheels` hashes it directly.
The ordinary pin commit initially stored LF hash
`b645d09dc8b62fd60d3ce7d8ae34d72c4680d3ff2d1c1d2e0f63e27e5c338c94`, and the export
preflight correctly failed. The representation-only follow-up stores the untouched,
reviewed mixed-line-ending artifact verbatim (58 CRLF endings). No runtime, version,
working file, lock or repository configuration changed. Its staged semantic diff
with `--ignore-space-at-eol` is empty. Default `git diff --cached --check` identifies
those 58 CR endings; the explicit one-command `core.whitespace=cr-at-eol` check
passes. All other staged scopes pass the default check. This disclosed exception
preserves the exact independently reviewed dependency identity.

## Export boundary and detached identity

The supported export uses SourceBuilder's operation and exact selected roots, with
the final full commit and automatic newline conversion disabled for this invocation:

```text
git -c core.autocrlf=false archive --format=zip --output=<new-owned-source.zip> <40-hex-commit> src tests deploy pyproject.toml requirements.txt requirements-dev.txt
```

No Builder/venv/install/publication path runs. The ZIP's Git comment must equal its
commit, and every file must equal that commit's blob. Existing
`verify_candidate.safe_archive` and additional bounds, path, casefold-duplicate,
mode/link, encrypted-member, forbidden-file and CRC checks verify the archive.

The first plain `git archive` inherited Windows `core.autocrlf=true` and converted
LF blobs to CRLF. The byte-equality guard rejected it; no non-line-ending difference
was found. That rejected ZIP remains under `frozen/` with a separate failure receipt.
The final export under `frozen-raw/` disables conversion for one command only;
repository configuration and runtime/source files are unchanged. A separate
documentation correction records this observation without rewriting earlier commits.

The 373 exported files comprise **365 of the reviewed inputs plus eight unchanged
tracked files**: the polkit rule, off-host service drop-in, three existing browser
drivers/helpers and three synthetic client harnesses. Those eight were omitted by
the old extension-filtered source map; each is explicitly compared with entry HEAD
and locally reviewed. No untracked browser driver is silently added.

The remaining **12 source-review-only inputs** are root conftest, the canonical
runner and its two import-probe files, and eight scripts. They stay outside the
installed payload under the existing contract; the source-comparison manifest
lists all twelve. The source lane still depends on repository history and preserved
local audit documents. Untracked canonical authorities, reports and scratch receipts
are not silently adopted: this freeze is **not a portable full-source audit bundle**,
and no clean-checkout full-suite PASS is claimed.

The new `scratch/release-freeze-20261009-01/frozen-raw/` contains the final source ZIP,
`source-manifest.json`, `source-comparison.json`, exact copied original review
manifests, wheel lock, both text locks, export command and `SHA256SUMS`. Wheels remain
at the original preserved wheelhouse, bound by their exact hashes. No package cache
is committed. Final commit/archive/manifest hashes are in the detached result and
the supervisor handoff, not inserted recursively into the commit they identify.
The manifest excludes its own hash; SHA256SUMS binds it externally. The final report
does not cause an endless source-commit/archive/hash rewrite cycle. Windows read-only
attributes guard against ordinary accidental edits, not malicious owner changes.

## Fresh checks, preservation and limits

Fresh guarded offline selection: **22 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, 8.406s
outer / 7.25s pytest. Fourteen documentation, four asset and four admission-selection
cases; no asynchronous test is selected. Seven unknown-asyncio-mark warnings arise
from imported fixture modules with plugin autoload disabled. They are disclosed;
RuntimeWarning/unraisable controls and strict xfail remain enabled. Exact command,
console and JUnit are saved in the new receipt directory. Historical canonical
**1869 PASS / 27 Linux-only SKIP** is reused by exact source correspondence and is
not a fresh run. No whole-suite repetition was authorized or needed for this freeze.

Entry records fingerprint 1,069 safe source/document files and 360 previous local
artifact/receipt files. Final preservation must match all original bytes except
the three exact additive routing notices. Mixed README/CHANGELOG and audit-history
changes remain unstaged; the untracked document index keeps inherited ownership.
The final receipt enumerates every remaining dirty path and every scoped commit.
Staged source/report scans reject common private-key and token patterns; synthetic
fixtures and non-secret configuration templates remain. No operational DB, SQL
backup, credential file or log contents are read, staged or exported.

Original A9/A10 operational acceptance remains BLOCKED; Integrated administrative
SCOPE-CLOSED is distinct. All **23** obligations in the
[operational register](operational-verification-register-20261009.md) retain their
original identity, timing and acceptance criteria. Deferred P11 execution remains
deferred. Recorded production is still source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`; there is no fresh production observation.
Native ARM64 loading/linking, target libraries/media/service execution, effective
configuration, installed manifest, readiness, current recovery proof and operational
approval remain unverified. No target activity starts here.

**One next gate:** independently accept the exact final committed source ZIP and
detached source/lock binding, including the disclosed newline representation and
source-review/payload split, before separately authorizing any ARM64 offline build
or installed admission. This local commit/freeze task stops here; no push, Pi/SSH,
installation, service action, production change, deployment or cleanup follows.
