# Remaining installed-admission dependencies - 2026-10-09

**Read-only diagnosis complete; remediation NOT AUTHORIZED/NOT IMPLEMENTED.**
The complete unchanged 588-case selection exposes one mixed source-history test,
not another wholly source-only module. Keep its current-runtime assertions and all
other installed cases mandatory. No runtime/test/policy/archive-root change, skip,
assertion relaxation, Git/source fallback or independent closure occurred.

## Scope, evidence and fresh outcome

The supervisor authorized this local diagnosis after the
[selection-correction stop](admission-selection-evidence-20261009.md). AGENTS,
current plan/active-state/index, operational register and C13 deployment contract
were read. C13 retains both the approved installed subset and full source-review
gate. Original A9/A10 BLOCKED, all 23 operational obligations and deferred cleanup
remain unchanged. Pi remains offline; no Pi/SSH/network/API, real data/credential
access, installation, service, commit/push/reset or inherited-file deletion.

Receipts: [`scratch/admission-boundary-diagnosis-20261009-01/`](../../../scratch/admission-boundary-diagnosis-20261009-01/).
The prior 374-file `green.zip` was reused unchanged, extracted into a new OS-temp
directory outside the repository. Its SHA-256 remains
`169fd3089d7e3bef00cbe19929bcee5a8f6f88e8c928ffb86e8bb081e5ee23eb`;
working-byte source identity remains
`ec109856f353cd3b0c56e3ef5cc4f2956f82f127d13af32907ed00f05b8c8a78`.
This is test material, never a final release or HEAD-only identity.

One complete, automatically approved guarded run outside the Windows filesystem
sandbox used the unchanged selection, `--maxfail=0`, existing warning errors and
strict xfail, disabled cache/bytecode/plugin autoload, and a **300-second outer
bound**. A8R4 credential/data/network guards, real-subprocess denial and original-tree
read denial stayed active. No denied action was permitted on retry; no retry was
needed. Existing test/child-process timeout values were unchanged.

**563 PASS / 3 FAIL / 22 fixture ERROR / 0 SKIP**, pytest **189.85s**; outer process
190.703s, exit 1, no timeout. All 588 cases were attempted, with none deselected or
wholly unattempted. The 22 fixture errors prevented those test bodies from entering;
the three failed bodies stopped at their denied subprocess. Their downstream
assertions remain unverified, not waived. All 25 failures/errors are preserved
`PermissionError: isolated diagnosis denies actual subprocesses` results. No real
Git/Python child was launched, so no native child success/failure is claimed.

`static-inventory.json` maps all **37 selected modules, 588 cases, 62 resolved
fixture definitions**, a 138-file statically resolvable packaged import graph,
and 20 literal `tool(...)` references. All those tool resources are packaged.
`installed-inventory-result.json` hashes 128 imported application modules, all from
the extraction; verifies extracted bytes unchanged; records read attempts and
25 subprocess denials with zero original-source fallback attempts. Read attempts
include normal missing bytecode-cache probes and SQLite `:memory:`, not missing
required application inputs. No root/tests conftest supplies collected fixtures;
the original root guard is preloaded solely for safety before source-read denial.

## Exact affected cases and dependency classification

All names below are under `tests/integration/operations/`. Full parametrized node
IDs, setup/call/teardown status and fixture edges are in `case-disposition.json`.

| Cases | Result | Dependency / required disposition |
| --- | --- | --- |
| `test_a9_bt1_independent.py::test_prechange_rejection_and_fixed_routing` | 1 FAIL | Lines 169 and 197 request two files from fixed repository commit `cb54da9948370db64133a0ead6c9df89d0b61055` using `git show`. Source-history proof mixed with current config/fetch checks; split obligations, not whole module |
| `test_a9_bt1_independent.py::test_real_synthetic_backup_download_restore_and_cancellation` | 1 FAIL | Line 252 enters `LocalTransport.run`; needs Git operating only on new disposable repositories. Current encrypted backup/download/restore/cancellation behavior; retain installed |
| `test_git_backup.py` cases enumerated below | 22 setup ERROR | `store` fixture line 59 -> line 69 -> `LocalTransport.run` line 51. Creates fresh synthetic repository history, not project history; retain installed |
| `test_staging_entrypoint.py::test_isolated_initial_builder_disables_bytecode_before_source_access` | 1 FAIL | Line 28 needs the candidate interpreter `-I -c`, packaged `deploy/staging/build_initial.py`, and synthetic cwd; retain installed |

The 22 Git-fixture cases are exactly these six functions with BOTH `[production]`
and `[isolated]` parameters (12), plus the five-fault matrix (10):

```text
test_publish_readback_download_keeps_legacy_and_ancestry
test_non_fast_forward_or_permission_failure_does_not_retry
test_initial_fetch_failure_has_no_fallback
test_uncertain_readback_is_failure_even_if_remote_commit_exists
test_identity_collision_is_not_overwritten
test_retention_current_tree_bounded_but_history_retained
test_invalid_input_never_contacts_remote
  [production|isolated] x [plaintext|digest|extra_metadata|identity|schema]
```

`LocalTransport` rewrites the fixed synthetic repository label to a newly created
`tmp_path/remote.git`; uses `protocol.allow=never`, file protocol only, disabled
hooks, empty init template, disabled global/system Git config and synthetic author
identity; each command has timeout 10. The 23 dependent cases need an installed
Git executable and temporary filesystem/process support, not this project's `.git`,
developer credentials or network. Git is already an operational tool (C13 source
export/update, backup transport and `docs/operations.md:101` installation list).
Their guard failures are not evidence that they belong in a source-only lane.
The pure `test_retention_keeps_daily_points_beyond_latest_eight` passes separately.

The staging test uses timeout 10 and the current interpreter, loads the packaged
helper with `runpy`, replaces its `Path` entry point, and raises before source or
host access. Its isolated-interpreter property must not be replaced with an
in-process imitation merely to satisfy this diagnostic guard.

No other selected case requires source-only scripts, audit documents, root
conftest, original checkout cwd or project Git history in the inspected paths.
The other 563 cases passed in the isolated extraction. `Path(__file__).parents[3]`
resolves to app and reads packaged deploy assets/config examples; `tmp_path`
fixtures create their own fake credentials/DBs. `scripts/synthetic.sh` and
`docs/example.md` in `test_stopped_release_verification.py:35` are in-memory test ZIP
member names, not repository reads. Windows symlink modeling remains a known test
fixture boundary, not Linux ownership/symlink evidence. Local dependency versions
and Windows success do not prove the reviewed ARM64 wheel/ABI environment.

One adjacent static finding: `deploy/staging/build_initial.py:31-34` still uses the
old directory-wide command; `activate_local.py:53` can invoke it. It is a historical
fixed-revision PHASE 9 helper, and its selected bytecode test intentionally stops
before that command. This is not an additional dependency of the 588 cases, nor an
executed failure here. Do not treat that helper as a verified current-candidate
admission path; its future routing/status needs explicit supervisor disposition.
No historical helper, revision pin or installation path was changed.

## One minimal cohesive correction to authorize next

Split **only the mixed test's history-dependent portion** into a mandatory source
review module outside the operations admission directory, for example
`tests/integration/source_review/test_a9_bt1_history.py`. Keep its current config
and fetch-routing checks in `test_a9_bt1_independent.py`. Keep that module's other
64 cases installed, including the synthetic backup case. The existing two exact
admission exclusions need not expand; no runtime/archive payload-root change is
needed. The new source module remains discovered by full `pytest tests/`.

Preserve these original obligations exactly, with setup/fake boundaries required
to execute each one; `proposed-partition.json` stores their AST identities:

| Original lines | Proposed sole owner |
| --- | --- |
| 171: exact old configuration hash | Source history |
| 187-188: old parser rejects isolated destination with the same error | Source history |
| 205: old store routes fetch to original production destination | Source history |
| 192: current configuration successfully loads the synthetic isolated destination | Installed |
| 208-209: current store executes fetch and routes to `REPOSITORY`, same exact argv assertion | Installed |

Extend partition/provenance regressions and lane documentation with the move and
explicit source obligation. The proposed map accounts for **all 714 original
operations cases**: 713 stay intact and one mixed case becomes two responsibility
units. Thus **715 proposed units = 588 installed + 127 source**, with empty missing
original-case and duplicate-assertion sets. This increase is the split, not a success
quota or duplicated assertion. The existing 126 source cases stay unchanged and
mandatory; their previous PASS is historical here, not a fresh rerun.

The same remediation's evidence plan must separately obtain real outcomes for the
24 installed subprocess cases using an explicitly reviewed synthetic execution
envelope: only disposable local-Git roots and the exact isolated staging probe,
retaining network/credential/original-source denial and existing deadlines. Do not
remove these tests, turn FAIL/ERROR into SKIP, replace real process assertions with
fakes, or broadly allow subprocesses. This diagnosis did not authorize or implement
that envelope. The ordinary installed command itself has no such blanket denial;
the local diagnostic guard is deliberately stronger. Successful collection and the
563 passes cannot substitute for the still-unverified 24 process cases.

## Handoff and preservation

Only this report and one additive routing note in the operational register change
non-ignored repository files. `entry.json` / `preservation.json` bind reviewed files,
all original evidence, dirty work, HEAD/refs/index and excluded-path metadata; code,
tests, selection and archive bytes are unchanged. New local receipts are additive.
The original failed ZIP and all previous incomplete/failed receipts remain intact.
No full repository/source-lane rerun was needed for this diagnosis. Full source and
complete installed acceptance remain mandatory and open; independent closure,
Linux/ARM64, Pi and production work remain NOT_RUN.

Executed from repository root (use a new owned receipt directory for independent
replay; helpers refuse overwrites and resolve the repository two parents above):

```powershell
.\.venv\Scripts\python.exe -I -B scratch/admission-boundary-diagnosis-20261009-01/prepare.py
.\.venv\Scripts\python.exe -I -B scratch/admission-boundary-diagnosis-20261009-01/run_bounded.py
.\.venv\Scripts\python.exe -I -B scratch/admission-boundary-diagnosis-20261009-01/static_inventory.py
.\.venv\Scripts\python.exe -I -B scratch/admission-boundary-diagnosis-20261009-01/classify.py
.\.venv\Scripts\python.exe -I -B scratch/admission-boundary-diagnosis-20261009-01/preserve.py
```

Supervisor review should check the complete failure XML, all case/fixture rows,
mixed-case assertion map, source hashes and historical-helper routing before
authorizing one cohesive remediation. **Stop for review; no implementation or
deployment follows from this report.** If reversal is later requested, remove only
this report and the saved exact routing insertion, retaining evidence and all
pre-existing dirty work. No reversal was performed.
