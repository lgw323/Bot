# Bounded import-probe tooling remediation - 2026-10-09

**Authoring result: focused PASS; whole-source acceptance PARTIAL / NOT RUN;
independent review PENDING.** This is one local tooling correction, not independent
closure, admission refreeze, deployment or operational acceptance.

Branch `codex/rebuild-v2`, HEAD `cb54da9948370db64133a0ead6c9df89d0b61055` matched
the assignment. No fetch occurred; remote freshness is unverified. The inherited
dirty checkout, not HEAD alone, is the source identity. `.agents/skills` is absent.
Reviewed AGENTS, current active-state/ledger/index, C13 deployment contract,
[latest independent admission verification](admission-independent-verification-20261009.md),
the original architecture assertions and the pre-existing A8R4 whole-suite runner.

## Cause and deliberately narrow correction

The historical 7 PASS / 1 harness FAIL / 1877 NOT_RUN was a parent admission failure:
`source_checks.py` rejected `[sys.executable, '-I', '-c', script]` before process
creation. It was not an application import failure. A raw argv allowance would
lose the parent audit hooks and let `-I` ignore `PYTHONDONTWRITEBYTECODE`.

The canonical [A8R4 runner](a8r4-test-runner.py) already runs the full-source tests,
but its parent audit hook does not transfer into that isolated child. It now installs
[one exact import adapter](import_probe_guard.py) below `import pytest`. Its existing
reusable guard prefix is unchanged, so the installed-admission loaders acquire no
new source-test dependency or subprocess behavior.

The adapter pins the complete original test file SHA-256, extracts only its reviewed
literal f-string, matches the exact interpreter/argv/cwd/capture shape, and executes
the **unchanged complete script** after a child guard with explicit `-I -B` and
`sys.dont_write_bytecode = True`. All original SQLite/socket/process/task/thread/
environment/logging/module-count assertions and the original 15-second timeout stay
unchanged. Changed test bytes require review, rather than a permissive fallback.

Each child receives a new empty owned OS-temp HOME/USERPROFILE/TEMP/TMP and only
Windows system-directory variables plus the dotenv opt-out. No PATH, Git/Python
overrides or inherited application credentials are forwarded. Code reads are
limited to source and existing interpreter/dependency roots; operational data,
credential names and non-code reads are denied. Writes are limited to the owned
temporary root, with lexical and resolved-path checks; source bytecode writes are
denied. All socket audit events and descendant process/environment escapes are
denied. Twelve rejection self-checks execute inside the actual child before the
original script; they emit audit events only, never touch real protected files or
make connections. The owned child directory remained empty after the focused run.

The task-owned copy of the existing source runner adds only the exact synchronous
launch-token admission, helper identities/receipt, focused selection and collection
modes. Its original Git and frozen packet-worker allowances and denials remain.
There is no broad Python/subprocess allowance or new general-purpose suite framework.
Old runner copies and receipts are unchanged. The canonical runner's unrelated
pre-existing subprocess policy is not redefined by this change.

These are safeguards for reviewed Python code, not hostile native-code isolation
or OS security enforcement. Parent negative write coverage rejects unreviewed
write code before launching it; it does not claim a new global parent filesystem
sandbox. Child negative write coverage exercises the real child audit hook.

## RED, GREEN and compatibility evidence

All executions used the default sandbox. No new escalation was requested or used.
The prior two owner-approved outside-sandbox runs are completed historical evidence,
not standing authorization. This task did not rerun either full admission lane or
the earlier socketpair stall. Its exact OS cause remains unproven.

Evidence directory: [`scratch/import-probe-20261009-01/`](../../../scratch/import-probe-20261009-01/).

| Check | Result |
| --- | --- |
| Original source-runner prefix with unchanged import test | RED reproduced: exact PermissionError before launch; `red-reproduction.json`, 15-second cap |
| First adapter attempt | 7 PASS / 1 harness FAIL; Windows audit executable was implicit `None`; retained `source-import.*` |
| Explicit executable correction | 12 architecture PASS; `source-import-green.*` |
| Final import + parent guard tests | **30 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, 5.23s console, 4.011s JUnit, 10.032s outer |
| Actual import child | 12 negative audit self-checks plus minimal-environment and bytecode checks; original import assertions PASS |
| Canonical runner, same 12 architecture cases | **12 PASS**, 4.07s console, 3.838s JUnit; overlapping, not added to 30 |
| Mandatory source lane collection | **127 collected**, exact node-ID set matches independently approved source receipt; no fresh behavioral credit |
| Full-source collection | **1885 collected**, exact node-ID set matches prior full-source receipt; no fresh behavioral credit |
| Preservation/static checks | Parent guard prefix, original test bytes, all `src/tests/deploy` bytes, admission selection and payload unchanged |

The 18 additional source-wrapper tests cover five rejected unreviewed child code
categories (protected data, credentials, external transport, outside-owned writes,
descendant commands), six rejected launch-shape changes, five direct parent audit
rejections, token lifetime, and original-byte/child-receipt verification. The 12
child events cover operational paths, credentials, outside-owned/source writes,
DNS/connect/sendto, subprocess/system and environment mutation. No failure is
converted into a skip and no assertion or warning policy is weakened.

Every suite/collection call used the copied unchanged `run_bounded.py`, with a
300-second parent deadline; every import retains its 15-second child deadline.
The wrapper's exit code alone is not the test verdict: process JSON child exit and
timeout, transcript, XML and result receipts must be read together. It remains a
bounded subprocess runner, not an OS process-tree sandbox.

Executed from checkout with `.venv/Scripts/python.exe -I -B`:

```text
scratch/import-probe-20261009-01/prepare.py
scratch/import-probe-20261009-01/red.py
scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-import
scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-import-green
scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-import-final
scratch/import-probe-20261009-01/run_bounded.py checks.py canonical-import
scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-measurement-collect
scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-full-collect
scratch/import-probe-20261009-01/evidence.py static
scratch/import-probe-20261009-01/record_red.py
scratch/import-probe-20261009-01/evidence.py preservation
```

## Exact review surface and preservation

| File | SHA-256 |
| --- | --- |
| `docs/rebuild/final-audit/a8r4-test-runner.py` | `df0484affd417bd7291f52116aa6c1c4ef122ffaf6e32d1de155636434f850f0` |
| `docs/rebuild/final-audit/import_probe_guard.py` | `381b73ac5a365c0eca6df8b886f61c329fdac770fbd0f3c6798397dc7fa6596a` |
| `docs/rebuild/final-audit/test_import_probe_guard.py` | `68c12ddd76878ca88154725ada07fb4cf4e552c59d888a097eea6bf7623faa28` |
| `scratch/import-probe-20261009-01/source_checks.py` | `1daf43c6842d0e658a8c6cc78a01d8672f613818f055df81dbcae50b159f51a6` |
| Unchanged original `tests/architecture/test_import_rules.py` | `8040d050100e41539eb9bebed4c4bdeee875a15103e66a9da02dd0bd7ec9d363` |

`static.json` binds interpreter/helper hashes, source manifests and collection sets.
`source-import-final-result.json` records the exact original script hash, guarded
child code hash, interpreter/cwd, synthetic owned root and environment key names.
`reviewed-*` copies preserve final reviewed tooling. `task-only.patch` includes only
this task's canonical/helper/test/report/routing changes and the task-owned diagnostic
runner delta; `preservation.json` binds its hash and all seven repository after-hashes.
The only existing repository edits are seven added canonical-runner lines and additive
notices in the three routing documents. No CHANGELOG/product/runtime edit is needed
for this evidence-tool correction. Prior reports, archives, failed receipts, refs,
index, inherited dirty files and excluded-file metadata are preserved.

No Pi, production DB/backup, credential values, external network, package install,
security-setting change, deployment, refreeze, commit/push or cleanup occurred.
MyFood/MyMoney remain paused. Rollback is limited to this saved task diff and new
tooling/report files; retain evidence and inherited changes. No rollback was performed.

## Stop and next independent boundary

**Stop here; one next task is independent review of this exact correction and its
focused/negative evidence.** The 715 obligation partition and prior independent
588 installed / 127 mandatory source PASS remain unchanged. This author does not
close its own correction. Full-source behavior, known inventory/Deno failures,
Linux/systemd skips, ARM64/target proof and all 23 operational obligations remain
unresolved by these focused results. Original A9/A10 BLOCKED, Integrated administrative
SCOPE-CLOSED and deferred cleanup remain unchanged.

After independent review, the exact existing bounded full-source diagnostic command
from this checkout is:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-full
```

It retains 300 seconds, `--maxfail=1`, the original 15-second import timeout and guard
policies. It is **NOT RUN here** and may stop on the known inventory failure or an
environmental socketpair stall; neither would be a clean suite result. Execution
outside the default sandbox needs a new exact owner approval for that command and
bound. Its risk is executing the whole reviewed source test set with only Python
guards and no OS process-tree isolation. Do not reuse the two completed admissions'
permission, retry a denied operation, change the boundary silently, or proceed to
deployment/cleanup. A broader runner-policy redesign requires a separate decision.
