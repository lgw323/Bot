# Local Linux ARM64 dependency artifacts - 2026-10-09

**PARTIAL for artifact preparation only.** All **61/61 current exact pins** now
have one hash-verified target-compatible wheel and a canonical lock. No pinned
artifact is missing. Required extras closure is **BLOCKED**: `yt-dlp[default]`
requires **brotli, mutagen and pycryptodomex**, none present in
`deploy/dependencies.pins`. No pin, version, requirement or lock rule was changed.
This pin-only wheelhouse is not a complete deployable dependency set or release.

## Authority, candidate and target

Read AGENTS.md, current active-state/ledger/document-index, C13 deployment and
dependency policy, normal/first-staging runbooks, the source-freeze and latest
post-install canonical reports, and existing wheel/build/filesystem tooling.
No checkout `.agents` or `.codex` skill directory exists; no additional skill was
required. This assignment authorizes local artifacts and a minimal existing-SSH
metadata read, superseding older next-task wording only. No Git fetch occurred;
remote branch freshness is not asserted.

| Identifier | Exact value |
| --- | --- |
| Branch / HEAD | `codex/rebuild-v2` / `cb54da9948370db64133a0ead6c9df89d0b61055` |
| Current 377-file source SHA256 | `2cf256d2c514fcab18083d01fc177c76831b2d0791e127a95892a5fa6788ae6c` |
| Current raw pins SHA256 | `6bb473645ce5a9997bc8cbaf09086bdf350afc8510c3a196d7781e6c97dd3deb` |
| Canonical wheel-lock SHA256 | `14fcf06bf03d69157363f992e40958af6e0e76dcd36d58e90ae06e3d889ebcd1` |
| dependencies.lock SHA256 | `73e8df62a23b4e3d00ed63cd926af4ffc486503965e6e71149d5aceec89b621e` |
| Artifact-manifest SHA256 | `540f0529b2996ada9c7e45f34e848431d182f57b55ac6318113b1140de3cc684` |

Source identity uses sorted compact UTF-8 JSON of the prior canonical
`{relative_path: raw_file_sha256}` map, without a newline. All 377 actual files
match the latest reviewed source. HEAD alone excludes dirty candidate bytes;
no new release ID or source archive was created. The old source-only ZIP and its
hash remain historical evidence and were not repurposed for current bytes.

October 8 host evidence established Ubuntu 24.04.4/aarch64 and a manifest-recorded
Python 3.12.3, but did not freshly verify interpreter ABI or libc. One successful
read at **2026-10-09 07:18:20 UTC** used existing SSH alias `bot`, strict host-key
checking, no host-key updates/multiplexing, and `timeout 15s python3.12 -I -B -`.
Only standard-library interpreter/platform metadata was returned:
**CPython 3.12.3, Linux aarch64, 64-bit, glibc 2.39,
SOABI `cpython-312-aarch64-linux-gnu`, empty ABI flags, Py_DEBUG=0**.
This is the system target interpreter, not execution inside the protected installed
release. No application import, DB, service, benchmark, remote file or configuration
operation occurred. The initial sandbox DNS failure and successful approved network
retry are retained. WSL/x86 supplied no target evidence.

## Artifacts and verification

Owned ignored root: `scratch/arm64-artifacts-20261009-01/`.

- [Artifact manifest](../../../scratch/arm64-artifacts-20261009-01/artifact-manifest.json)
  inventories all preparation inputs/receipts and each wheel by relative path,
  size and SHA256; no host credentials, IP address or private configuration.
- [Canonical wheel lock](../../../scratch/arm64-artifacts-20261009-01/wheels/wheel-lock.json),
  [requirements.lock](../../../scratch/arm64-artifacts-20261009-01/wheels/requirements.lock)
  and [dependencies.lock](../../../scratch/arm64-artifacts-20261009-01/dependencies.lock).
  The two text locks are byte-identical, 61 exact hash-pinned rows. The unchanged
  `deploy/wheels.py` called `seal_wheels` and `verify_wheels`; `dependencies.lock`
  contains the exact returned text used by Builder. Builder/install was not run.
- [Target receipt](../../../scratch/arm64-artifacts-20261009-01/target.json),
  [acquisition/provenance mapping](../../../scratch/arm64-artifacts-20261009-01/acquisition.json),
  [wheel verification](../../../scratch/arm64-artifacts-20261009-01/wheel-verification.json),
  [closure evidence](../../../scratch/arm64-artifacts-20261009-01/dependency-closure.json),
  [attestation review](../../../scratch/arm64-artifacts-20261009-01/attestation-review.json),
  [ELF static review](../../../scratch/arm64-artifacts-20261009-01/elf-static-review.json)
  and [preservation/final checks](../../../scratch/arm64-artifacts-20261009-01/preservation.json).

**61 wheels / 62,428,082 bytes: four reused, 57 downloaded.** Reused artifacts:
ARM64 Deno 2.9.7 from the existing Phase 10 media artifacts; universal
bgutil-ytdlp-pot-provider 1.3.1, yt-dlp 2026.8.19 and yt-dlp-ejs 0.8.0 from the
existing prerequisite wheel directory. Named repository wheel locations and the
standard Pip wheel cache were also checked. Private scratch/HTTP caches and other
projects were not searched; no global cache-absence claim is made.

Official version-specific PyPI JSON and `files.pythonhosted.org` provided metadata
and missing bytes; redirects were restricted to these HTTPS hosts. Every exact
version/filename, non-yanked selection, publisher SHA256/size, Requires-Python,
filename/WHEEL tags, METADATA identity, unique safe ZIP paths and complete RECORD
coverage/hash/size passed. **3,884 hashed members** plus 61 intentionally unhashed
RECORD members were checked without extracting or importing package code. No
symlinks, traversal, private-data filenames or startup `.pth`/customize hooks were
admitted. Wheelhouse contains exactly the 61 expected wheels and two canonical
lock files; no sdist, extra package, build output or Windows wheel is present.

Tags were evaluated for explicit CPython 3.12/cp312, compatible abi3/universal
Python tags, and aarch64 manylinux floors no newer than glibc 2.39 (including the
manylinux2014 alias). All **23 native ELF members** are 64-bit little-endian
AArch64; embedded GLIBC version strings do not exceed 2.39. This is static
compatibility evidence, not loader/import, CPU-feature, libc++ or media execution.

PyPI attestations: **38 exact-subject supplementary PASS, 22 not published (404)**.
gTTS's supplied statement uses `gtts-...` while its PyPI filename is `gTTS-...`;
the original strict mismatch is retained. The separate
[case review](../../../scratch/arm64-artifacts-20261009-01/gtts-attestation-case-review.json)
verifies identical parsed wheel identity and digest, the `pndurette/gTTS`
publisher/certificate identity and leaf-key DSSE signature. All 39 available
attestations have supplementary signature evidence. Independent Fulcio chain/
Rekor checkpoint/inclusion verification was not performed; no verifier was
installed. Acquisition trust is official HTTPS PyPI and recomputed published SHA256.

All 61 installed pins' base dependency constraints close for the target markers.
Recursive extras propagation from both requirements files includes Discord voice,
httpx socks and yt-dlp default. Only the three unpinned default extras above fail.
Existing Windows installation of those packages does not amend ARM64 pin policy.
Their ARM64 artifacts were not acquired and no versions were silently chosen.

## Boundaries, preservation and next gate

This task ran **metadata/static verification only; no pytest or target execution**.
Prior evidence retains its exact scope: installed admission 588 PASS/source 127 PASS;
Windows music 2 PASS; canonical 1,896 collected / 1,869 PASS / 0 FAIL / 0 ERROR /
27 Linux user-systemd SKIP / 0 NOT_RUN in 325.422 seconds. No redundant suite run
was needed for an artifact/documentation-only task.

The entry snapshot's first attempt used the older source-freeze list encoding and
failed before saving; the corrected encoding exactly matches the current canonical
map identity. Initial helper and network-denied receipts remain retained. No source
or test correction was made. Final checks verify inherited file bytes (apart from
the three additive routing notices), all 377 source files, 7,748 installed package
files, 48 prior artifact/receipt files and unchanged Git HEAD/branch/refs/index.
The original bytes of each routing document are recoverable by removing only this
task's exact additive notice. No inherited dirty work was reverted or removed.

No installs, downloaded code execution, source build, credentials, Pi writes,
service operation, upload, commit/push, cleanup or production cutover occurred.
MyFood/MyMoney remain paused; My Moving is untouched. Recorded production remains
source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`; it was not re-audited here. A9/A10 original
operational gates, all 23 obligations and deferred P11 remain unchanged.

**Exactly one next release-readiness gate:** review and explicitly approve a
canonical dependency-pin revision covering the three required yt-dlp default
extras, then acquire/verify those exact ARM64 artifacts and reseal a complete
extras-closed wheelhouse. Preserve this 61-pin snapshot as evidence. This is a
dependency-policy gate, not installation, target acceptance or deployment approval.
