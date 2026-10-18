# Independent admission selection/boundary verification - 2026-10-09

## Approved execution addendum - 2026-10-09

**Latest verdict: independent bounded PASS for the admission selection and boundary
correction only.** This supersedes the behavioral-completion BLOCKED disposition
below after a new explicit owner decision and two successful formal escalation
requests. The earlier review, timeout evidence and rejection remain intact history;
they were not retroactively approved or removed. Whole-source, ARM64, deployment and
operational acceptance are not granted.

At 14:13 KST on 2026-10-09 the owner explicitly approved exactly two local sets:
installed 588 and mandatory source 127, outside the default sandbox, each capped at
300 seconds, retaining the reviewed data/credential/external-network guards. That
decision superseded the prior restriction only for these formal requests. Neither
request was rejected anew. There was no alternate execution route, security-setting
change, guard relaxation or runner implementation change. The runs were sequential.

Before execution, `approved_verify.py entry` recomputed and matched the prior final
repository hashes, original sensitive-file metadata, all earlier implementation
evidence, exact archive/extraction, source manifest, five copied helper hashes and
HEAD/branch/refs/index. New receipt names and installed temporary root were absent.
`approved-entry.json` binds that check and the previous independent receipts.

From the unchanged checkout root, using the existing interpreter, the only new
behavioral executions were these two formally approved commands:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/admission-independent-20261009-01/run_bounded.py checks.py installed-approved
.\.venv\Scripts\python.exe -I -B scratch/admission-independent-20261009-01/run_bounded.py source_checks.py source-measurement-approved
```

Each used `exec_command` with `sandbox_permissions=require_escalated`. The existing
wrapper launched its child with `-I -u -B` and timeout 300. Exact argv/cwd/basetemp,
XML, phase records and final inventories are the corresponding `*-command.json`,
`*-effective-command.json` where applicable, `*-process.json`, `*.xml`, `*.txt` and
`*-result.json`. The installed cwd remained the newly created independent extraction
`C:\Users\dlrjs\AppData\Local\Temp\discord-admission-final-zeh70nyf\app`;
its new owned root was sibling `installed-approved-owned`. Source used checkout cwd
and a fresh `discord-source-source-measurement-approved-*` OS-temp root; its precise
generated path is retained in its command receipt. No existing output was overwritten.

| Fresh approved run | Result | Console / JUnit / outer seconds |
| --- | --- | --- |
| Complete extracted installed admission | **588 PASS, 0 FAIL, 0 ERROR, 0 SKIP, 0 NOT_RUN** | 231.97 / 231.580 / 232.515 |
| Mandatory source regressions | **127 PASS, 0 FAIL, 0 ERROR, 0 SKIP, 0 NOT_RUN** | 56.58 / 56.483 / 57.391 |

Both child exits were zero with no timeout. `approved-results.json` independently
matches the executed node-ID sets to the earlier collection/AST partition: exactly
**715 = 588 + 127**, with no missing or overlapping cases. The source lane retains
42 local-harness, 84 candidate-packet and 1 fixed-history case. All 588 installed
setup/call/teardown records passed without xfail. The four shared-selection/active
caller command regressions, the other 64 BT1 cases and mandatory subprocess cases
were now reached and passed; they are part of 588, not additional counts.

Installed execution recorded 1078 disposable local Git children and one exact guarded
isolated staging child. Twelve parent rejection probes and four child rejection probes
passed again; these are boundary checks, not extra pytest cases. All 128 recorded
application modules came from the extraction; no scripts module or original-source
fallback was observed. The complete archive inventory and every extracted byte were
unchanged after execution. Source-manifest bytes were also unchanged. The archive,
source and runner identities are the exact hashes recorded in the earlier review
below, not a new release identity or candidate refreeze.

Successful completion under the newly approved execution boundary resolves this
review's missing behavioral receipts. It does not prove a particular OS cause for
the earlier socketpair stalls, or make Python audit hooks equivalent to an OS sandbox.
The prior default-sandbox attempts and reviewer denial retain their original meaning.

No whole-suite or documentation pytest run was added in this continuation. The
separate full-source import-probe denial remains unresolved: last evidence is
7 PASS / 1 harness FAIL / 1877 NOT_RUN. The known document-inventory failure also
remains. Source runner permissions were not broadened to admit that import child.
The detailed child audit/bytecode concerns and narrow remedy boundary below remain.

Final `approved-preservation.json` verifies exactly four additive documentation
updates: this report and the three current routing files. All their prior verdict
bytes, inherited code/tests, original evidence and independent failed/timeout/denied
receipts, excluded sensitive metadata, HEAD/refs/index and Git status are preserved.
No Pi, production/real-data/credential access, external communication, package install,
deployment, cleanup, commit/push or refreeze occurred. MyFood/MyMoney remain paused.
Original A9/A10 BLOCKED, Integrated administrative SCOPE-CLOSED and all 23 operational
obligations retain their existing meaning. Full source regression, reviewed ARM64
wheel/lock/ABI, truthful committed release identity, installed manifest/configuration
and Linux/target readiness remain required.

**One next step: separately scope and review the narrow full-source harness correction
for the mandatory import probe, retaining child safety, bytecode control, original
assertions and bounds.** It is not implemented or authorized by this bounded PASS.
Stop after this verification result; no deployment or operational gate is waived.

---

The following is the preserved pre-approval independent review and its BLOCKED verdict.


**Verdict: BLOCKED for independent behavioral completion.** The bounded selection
and assertion partition pass independent static/collection review. No lost assertion,
additional exclusion, product change or release-root expansion was found. Fresh full
installed and mandatory-source attempts could not finish in this execution environment;
historical green runs do not close that gap. No implementation fix was made.

Authority: current checkout, AGENTS sections 1/4/7, current active-state/ledger/index,
the [selection report](admission-selection-evidence-20261009.md),
[diagnosis](admission-boundary-diagnosis-20261009.md), and
[remediation](admission-boundary-remediation-20261009.md).
`.agents/skills` is absent in this checkout; no checkout skill or memory substituted
for repository evidence. This is one independent local review, not a refreeze,
deployment, whole-source acceptance or operational audit.

## Identity and exact change boundary

Branch `codex/rebuild-v2`, HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`;
no fetch, so remote freshness is unverified. HEAD is provenance, not dirty-byte identity.
Entry contains 111 porcelain file entries, 740 hashed non-sensitive repository files,
40 metadata-only excluded files, and 213 prior evidence files. Raw index SHA-256:
`567e4ee312ef2b1baf37cf249a4e6437cd3679044a0eaff6b8aa5af216374268`.
HEAD/branch/refs/index also match the remediation entry record.

The following identities were recomputed before relying on the evidence:

| Evidence | SHA-256 |
| --- | --- |
| Remediation report | `048eb84e6ccab8dbe3b3a1052ffaf6eee5aa3447ae74865f20f579d196cd7480` |
| Remediation `preservation.json` | `ce792f7f46fbaaef86e5185f67f8b7fe3f5aea1784eee90ac774e137f43a3168` |
| Remediation `task-only.patch` | `8f556bceef7e096957d29af4ad692eb49bb49bbc06476b8e4b432cd7358e16f4` |
| Earlier selection `task-only.patch` | `4ab2f93879231cc9feb2246f46b741857c6281534340431a1102f23602252b2a` |
| Selection report | `aef8e4f867cadb8e1bf00b357257d100fea08c096c1c67dcc5e2bbe1aed49da8` |

Reviewed both entry-relative patches, including the two active caller edits in the
earlier selection patch and all 11 remediation files: `admission.py`,
`test_admission_selection.py`, `test_a9_bt1_independent.py`, new
`source_review/test_a9_bt1_history.py`, README, CHANGELOG, C13 deployment contract,
the three current routing documents and the remediation report. All 11 after-hashes
matched current bytes before this review's routing insertions. Earlier patches,
reports, archives and failed/incomplete receipts are preserved.

New evidence lives in
[`scratch/admission-independent-20261009-01/`](../../../scratch/admission-independent-20261009-01/):
`entry.json`, `static.json`, `partition.json`, `negative-result.json`, exact command,
phase, process, source-manifest and collection receipts, transcripts, available XML,
`approval-rejection.json`, final preservation record and review-only patch.
The entry/copy helper is `review.py`; it does not modify application/tests.

## Contract, callers and complete assertion partition

[C13](../phases/phase-08/deployment-contract.md) **Dependencies and source** retains
bounded selected code/test/deploy exports and sensitive-data exclusion. **Transaction
and failures** requires both the installed subset and separate full source gate,
conftest cutoff, no bytecode/cache, existing warnings, timeouts and caller xfail policy.
**Layout and identity** still requires full commit/dependency manifest validation.

`LocalDeployment.test` (`deployment.py:125`) and production
`verify_candidate.py:64-82` both expand the same `installed_operations_args()`:
the operations directory, its exact conftest cutoff, and exactly two precollection
`--ignore` paths. No glob, skip marker or third module exclusion exists. Both keep
300 seconds and RuntimeWarning/unraisable errors. Production retains strict xfail;
LocalDeployment retains its prior policy. Selection semantics are identical; these
pre-existing xfail policies are intentionally not identical. Four selection regression
tests retain their command assertions and poison/future-name collection checks.
They were inspected but were not reached in this fresh stalled full installed run.

Fresh collection mapping, independently compared with the original node-ID set:
**714 original cases -> 715 units = 588 installed + 127 source**, empty missing and
overlap sets. The source lane is exactly local harness **42**, candidate packet **84**,
and fixed-history **1**. The first two modules' bytes match the earlier selection
entry. Collection proves membership, not behavioral PASS.

| Original mixed-case obligation | Sole current owner |
| --- | --- |
| Original lines 171-172: normalized historical configuration hash | `source_review/test_a9_bt1_history.py::test_prechange_rejection_and_routing` |
| Lines 187-188: original ConfigurationError and exact match expression | Same source case |
| Line 205: historical fetch argv uses original production destination | Same source case |
| Line 192: successful current configuration load; lines 207-209: exact isolated fetch argv | `operations/test_a9_bt1_independent.py::test_current_isolated_configuration_and_fetch_routing` |

Independent AST multisets preserve all four original Assert/With nodes: three source,
one installed; the successful current load operation also matches exactly. All other
function/class/fixture definitions in the BT1 module have identical AST. All other
**64** collected BT1 cases remain installed, including real synthetic encrypted
backup/restore/cancellation. All 22 parametrized local-Git fixture cases and the
isolated-interpreter case remain mandatory. No assertion weakening or skip was found.

Builder/SourceBuilder hashes match their selection-entry bytes. Both still export
`src`, `tests`, `deploy` and the three allowed root metadata files; no docs/scripts/
project Git/root conftest fallback was introduced. Existing sensitive-file rejection,
bounded extraction and release identity behavior were inspected unchanged. The
unchanged production archive validator accepts the new test archive with an empty
expected comment, solely as an inventory check; this is not committed-release proof.

`build_initial.py` remains fixed to `7d596ade8c721931437560ad9e6828762018972c` and
historical host/bootstrap paths. Its `activate_local.py`, `diagnose_initial.py` and
`repair_initial_cache.py` callers were inspected, not executed. The current first
staging runbook routes activation through the operations CLI, not that helper.
Keeping the historical directory-wide test command unchanged is appropriate here;
it is not certified for reuse with current candidates. The isolated early-exit probe
only verifies bytecode disabling before source access, not that legacy admission path.

## Guard review and fresh execution

The task copied the reviewed runners byte-for-byte before execution:

| Runner | SHA-256 |
| --- | --- |
| `run_bounded.py` | `97f3185a3c117232fd068e511eb8216ecbd09b082f40e04f8c1e92369fbd56b2` |
| `checks.py` | `2a49917d6daf0db1addedf0678c5de55616ce43cc0749e4ec6a0a80040bd770d` |
| `source_checks.py` | `bd443d7132e47d657744db6f39617715db9f4af3cd1d88d2617914256b0c1a30` |
| `envelope.py` | `f181c6283263195d26defe9bdea979027329ef62be1a7061427108c3f6078bc1` |

`run_bounded.py` keeps a 300-second parent deadline and kill/wait via subprocess.run;
its own exit code is not the test verdict: inspect `*-process.json`'s child exit and
timeout fields. It is not an OS process-tree/job sandbox. Reviewed local Git/staging
children have 10-second test deadlines; packet workers retain their timeout, cancel,
reap and parent-pipe logic. No timeout or warning/xfail policy was relaxed.

Installed `checks.py` preloads the root credential/A8R4 data/network guard, removes
original import roots except cached dependencies, changes cwd into the new extraction,
clears Git/Python/pytest overrides, and denies original checkout reads except the
cached venv and owned receipts. Test fixtures are reviewed synthetic/fake paths.
`envelope.py` only permits reviewed argv in newly owned temporary roots. Git receives
a minimal environment, empty home, disabled global/system config, credentials,
prompts, signing, hooks, fsmonitor and attributes; init templates are empty. All
protocols are denied except explicit same-case local `remote.git` file transport.
No configured/inherited remote or actual external repository is used. Approved-child
audit tokens reject direct subprocess escape. The exact staging `-I` probe gets a
minimal environment and a child audit guard before its unchanged early-exit code.

Source `source_checks.py` deliberately allows exact read-only HEAD/two fixed-file
history commands and the existing frozen packet bootstrap. Its Git wrapper clears
system/global/environment config; historical Git is provenance in the source lane
only. Normal packet launches use the minimal environment and hash-verified in-memory
module loader in `scripts/a9_candidate_packet.py`, with network/descendant guards.
The source runner is not the installed runner and does not make project history an
installed dependency. Some human-readable receipt guard labels still abbreviate the
older denial policy; the hashed executable code above is the actual policy.

These Python audit hooks and argv checks are evidence for the reviewed paths, **not
proof of hostile-code security isolation or OS enforcement**. They do not establish
Linux ownership, arbitrary native-library containment or ARM64 behavior. In particular,
the A8R4 hook permits stdlib Windows socketpair construction; that does not guarantee
the platform can complete it. No OS permission/security setting was changed.

Fresh archive: **375 files / 652209 bytes**, SHA-256
`98e75a541c416ff4830517993adc8429b660705c5ede787abd73fbca6421de16`;
source identity `15b74329d83810a02834ad8c04b08951d84a1d3efc9ca8bb5c2b583f04daed42`.
It was newly assembled from current bytes and extracted outside the checkout into
a task-owned OS-temp app. It contains no docs/scripts/.git/root conftest. Its bytes
match the prior final test artifact; no release was built or refrozen. Fresh source
manifest and packet identities are in `source-measurement-review-source.json`.
They are respectively `bd944b774dca8ee5abe2eb793b7a9d818204a5ee26bd56516de49561d5ecefe4`
and `189c848f9960611989975ba3cee930f16b144385165d56d9aaa77844812438e8`.

| Current verification | Actual outcome |
| --- | --- |
| AST/control/hash/archive checks | PASS; all 11 remediation after-identities match |
| Full fresh partition collection | 715 collected; exact 588/127 mapping; no behavioral credit |
| Negative events | 12 existing + 4 additional parent rejection checks PASS; 4 child rejection checks PASS |
| Installed full attempt | 588 collected; 59 complete setup/call/teardown PASS; next case incomplete; 528 subsequent NOT_RUN; no SKIP recorded; 300-second TIMEOUT |
| Mandatory source attempt | 127 collected; 42 PASS lines; next case incomplete; 84 subsequent NOT_RUN; no SKIP recorded; 300-second TIMEOUT |
| Whole-source diagnostic attempt | 1885 collected; 7 PASS / 1 harness FAIL / 0 SKIP; 1877 NOT_RUN |
| Escalated installed attempt | NOT_RUN: automatic approval rejection before process creation |
| Documentation after report/routing additions | 2 PASS / 1 known inventory FAIL / 0 SKIP, 3.17s; links and anchors pass |

Both unfinished lanes stalled in Windows `socket.py:295 accept` /
`_fallback_socketpair:627`, reached from asyncio event-loop initialization, as retained
faulthandler traces show. Installed stalled before the next test's setup report;
source stalled in the first candidate packet case after the 42 harness tests. There
is no final pytest XML/import-inventory receipt for either timed-out run. Independent
post-run byte checks establish extraction/source preservation; they do not turn the
partial attempts into completed module-origin or whole-admission proof.

Automatic approval review rejected `require_escalated` for the same guarded installed
command because the owner explicitly prohibited platform-denial bypass. No approved
retry ran, no source escalation was requested, and no alternate workaround was used.
This is an execution blocker, not evidence that the admission selection is defective.

## Remaining full-source limitation and historical evidence

The fresh full-source failure is exactly
`tests/architecture/test_import_rules.py::test_importing_every_v2_module_has_no_runtime_side_effects`
at line 230. It requests `[sys.executable, '-I', '-c', script]`, cwd=checkout, timeout=15.
Its script imports all V2 modules and forbids SQLite, socket, child-process, task/thread
and environment-read side effects, then checks logging handlers and module count.
`source_checks.py:76` rejects this argv before child creation: it is neither a
read-only Git command nor the exact `-I -B` packet worker bootstrap. Thus this attempt
does not test the import assertions or establish an application import defect.
Fresh result: 7 PASS / 1 harness FAIL in 20.60s console (18.810s JUnit); 1877 NOT_RUN.
The existing audioop deprecation warning remains. The runner was not broadened here.
Simply whitelisting that interpreter is not a reviewed remedy: Python audit hooks do
not transfer to the child, and `-I` ignores its `PYTHONDONTWRITEBYTECODE` environment
setting. Any separate source-runner correction must retain child data/credential/
network denial, explicit bytecode disabling and the original import assertions.
These child properties were inspected statically; the denied child did not run here.
The documentation failure is the unchanged `test_rebuild_documentation.py:92`
assertion that final-audit contains only `a0-phase-0-report.md`; adding this authorized
review does not repair or waive that already-known inventory gate.

Historical results were checked against saved XML/transcripts/process records and
remain historical: diagnosis **563 PASS / 3 FAIL / 22 ERROR**; remediation installed
**588 PASS**, source **127 PASS**, focused **94 PASS** (overlap), negative **12+4**;
full source **7 PASS / 1 harness FAIL / 1877 NOT_RUN**; docs **2 PASS / 1 known inventory
FAIL**. The installed duration is 234.44s console, 232.960s JUnit, 234.984s outer
process: these are distinct measurements, not conflicting test counts. Prior RED,
timeouts and intermediate failed attempts remain intact. No clean whole-suite claim.

## Commands, preservation and one next step

Executed from checkout using `.venv/Scripts/python.exe -I -B`:

```text
scratch/admission-independent-20261009-01/review.py entry
scratch/admission-independent-20261009-01/prepare.py final
scratch/admission-independent-20261009-01/review.py static
scratch/admission-independent-20261009-01/run_bounded.py checks.py installed-review
scratch/admission-independent-20261009-01/run_bounded.py source_checks.py source-measurement-review
scratch/admission-independent-20261009-01/negative_checks.py
scratch/admission-independent-20261009-01/run_bounded.py source_checks.py source-partition
scratch/admission-independent-20261009-01/run_bounded.py source_checks.py source-full
scratch/admission-independent-20261009-01/review.py partition
scratch/admission-independent-20261009-01/review.py summary-final
scratch/admission-independent-20261009-01/route.py
scratch/admission-independent-20261009-01/docs_checks.py docs-review
scratch/admission-independent-20261009-01/review.py preservation
```

The escalation rejection is recorded separately and is not a successful command.
`git -c core.safecrlf=false diff --check` and `git diff --cached --check` passed;
the index has no staged changes.
Final documentation validation and preservation receipts accompany this report.
Only this report and additive notices in the three current routing documents change
non-ignored repository content. All inherited bytes outside those exact insertions,
prior evidence, excluded metadata, HEAD, refs and index are preserved. No production,
real DB/backup/credential, external network, package install, permission change,
deployment, cleanup, commit/push or candidate refreeze occurred. MyFood/MyMoney remain
paused and untouched. Review rollback would remove only this report and its saved
exact routing insertions, retaining all evidence; no rollback was performed.

Whole-source regression, completed independent installed/source reproduction,
truthful committed release identity, reviewed wheel/lock/ARM64/ABI environment,
installed manifest/configuration, Linux/target readiness and all 23 operational
obligations remain open. Original A9/A10 BLOCKED, Integrated administrative
SCOPE-CLOSED and deferred Phase 11 cleanup are unchanged.

**Exactly one next step: obtain an explicit owner decision approving a separately
reviewed local verification execution boundary that supports stdlib socketpair and
the mandatory architecture import probe, while retaining external-network/data/
credential denial and all bounds.** The existing prohibition and automatic rejection
prevent assuming that approval. Do not implement, refreeze or deploy from this review.
