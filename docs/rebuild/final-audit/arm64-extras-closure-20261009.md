# Linux ARM64 required-extras closure - 2026-10-09

**PASS for local artifact preparation; independent artifact review pending.**
The authoritative policy now has **64 exact pins**, and a separate wheelhouse
contains all 64 compatible artifacts with canonical locks. Base and recursively
declared extras closure both PASS; **zero missing wheels or dependencies**.
This is not an installed release, native execution certificate or deployment approval.

## Authorized correction and RED/GREEN evidence

The supervisor explicitly authorized the three versions already approved and
tested in the Windows development environment: `brotli==1.2.0`,
`mutagen==1.48.1`, `pycryptodomex==3.23.0`. They satisfy the existing
`yt-dlp[default]==2026.8.19` requirement; no new feature or optional extra was chosen.
Root AGENTS, current audit routing, C13 dependency/deployment contract, requirements,
canonical sealing code and existing asset/build tests were reviewed.

Only the authoritative `deploy/dependencies.pins` gains those three alphabetically
placed pins and a corrected header. All previous 61 versions remain identical.
`requirements.txt` already declares the extra and stays unchanged. C13 records the
64-pin correction and extras-review requirement; CHANGELOG records this change.
No obsolete fixed-61 expectation was found in `src`, `tests`, `deploy` or `scripts`
source; unrelated numeric literals and all tests/rejection rules were left intact.

| Verification | Before correction | After correction |
| --- | --- | --- |
| Exact pins / verified wheels | 61 / 61 | 64 / 64 |
| Base dependency closure | PASS | PASS |
| Required recursive extras closure | RED: exactly brotli, mutagen, pycryptodomex unpinned | GREEN: no missing/version-mismatched dependencies |
| Old lock against old pins | PASS | Historical pair remains PASS |
| Old lock against corrected pins | Not applicable | Correctly REJECTED with DataIntegrityError |
| New canonical lock against corrected pins | Not applicable | PASS |
| Existing offline asset-policy tests | Existing unchanged tests | 4 PASS / 0 FAIL / 0 SKIP, 1.969s outer |

The RED closure was freshly reproduced before editing the pins. Both phases used
the same artifact/marker validator, with only phase-specific receipt destinations
and input manifests. Root requirements and recursively propagated extras include
Discord voice, httpx socks and yt-dlp default for the explicit Linux/CPython target.
Original validation assertions remain intact; no missing dependency is ignored.

## Exact candidate and local artifacts

Branch remains `codex/rebuild-v2`, HEAD
`cb54da9948370db64133a0ead6c9df89d0b61055`; no fetch, commit or push. No remote
freshness is claimed. The reviewed 377-file source map changes only
`deploy/dependencies.pins`; runtime and test source bytes are unchanged. Source
identity hashes sorted compact UTF-8 JSON `{relative_path: raw_sha256}` with no newline.

| Identity | SHA256 |
| --- | --- |
| New 377-file source | `3f99198f63a585848d1236f9b654a9c1a50b7a5e1de914a8866800556a87173d` |
| Corrected raw pins | `3fe9f232fa36041c77db9da3de60d0c8f732e693bed708697c5296e4786c431f` |
| New canonical wheel-lock.json | `bd1ffa96253a4d84b8f229cee226699c54fd3f50ca74b82fa3255adb29093bac` |
| New dependencies.lock / requirements.lock | `58d3c6fbe0e7cec5d3340d8c625fef32355b8643a0a2240bf7c218ab6b0f70d9` |
| Artifact manifest | `edac5243e4aec7780bd127c99ad6a772ebfc40ba671f5031769b885009b7fcf6` |

Owned ignored root: `scratch/arm64-extras-20261009-01/`.

- [Artifact manifest](../../../scratch/arm64-extras-20261009-01/artifact-manifest.json),
  [source map](../../../scratch/arm64-extras-20261009-01/source-manifest.json),
  [canonical wheel lock](../../../scratch/arm64-extras-20261009-01/wheels/wheel-lock.json),
  [dependency lock](../../../scratch/arm64-extras-20261009-01/dependencies.lock).
- [Fresh RED](../../../scratch/arm64-extras-20261009-01/red-dependency-closure.json),
  [fresh GREEN](../../../scratch/arm64-extras-20261009-01/green-dependency-closure.json),
  [64-wheel verification](../../../scratch/arm64-extras-20261009-01/green-wheel-verification.json),
  [canonical rejection checks](../../../scratch/arm64-extras-20261009-01/canonical-checks.json),
  [unit receipt](../../../scratch/arm64-extras-20261009-01/unit-result.json),
  [JUnit](../../../scratch/arm64-extras-20261009-01/unit.xml).
- [Three artifact provenance records](../../../scratch/arm64-extras-20261009-01/extras-acquisition.json),
  [attestation availability](../../../scratch/arm64-extras-20261009-01/extras-attestations.json),
  [ELF static review](../../../scratch/arm64-extras-20261009-01/elf-static-review.json),
  [preservation](../../../scratch/arm64-extras-20261009-01/preservation.json),
  [complete final inventory](../../../scratch/arm64-extras-20261009-01/final-inventory.json).

**64 wheels / 66,338,086 bytes; 62 reused and two newly downloaded.** The previous
61 wheels were copied byte-for-byte into the new directory; universal Mutagen was
reused from the prior approved Windows preparation. Only Brotli and PyCryptodomeX
required downloads. Official version-specific PyPI metadata and file-host SHA256/
size matched all three. No source builds, substitutions or other packages.

| Added artifact | Publisher SHA256 |
| --- | --- |
| brotli-1.2.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl | `acec55bb7c90f1dfc476126f9711a8e81c9af7fb617409a9ee2953115343f08d` |
| mutagen-1.48.1-py3-none-any.whl | `4f077fe87d3fc7fba259aa63d8c026b18382ca6a42ef37c61e16f1b1b5b82fe7` |
| pycryptodomex-3.23.0-cp37-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl | `43c446e2ba8df8889e0e16f02211c25b4934898384c1ec1ec04d7889c0333587` |

## Compatibility, provenance and execution limits

Target evidence is reused unchanged from the successful **2026-10-09 07:18:20 UTC**
minimal bot SSH query: **CPython 3.12.3, Linux aarch64, 64-bit, glibc 2.39,
SOABI cpython-312-aarch64-linux-gnu, Py_DEBUG=0**. No new SSH/Pi operation was needed.
This is system-interpreter metadata, not an installed-candidate execution receipt.

All 64 wheels passed exact filename/METADATA/version/Requires-Python/tag checks,
ZIP path/duplicate/symlink checks and complete RECORD validation: **4,308 hashed
members**, plus 64 intentionally unhashed RECORD files. All **64 native ELF
members** are ELF64 little-endian AArch64 with embedded GLIBC symbol versions no
newer than 2.39. The wheel directory contains exactly the allowed 64 wheels and
two lock files; no unexpected archive, private-data filename or startup hook.
No wheel was extracted, imported, installed or executed. Static tag/ELF evidence
does not prove CPU capabilities, dynamic library availability or live voice/media.

All three added wheels' PyPI attestation endpoints returned 404. Prior supplementary
evidence remains 38 exact-subject signatures plus the separately disclosed gTTS
case-normalized signature; **25/64 have no published attestation**. Full independent
Fulcio/Rekor trust verification remains NOT_RUN. Publisher HTTPS/SHA256 and RECORD
integrity PASS are not represented as full Sigstore verification.

The unchanged `deploy/wheels.py` sealed and verified the fresh directory. Text
locks are byte-identical output from the existing verifier. No Builder, venv,
installer, target binary, provider request, DB, secrets or service was run.
Four existing static tests used the unchanged canonical credential/data/network
guards, disabled plugin autoload/cache/bytecode and a 45-second outer limit. Full
suite was intentionally NOT_RUN for this metadata-only correction; previous
588/127 admission and Windows 1,869 PASS/27 SKIP retain their historical identities
and are not relabeled as a new installed release test.

## Preservation and next gate

The full prior 61-wheel tree, manifests, source-only archives, old report and
earlier receipt files remain byte-preserved. All 7,748 recorded Windows package
files remain unchanged. Inherited dirty work, Git HEAD/branch/refs/index and every
unrelated file were preserved. Only pins, the additive contract/changelog notices,
three compact routing notices and this new report changed repository state.
The final preservation receipt records exact exceptions, before-images, owned diff,
source and artifact hashes; diff/link checks passed. No cleanup was performed.

A9/A10 operational acceptance, all 23 transferred obligations and deferred P11
remain unchanged. MyFood/MyMoney stay paused; My Moving is untouched. No source
archive refreeze, installed-release identity, operational PASS or cutover is claimed.

**One next gate: independent artifact review** of this exact 64-pin source/policy,
wheelhouse, canonical locks, RED/GREEN closure and provenance limitations. The
review does not authorize installation, Pi writes or deployment.
