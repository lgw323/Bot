# Post-install canonical verification - 2026-10-09

**Windows source-suite PASS within its platform scope: 1,896 collected, 1,869 PASS,
0 FAIL, 0 ERROR, 27 SKIP, 0 NOT_RUN; no XFAIL/XPASS.** The two prerequisite music
tests also passed. Both approved runs completed once, without a timeout or retry.
This closes the local missing-Deno failure; it does not close Linux/ARM64,
user-systemd, installed-release or operational acceptance.

## Authority and exact execution

The owner approved the bundled request at 2026-10-09 16:03 KST: one music/runtime
run outside the default sandbox, maximum 60 seconds, followed only on success by
one canonical full run outside the default sandbox, maximum 600 seconds. Formal
escalations for those exact phases succeeded. No wider authority was inferred.
AGENTS.md, the current audit authority/ledger/index, prior canonical receipts and
the unchanged runner/test inputs were checked. No additional skill was required.

Executed commands, with newly owned output paths:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/post-install-20261009-01/supervise.py focused
.\.venv\Scripts\python.exe -I -B scratch/post-install-20261009-01/supervise.py full
```

Both supervisors called the unchanged `a8r4-test-runner.py`, not the diagnostic
`source_checks` wrapper. Both used `--maxfail=0`, no `-x`, strict xfail,
RuntimeWarning/PytestUnraisableExceptionWarning errors, no pytest cache, disabled
plugin autoload, explicit asyncio plugin, a clean allowlisted environment and
fresh home/basetemp/XML paths. The existing credential, operational-data and
external-network guards and reviewed synthetic fixtures remained in force.
Python parent hooks are not general child-process OS isolation; the reviewed
children and fixtures retain their existing bounded scope. No provider request,
Pi access, operational-data access, installation, source/test/runner edit,
deployment, commit, push or deletion was performed in this session.

| Run | Collected | PASS | FAIL | ERROR | SKIP | NOT_RUN | Outer seconds / limit | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Focused | 2 | 2 | 0 | 0 | 0 | 0 | 1.438 / 60 | 0 |
| Canonical full | 1896 | 1869 | 0 | 0 | 27 | 0 | 325.422 / 600 | 0 |

The focused nodes were `test_provider_uses_release_local_deno_and_disallows_remote_components`
and `test_pinned_provider_and_runtime_load_without_network`, both in
`tests/integration/music/test_resources.py`. The latter retained its 10-second
bound for each subprocess and verified actual yt-dlp/Deno version execution plus
the EJS version. The conditional full-run supervisor independently required exit
0 and exactly two passing JUnit cases before admitting the full run.

The full console duration was 324.42s and JUnit duration 324.388s. All 1,896 case
identities match the preceding canonical run. All 27 skip identities and reasons
also match: `explicit isolated Linux user-systemd environment required`.
One existing `audioop` DeprecationWarning remains; neither configured warning-error
category occurred. Both owned pytest children exited normally; no forced cleanup
was necessary.

## Environment, identity and evidence

Python 3.12.14 / Windows AMD64; pytest 9.1.1. The seven approved installed versions
were reverified before execution and again afterward: deno 2.9.7, yt-dlp
2026.8.19, yt-dlp-ejs 0.8.0, bgutil-ytdlp-pot-provider 1.3.1, brotli 1.2.0,
mutagen 1.48.1 and pycryptodomex 3.23.0. All 65 installed distribution versions,
7,748 recorded installed-file hashes and seven staged wheel hashes matched the
completed installation inventory; this session installed nothing.

- Branch `codex/rebuild-v2`, HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`.
- Reviewed 377-file source identity:
  `2cf256d2c514fcab18083d01fc177c76831b2d0791e127a95892a5fa6788ae6c`.
- Canonical runner SHA256:
  `df0484affd417bd7291f52116aa6c1c4ef122ffaf6e32d1de155636434f850f0`.
- Music resource-test SHA256:
  `2615d8d31eb08067d603848fef7fb97ff410f6a3a973a3744a06eabd8859c526`.
- [Preflight inventory](../../../scratch/post-install-20261009-01/preflight.json),
  [focused command](../../../scratch/post-install-20261009-01/focused-command.json),
  [full command](../../../scratch/post-install-20261009-01/full-command.json).
- [Focused JUnit](../../../scratch/post-install-20261009-01/focused.xml),
  [full JUnit](../../../scratch/post-install-20261009-01/full.xml),
  [full console](../../../scratch/post-install-20261009-01/full-console.txt),
  [complete counts, skips and preservation reconciliation](../../../scratch/post-install-20261009-01/reconciliation.json).
- [Seven wheel identities](../../../scratch/music-prerequisites-20261009-01/staged-seven.json)
  and [installed file inventory](../../../scratch/music-prerequisites-20261009-01/installed-inventory.json)
  remain retained; provenance limitations remain in the earlier installation report.

At completion, all 979 inherited files, 74 prior receipts, 29 candidate-artifact
files, 2,108 rollback files, reviewed source/guard hashes and Git HEAD/branch/refs/
index/status matched the entry snapshot. The subsequent documentation-only update
adds this report and a compact notice to each of the three audit authorities;
every prior notice/content remains byte-preserved. No archive or candidate
manifest was refreshed. Static inventory/link checks cover those added notices.

## Supersession and remaining release boundary

The retained [pre-install canonical receipt](../../../scratch/canonical-full-20261009-01/canonical-summary.json)
reported 1,868 PASS / 1 missing-Deno FAIL / 27 SKIP. The newer result supersedes
that environment failure and older partial full-source routing only. The earlier
default-sandbox focused timeout remains historical evidence, not a hidden pass.
Prior independent 588 installed / 127 source admission PASS keeps its own scope;
this run does not certify a newly built Linux installed release. A2-N1 closure,
Integrated ACCEPTED / SCOPE-CLOSED, original A9/A10 BLOCKED, all 23 transferred
operational obligations and deferred Phase 11 remain unchanged.

**Next actual release-readiness blocker: target dependency artifacts.** Prepare
and review the complete CPython 3.12 / Ubuntu 24.04 Linux ARM64 wheelhouse against
the current 61-entry `deploy/dependencies.pins`, then materialize and verify its
wheel lock with the existing sealing path. The installed Windows wheels are not
that artifact. No target acquisition, installation or sealing was executed here.
A truthful current source/release identity, target installed/configuration proof
and the applicable operational gates remain required afterward. No generic
repeat of this successful Windows bundle is proposed. Session STOP.
