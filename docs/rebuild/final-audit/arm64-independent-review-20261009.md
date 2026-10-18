# Independent ARM64 dependency artifact review - 2026-10-09

**PASS, bounded to the prepared 64-wheel artifact set and static target dependency
compatibility.** No material artifact defect found. This closes the pending independent
review in [the extras preparation report](arm64-extras-closure-20261009.md), not installed
ARM64 execution, service readiness, operational acceptance or deployment approval.
The original [61-wheel PARTIAL](arm64-dependency-artifacts-20261009.md) remains historical.

## Inspected identity and authority

Read root AGENTS, current active-state/ledger/document-index, C13 dependency/deployment
contract, requirements, canonical sealing/verification code, relevant deploy runbooks,
source-freeze and post-install evidence, both ARM64 reports and actual manifests.
No additional applicable AGENTS was found. The visible related chats were idle at entry;
this is a bounded concurrency observation, not proof against every external writer.
Entry/final byte and Git comparisons provide the preservation evidence.

Branch **codex/rebuild-v2**, HEAD **cb54da9948370db64133a0ead6c9df89d0b61055**;
entry **25 modified / 99 individually enumerated untracked files**, empty index.
HEAD is unchanged but does not identify these dirty source bytes. No fetch was run.
Index SHA256: `567e4ee312ef2b1baf37cf249a4e6437cd3679044a0eaff6b8aa5af216374268`.

| Inspected identity | Fresh SHA256 |
| --- | --- |
| 377-file source map | `3f99198f63a585848d1236f9b654a9c1a50b7a5e1de914a8866800556a87173d` |
| Source-manifest JSON file itself | `555db02aa2341f833e503e48a387f991a2bda935827d7d4e138fb4900f96467b` |
| deploy/dependencies.pins | `3fe9f232fa36041c77db9da3de60d0c8f732e693bed708697c5296e4786c431f` |
| Canonical wheel-lock.json | `bd1ffa96253a4d84b8f229cee226699c54fd3f50ca74b82fa3255adb29093bac` |
| dependencies.lock = requirements.lock | `58d3c6fbe0e7cec5d3340d8c625fef32355b8643a0a2240bf7c218ab6b0f70d9` |
| Artifact-manifest JSON | `edac5243e4aec7780bd127c99ad6a772ebfc40ba671f5031769b885009b7fcf6` |

Source identity is SHA256 of sorted compact UTF-8 JSON `{relative_path: raw_sha256}`,
without a newline. Each of the 377 current files was rehashed. Other table entries
hash raw file bytes. Wheel-lock serialization is sorted compact JSON **with** final
LF, matching `atomic_json`; generated dependency rows are sorted and LF-terminated.
The three manifest inventories checked contain 100 current artifact entries,
105 current final-inventory entries and 182 historical artifact entries; these overlap.

Target is **historical 2026-10-09 07:18:20 UTC metadata**: CPython 3.12.3, Linux
AArch64, glibc 2.39, SOABI `cpython-312-aarch64-linux-gnu`, 64-bit, non-debug.
No fresh Pi/SSH observation occurred. Recorded production remains source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`; neither was re-audited.

## Fresh checks and reproducible commands

Reviewer code and receipts are in the new ignored directory
[`scratch/arm64-independent-20261009-01`](../../../scratch/arm64-independent-20261009-01/).
No author validator was executed or used as the independent result. Existing installed
`packaging` parsed metadata/tags, and installed `cryptography` checked cached signatures;
no downloaded package code was extracted, imported, installed or executed.

Commands from repository root (each mode was executed, not merely proposed):

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git diff --cached --stat
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/review.py snapshot
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/review.py identities
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/review.py artifacts
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/review.py publisher
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/supplement.py
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/route.py
.\.venv\Scripts\python.exe -I -B scratch/arm64-independent-20261009-01/finish.py
git -c core.safecrlf=false diff --check
git diff --cached --check
```

Helpers create receipts exclusively and must use a fresh output directory for replay.
Initial reviewer-only failures were corrected: wheel-lock check omitted the contract's
final LF, and a requirements read inherited Windows cp949 instead of explicit UTF-8.
The initial helper remains saved; neither failure changed an artifact or assertion
about its contents. All substantive final commands exited 0. Initial publisher reads
returned 64 URLError/BLOCKED results under the default network sandbox. The same bounded
metadata-only command then received automatic escalation approval and returned 64 PASS;
both receipts are retained. No manual permission or wider operation was inferred.

| Fresh verification | Result |
| --- | --- |
| Pins / wheel lock / dependency lock / C13 | 64 exact versions agree; old 61 entries unchanged; both text locks byte-identical to independent reconstruction |
| Artifact size and publisher checksums | 64/64 PASS; **66,338,086 bytes**; fresh official version-specific PyPI JSON, filename, SHA256, size, non-yanked state and Requires-Python match |
| Wheel structure | 64/64 filename/METADATA identity, Requires-Python, WHEEL/filename tags and supported wheel format PASS |
| Archive and RECORD | **4,308 hashed members** and 64 intentionally unhashed RECORDs; full file coverage, size/digest/CRC, unique paths including casefold, no traversal/absolute/backslash/drive paths, links, special files, encrypted members or startup hooks |
| Target closure | 20 root declarations, 2 propagation passes, **106 active edges**, **273 inactive edges**, zero missing pins/version conflicts/unknown requested extras |
| Native static checks | **64 ELF members across 16 distributions**, ELF64 little-endian AArch64; parsed dynamic/version-needs sections, max required GLIBC **2.28**, compatible with recorded 2.39 |
| Cached supplementary attestations | Freshly verified **39 leaf DSSE signatures** and subjects: 38 exact filenames, 1 separately disclosed gTTS case-normalized identity/digest match |
| Installed Windows preservation | **65 distribution versions** and **7,748 recorded package-file hashes** unchanged; no install |

The wheelhouse contains exactly 64 wheels plus two lock files. Tags were constructed
for CPython 3.12/cp312, compatible older abi3 and universal tags, and AArch64 manylinux
floors up to 2.39, including the manylinux2014 alias. Windows host tags were not used.
All marker fields were explicit; no dependency uses unknown `platform_release` or
`platform_version` fields. Every pinned distribution's base dependencies were checked,
with recursive extras propagated to a fixed point. Active extras are precisely
`discord-py[voice]`, `google-auth[requests]`, and `yt-dlp[default]`.

Provenance is official HTTPS PyPI release metadata and recomputed published artifact
SHA256, not an assertion that publisher accounts or package code are harmless.
Fresh URL/digest receipts: [publisher-approved.json](../../../scratch/arm64-independent-20261009-01/publisher-approved.json).
Full details: [identities](../../../scratch/arm64-independent-20261009-01/identities.json),
[static checks](../../../scratch/arm64-independent-20261009-01/static.json),
[supplement](../../../scratch/arm64-independent-20261009-01/supplement.json).

## Findings, historical evidence and limits

- **Minor explanatory discrepancy:** the preparation reports mention activated
  `httpx socks`. Neither requirements nor target metadata activates that extra.
  The author's saved GREEN extras map agrees with this independent result; socks
  requirements are correctly inactive. No missing required dependency or pin change
  follows, and no remediation gate is invented for this wording. Old reports retained.
- Required external ELF libraries are `ld-linux-aarch64.so.1`, `libc.so.6`, `libdl.so.2`,
  `libgcc_s.so.1`, `libm.so.6`, `libpthread.so.0`, `libstdc++.so.6`. Parsed non-glibc
  requirements reach GLIBCXX_3.4.22, CXXABI_1.3.11 and GCC_4.2.0. Their actual target
  availability/resolution, CPU instructions, Python loading, Deno/EJS/provider execution,
  FFmpeg/libopus/media and services remain **NOT_RUN**. Static compatibility cannot
  establish these facts.
- Attestation availability was not refreshed: the saved preparation evidence reports
  **25/64 unpublished**. Fulcio chain, certificate-time/trust-root and Rekor
  inclusion/checkpoint validation remain **NOT_RUN**; the 39 leaf checks are supplementary,
  not full Sigstore validation. Missing attestations alone are not a release gate.
- Historical Windows full-suite receipt remains **1896 collected / 1869 PASS / 0 FAIL /
  0 ERROR / 27 Linux-only SKIP / 0 NOT_RUN**. Its source identity was
  `2cf256d2c514fcab18083d01fc177c76831b2d0791e127a95892a5fa6788ae6c`.
  Fresh comparison finds only `deploy/dependencies.pins` changed across the 377-file map;
  runtime/tests and installed Windows versions are unchanged. This is historical
  regression evidence, not a fresh run or target-venv acceptance. Full suite and the
  author's four offline tests were deliberately **NOT_RUN here**.
- No installed-release manifest, current committed source freeze, effective configuration,
  actual Pi execution, load/soak/recovery, service readiness or operational approval is
  produced. Original A9/A10 BLOCKED, Integrated administrative SCOPE-CLOSED, all 23
  operational obligations and deferred P11 retain their separate scopes.

## Preservation, disposition and exactly one next task

Fresh final comparison preserves **1,068 inherited safe source/document files**, except
the three exact additive routing notices, **344 prior artifact/receipt files**, the
377 source files and 7,748 installed package files. Original source-only archives,
61-wheel and 64-wheel trees, reports and evidence remain unchanged. Git HEAD/branch/
refs/index and every inherited status remain unchanged; final status adds only this
report (**25 modified / 100 untracked**, individually enumerated). Only this report
and notices in `final-audit-active-state.md`, `final-audit-ledger.md`, and
`final-audit-document-index.md` affect nonignored content. Reviewer scripts, receipts,
public metadata and before-images are confined to the new ignored scratch directory.
See [preservation receipt](../../../scratch/arm64-independent-20261009-01/preservation.json).
Documentation rollback is removal of only these exact additions; it was not performed.
No source/test fix, data/credential access, Pi/SSH, service change, install, deletion,
commit, push or deployment occurred.

**Next task: materialize the reviewed source as a truthful, locally committed release
candidate and freeze its source/dependency identity.** Review and split the release
changes into atomic local commits, preserving unrelated inherited work; export the
resulting full 40-hex commit through the existing source boundary, compare its selected
bytes with this 377-file source evidence (distinguishing source-review inputs from the
installed payload), and produce a new source artifact/manifest tied to the exact reviewed
wheel-lock and dependency-lock hashes. Preserve all older bundles. Do not label dirty
HEAD `cb54da9...` or the historical source-only ZIP as that new release.

Prerequisites: these verified bytes remain unchanged, the intended staged changes pass
the required scope/secret/diff review, and the existing historical test identities remain
applicable; any new source change requires its own appropriate validation. **New authority
needed is the follow-up task's explicit authorization for local commits and candidate
freeze**, excluded from this review. No Pi, installation, service, push or deployment
permission is needed for that local task, and none is requested or implied here. C13
requires a full committed source revision before Builder can truthfully identify a
release, making this concrete work the next gate rather than another planning stage.

**Review STOP. The next task was not started.**
