# Independent import-probe tooling review - 2026-10-09

## Approved single full-source execution addendum - 2026-10-09

**Full-source acceptance: FAIL / PARTIAL. Fresh result: 13 PASS, 1 FAIL, 0 ERROR,
0 SKIP, 1871 NOT_RUN out of 1885 collected.** The exact import-probe tooling retains
its bounded PASS; the previously blocked import test passed in this full-source run.
The first failure is the already-known stale documentation inventory assertion at
`tests/architecture/test_rebuild_documentation.py:92`, requiring final-audit to contain
only `a0-phase-0-report.md`. This is a reproduced repository test failure, not a new
runtime defect or import-adapter failure. It remains a real acceptance blocker.

The owner explicitly approved one guarded whole-source run outside the default
sandbox, maximum 300 seconds, excluding Pi, real data, credentials and external
network. The parent relayed the exact question and owner's approval. This reviewer
used `exec_command` with `sandbox_permissions=require_escalated` for precisely:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-full
```

Working directory was the unchanged repository root:
`C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot`.
Formal execution was allowed; there was no new rejection, workaround or retry.
This consumes that single authorization, not a standing permission for another run.

Before execution, `approved-full-entry.json` reverified every reviewed tooling hash
in the table below, author patch hash, interpreter, inherited safe repository/evidence
bytes, excluded-file metadata and branch/HEAD/refs/index. All six intended output names
were absent. No prior receipt was overwritten. Source identity remained
`f94377a197bf83d04d9fd091f24988af2c516fd70044405e0c49fd27c3328bb4`.

| Actual measurement | Result |
| --- | --- |
| Collection | 1885; exact same node-ID set as retained full-source collection |
| Completed cases | 13 PASS / 1 known inventory FAIL / 0 ERROR / 0 SKIP |
| Not executed because of unchanged `--maxfail=1` | 1871 NOT_RUN |
| Duration | 3.94s console / 3.805s JUnit / 5.188s outer |
| Test-child status | exit 1; no timeout; 300-second bound unchanged |
| Original architecture import probe | PASS with exact original assertions, `-I -B`, 15-second timeout and 12 actual child rejection checks |
| Warnings | One existing audioop deprecation warning; no runtime/unraisable warning reported |

The wrapper itself exited zero after printing child exit 1; this report uses the
test-child process receipt, JUnit and pytest result together. It does not mislabel
that wrapper exit as success. Fresh basetemp was
`C:\Users\dlrjs\AppData\Local\Temp\discord-source-source-full-k22rtll3\pytest`;
import child owned root was `C:\Users\dlrjs\AppData\Local\Temp\discord-import-probe-6e2y6ojl`
and remained empty after completion. All 377 source-manifest file hashes were unchanged.
No default-sandbox stall diagnosis is inferred from a run that stopped this early.

Evidence: the six new `scratch/import-probe-20261009-01/source-full*` files (excluding
historical `source-full-collect*`) contain command/source/result/process JSON, console
transcript and JUnit. `scratch/import-probe-independent-20261009-01/approved-full-result.json`
independently maps all executed and NOT_RUN node IDs, counts, exact receipt hashes and
preservation checks. `approved-full-entry.json` and `approved-full-preservation.json`
bind the before/after identities and prior evidence.

Historical Deno failure, dependency mismatches, Linux/systemd opt-in skips and the
unsupported subprocess families described below were **NOT REACHED / NOT_RUN** here.
They are not new failures, newly observed skips or passing coverage. The former
7 PASS / 1 import-harness FAIL / 1877 NOT_RUN, earlier timeouts/rejection, author
attempts and independent 30/12 guard evidence are preserved. Prior approved admission
588/127 PASS and 715 partition retain their distinct scope. No other harness failure
was observed in the 14 reached cases; no claim is made about the remaining 1871.

Only this additive report section and three additive current-routing notices were
written after execution. Runtime, tooling, tests, prior evidence, sensitive metadata,
HEAD/refs/index and inherited dirty changes are preserved; whitespace checks passed.
No guard change, package operation, Pi/real DB/credential/external-network access,
permission-setting change, commit/push, deployment, refreeze or cleanup occurred.
Python hooks remain reviewed-code safeguards, not OS or process-tree isolation.
MyFood/MyMoney remain untouched. A9/A10 BLOCKED, Integrated administrative SCOPE-CLOSED,
all 23 operational obligations and deferred Phase 11 remain unchanged.

**Exactly one next step: a separate narrow review/remediation of the stale final-audit
document-inventory test against the current documented inventory contract, preserving
all audit evidence and without skips or weakened coverage.** No fix or second run is
authorized or performed in this execution review. STOP.

---

The following pre-approval review and its pending-execution routing are preserved history.

**Verdict: bounded tooling PASS. Full-source behavioral acceptance remains PENDING /
NOT RUN in this review.** No material defect was found in the exact import adapter.
The prepared full-source command is a bounded first-failure diagnostic, not a promise
that the whole suite is supported or green. No implementation fix or policy widening
was made. Stop after this review.

Authority read: AGENTS.md; current final-audit active-state, ledger and document index;
[C13 deployment contract](../phases/phase-08/deployment-contract.md), including the
full repository development/commit gate; [independent admission evidence](admission-independent-verification-20261009.md);
and [authoring report](import-probe-remediation-20261009.md). `.agents/skills` and
`.codex/skills` are absent. Root AGENTS governs; no checkout skill was substituted.

## Exact identity and independent findings

Branch `codex/rebuild-v2`; HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`.
Index is empty of staged changes; raw index SHA-256 remains
`567e4ee312ef2b1baf37cf249a4e6437cd3679044a0eaff6b8aa5af216374268`.
No fetch; remote freshness is unverified. HEAD alone does not identify dirty source.
The reviewer recomputed all 744 safe repository hashes in the author entry/final
manifests, prior evidence hashes and 40 excluded-file metadata records without
opening excluded content. All matched. The task patch was independently reconstructed
from before/current bytes, not merely compared with a claimed hash.

| Reviewed input | Recomputed SHA-256 |
| --- | --- |
| Author `task-only.patch` | `2bd485f66f1ac6db8031bafea01ae19b26f501177a2b8722e32c4e1ba1709a28` |
| `import_probe_guard.py` | `381b73ac5a365c0eca6df8b886f61c329fdac770fbd0f3c6798397dc7fa6596a` |
| Canonical `a8r4-test-runner.py` | `df0484affd417bd7291f52116aa6c1c4ef122ffaf6e32d1de155636434f850f0` |
| `test_import_probe_guard.py` | `68c12ddd76878ca88154725ada07fb4cf4e552c59d888a097eea6bf7623faa28` |
| Task `source_checks.py` | `1daf43c6842d0e658a8c6cc78a01d8672f613818f055df81dbcae50b159f51a6` |
| Task `run_bounded.py` | `97f3185a3c117232fd068e511eb8216ecbd09b082f40e04f8c1e92369fbd56b2` |
| Original `tests/architecture/test_import_rules.py` | `8040d050100e41539eb9bebed4c4bdeee875a15103e66a9da02dd0bd7ec9d363` |
| Existing `.venv/Scripts/python.exe` | `5912d0884b23c0343983a864c6064242391e2265536f50b88624857e353882c9` |

The unchanged 377-file source receipt has aggregate SHA-256
`f94377a197bf83d04d9fd091f24988af2c516fd70044405e0c49fd27c3328bb4`.
All original `src/tests/deploy/scripts` manifest bytes match. No runtime, installed
selection, payload-root or release identity change was introduced. The canonical
runner changes by seven lines below `import pytest`; its reusable guard prefix is
byte-equivalent after newline decoding. Installed loaders retain the old prefix.

- The complete original test file is hash-pinned. Independently evaluated original
  f-string equals the adapter's script. SQLite/socket/process/task/thread/getenv,
  logging-handler and module-count assertions are unchanged; return-code assertion,
  capture behavior and `timeout=15` remain. The adapter executes that script intact.
- Only exact interpreter, original argv/code and original cwd/text/capture shape
  trigger adaptation. A synchronous ContextVar token admits the generated executable,
  full command, cwd and minimal environment together; reset occurs in `finally`.
  Different commands fall through to the source runner's existing deny policy.
  No broad Python allowance was added. The canonical runner's older general process
  policy is not represented as equivalent to the stricter source wrapper.
- Actual child gets `-I -B`, `sys.dont_write_bytecode=True`, fresh owned home/temp and
  only SYSTEMROOT/WINDIR plus synthetic path/ dotenv-opt-out settings. No inherited
  PATH, application credentials, Git or Python configuration is forwarded. Parent
  conftest disables dotenv and clears application settings; source wrapper removes
  Git/Python overrides, disables automatic pytest plugins and preserves Git config
  isolation. Interpreter/site/dependency code remains a trusted prerequisite.
- Child audits lexical and resolved paths, blocks operational data and credential
  names, confines writes to its owned temp root and other reads to code extensions
  under reviewed source/interpreter roots. All socket events, descendants and
  environment mutation are denied. Child self-checks emit events without opening
  forbidden paths or attempting network access. The actual child directory stayed empty.
- Native `Popen` communicate/wait/kill/context behavior remains inherited. Inspection
  of this interpreter's `subprocess.run` confirms timeout kill followed by reap/drain;
  the successful run exited normally. No live timeout/forced-parent-death experiment
  was added. The outer unchanged wrapper kills/reaps its immediate test child at its
  configured 300-second timeout. It is not an OS process-tree supervisor: forced parent
  death is not proof of import-grandchild cleanup. The existing packet worker separately
  retains its parent-pipe exit and bounded kill/wait lifecycle.

These are safeguards for reviewed code, not hostile/native-code isolation. Parent
guards do not globally restrict all filesystem writes or cover every transport API;
full-source safety also depends on inspected synthetic fixtures and fakes. They do
not replace the default OS sandbox or independently justify removing it.

## Fresh evidence versus retained history

All fresh executions used the default sandbox. From the checkout root:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/import-probe-independent-20261009-01/review.py entry
.\.venv\Scripts\python.exe -I -B scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-import-independent
.\.venv\Scripts\python.exe -I -B scratch/import-probe-independent-20261009-01/static_checks.py
```

| Fresh independent check | Actual result |
| --- | --- |
| Original architecture cases plus adapter rejection tests | **30 PASS / 0 FAIL / 0 ERROR / 0 SKIP**; 5.25s console, 4.021s JUnit, 10.188s outer; exit 0, no timeout |
| Actual import child audit checks | **12 negative checks PASS**, within that successful import; not additional pytest cases |
| Reviewer exact-event matcher checks | **12 PASS**, including 10 rejections: executable/code/flags/cwd/environment changes, fresh context and reset token; no child spawned by these checks |
| Patch/assertion/manifest preservation | PASS; exact patch reconstruction and original file/script identity |
| Historical collection receipts matched against current manifests | 127 mandatory-source / 1885 full-source IDs unchanged; **no fresh collection or behavioral credit** |

Fresh receipts are `scratch/import-probe-20261009-01/source-import-independent*`;
reviewer inventory and static proof are in
[`scratch/import-probe-independent-20261009-01/`](../../../scratch/import-probe-independent-20261009-01/).
Read process JSON, transcript, JUnit and result JSON together: the outer wrapper
prints child status but can itself exit zero after a failed or timed-out test child.

Historical evidence retained without new credit: author focused 30 PASS; canonical
12 PASS overlapping those cases; previous independently approved installed 588 and
mandatory-source 127 PASS with 715 partition. Prior 7 PASS / 1 import-harness FAIL /
1877 NOT_RUN, initial adapter failure, socketpair timeouts, and the old automatic
approval rejection remain intact. No full behavioral attempt or new escalation here.

Known stale inventory failure remains at `tests/architecture/test_rebuild_documentation.py:92`.
Historical Deno failure and four recorded dependency mismatches remain unverified
here (bgutil provider, deno and yt-dlp-ejs missing metadata; yt-dlp version mismatch).
Linux/systemd opt-in skips, earlier A3 limits, ARM64/wheel/ABI and target-host proof
remain unresolved. Source inspection also identifies other unsupported subprocess
families (for example SQLite lock children, TTS/staging entrypoint children and Node
browser harnesses). This exact allowance does not cover them. `--maxfail=1` preserves
the first failure and leaves subsequent cases NOT_RUN; no skip, waiver or further
runner redesign was introduced.

An initial broad instruction-file directory listing encountered access-denied legacy
scratch directories. It read no files there and was not retried or escalated. Reviewer
receipt scripts first hit two local assertions (test-code directory named `data`, then
Windows patch newline serialization); the reviewer corrected only those new receipt
scripts. Neither was a product/test failure or an access-denial workaround.

## Exact pending execution boundary and stop

After fresh explicit owner authorization, the proposed **single** command is:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/import-probe-20261009-01/run_bounded.py source_checks.py source-full
```

Working directory:
`C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot`.
Request scope: one local run of these exact reviewed bytes outside the default
sandbox, if the owner accepts that execution boundary; no permission-setting change.
Configured maximum test-child duration **300 seconds**, unchanged import-child
timeout **15 seconds**; process termination/receipt overhead is outside that timeout,
and no hard whole-tree limit is claimed. No retry or budget extension is included.

The wrapper runs `tests/`, strict xfail/runtime/unraisable policy, disabled cache and
plugin autoload, `--maxfail=1`, with fresh synthetic basetemp under
`C:\Users\dlrjs\AppData\Local\Temp\discord-source-source-full-*\pytest`.
Legacy DB/SQL fixtures point there; import home/temp uses a fresh
`discord-import-probe-*` sibling; frozen packet inputs use owned OS-temp files.
Only allowlisted read-only Git provenance and exact guarded import/packet children
are admitted. Parent permits stdlib Windows socketpair only for loop wakeup; no
application/external network is authorized. Outputs are new `source-full*` receipts
in the author scratch directory; their exact names were absent at review time.
Do not read real DB/backups, credentials, contact Pi/providers, install packages,
refreeze, deploy, change permissions, commit/push or broaden unsupported children.

The known default-sandbox socketpair stall was deliberately not reproduced. The
previous approval applied only to two completed admission runs and cannot authorize
this command. No fresh escalation request was submitted by this review.

Preservation is recorded by `review.py preservation` in `preservation.json`: only this
report and additive notices in the three routing documents change repository content;
all inherited code, evidence, sensitive metadata, HEAD/refs/index remain unchanged.
Git cached and working diff whitespace checks passed. No fix, cleanup or rollback was
performed. Rollback scope is only these review additions, retaining historical proof.
MyFood/MyMoney remain untouched. Original A9/A10 BLOCKED, Integrated administrative
SCOPE-CLOSED, all 23 operational obligations and deferred Phase 11 remain unchanged.

**Exactly one next step: parent obtains fresh explicit owner authorization for the
single guarded 300-second command above.** Full-source acceptance remains pending;
this review stops without executing that request or starting another microphase.
