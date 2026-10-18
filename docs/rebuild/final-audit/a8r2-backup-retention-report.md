# A8R2 backup retention remediation

Date: 2026-10-04. Branch `codex/rebuild-v2`; entry HEAD
`01d848555cfbf35115523752982a7ddb711ce09f`. Implementation commit
`ca8078fc4b84e57b46a63ac534edc34480bce19f`.

**Scoped remediation PASS. Phase 8 remains FAIL. A8-M1 independently CLOSED;
A8-M2 remediated, OPEN pending independent verification.** No A8V2/A9,
Integrated Audit, Phase 11 or production work was performed.

## Authority and scope

Git branch/HEAD/index and all 70 inherited contents were inventoried before writes:
11 modified, 59 untracked, empty index. Read repository AGENTS.md, active-state,
Phase 8 ledger row, document index, original C13/C14/C15 contracts, B20 exit/rollback,
Phase 8 report, ADR-023/024, backup verification runbook and A8V1 exact RED/report.
A8R1 and current release retention were reviewed to retain M1 protection. Original
contracts remain authoritative; historical Phase 10 remote-adapter acceptance does
not waive eight verified local alternatives. Recorded host evidence is not fresh proof.

There is no checkout `.agents`/`.codex` or governing nested AGENTS/skill. No relevant
specialized skill or sub-agent was needed. `rg` was unavailable; PowerShell, Git and
existing `.venv` Python were used without installing packages. An initial PowerShell
read used the wrong text encoding and an absent `.agents` lookup attempted directory
enumeration; subsequent reads used explicit UTF-8 and existence checks. No protected
scratch content was read. The October 4 resumed supervision has no new time cutoff.

## Root cause and minimal correction

`Backups.retain` selected the first eight metadata filenames before validating their
archives. Remote failure naturally leaves local artifacts and metadata. Seven newer
corrupt failed-publication records could consume seven retention slots; the next
successful create then deleted all eight independently recoverable prior snapshots.
This was the original Phase 8 implementation, not an M1 release-retention regression.

The change is confined to the operations recovery adapter, one regression module,
the relevant runbook and a CHANGELOG entry. No codec/schema/metadata format, remote
policy, service setting, dependency, public command or retention threshold changed.

- Extract the existing isolated restore validation/cleanup into `_validated_candidate`.
  Both rehearsal and retention use the same metadata identity/key/schema/checksum,
  real decryption/restore, semantic validation and independent application startup
  compatibility checks. No checksum-only definition of recoverability was substituted.
- Compute the complete pruning plan before success audit and latest replacement.
  Validate the newly emitted artifact after remote publication as well. Corruption
  of that artifact prevents pointer advancement or pruning. Candidate corruption is
  excluded from the floor; operational I/O faults and cancellation propagate before
  any deletion. All private DBs, executors and plaintext sidecars are closed/removed.
- Keep eight newest *verified* candidates in the existing filename-ID order. Pin the
  prior latest and the new candidate independently, even if clock regression or newer
  valid orphans puts either outside that floor. Pins can add an extra archive; they
  do not consume or shrink the eight-point recovery floor.
- Invalid, absent-artifact and old-key records remain for operator reconciliation,
  never counted or automatically cleaned. A failed remote operation's locally valid
  orphan can still be recoverable, exactly as C14 already states. The hard 65-entry
  admission policy remains; accumulation can still require operator inspection.
- Only after validation, success audit and latest publication does `_prune` delete
  eligible excess verified archives. A subsequent unlink failure remains visible and
  may leave a partial excess pair, while the eight selected alternatives and latest
  remain. No unsafe compensating rollback overwrites the newest legitimate pointer.

`retain(count)` now awaits validation; repository-wide source/test/deploy references
showed its only prior production caller was `create`, which now calls planning and
pruning around its existing commit point. The adapter's direct retained entrypoint
is covered too. This is not a change to the deployment port's separate synchronous
release retention. M1 implementation files are untouched. Restore candidate selection
still examines at most eight newest metadata records by default; explicit candidate
IDs remain available. This microphase does not redesign that separate selection policy.

Validation reuses existing per-candidate deadlines and sequential temporary work.
It adds local decrypt/SQLite I/O under the existing operations lock. The 180-second
backup service budget is unchanged; production-scale duration/RPO/RTO is unmeasured.
A real host timeout, filesystem power loss and post-replace fsync uncertainty are not
proved by Windows synthetic tests. This is a stated limit, not a latency/SLO PASS.

## Unchanged RED to GREEN and fresh evidence

The original [A8V1 backup probe](a8v1-backup-probe.py) is byte-identical, SHA256
`0ea8cf50a6806392f671d025c332ceb1d81dd3a97f005b38a13b574d2ef3497a`.
It independently restores all eight prior backups, rejects the seven corrupt orphans,
and restores the new snapshot. Before the fix its exact assertion reports
`kept 0 prior verified + 1 new; kept 7 independently rejected corrupt publications instead`.
Afterward the unchanged assertion passes: at least seven prior verified snapshots
survive with the new snapshot. No assertion, skip, xfail or recovery contract was weakened.

| Receipt | PASS | FAIL | SKIP | Meaning |
| --- | ---: | ---: | ---: | --- |
| [Original RED](a8r2-original-red.xml) | 1 | 1 | 0 | Exact unchanged M2 probe on entry implementation |
| [Initial boundary RED](a8r2-boundaries-red.xml) | 12 | 14 | 0 | Initial 26 new tests, before implementation fix |
| [Initial focused GREEN](a8r2-focused-green.xml) | 41 | 0 | 0 | Original M2 2 + initial26 + existing recovery13 |
| [Final affected regression](a8r2-regression-results.xml) | 760 | 1 | 0 | Operations/data/platform/architecture + ten original/independent probes |
| [Standard full suite](a8r2-full-results.xml) | 1503 | 2 | 27 | Existing inventory/Deno failures and Linux skips retained |
| **Distinct final current union** | **1513** | **2** | **27** | Full suite plus ten audit-only probes; repeats excluded |

All final selections have zero XFAIL. Receipt identities determine overlap: the 36
new boundary tests and 78 M1 remediation cases are already in the full suite. The
regression includes original M1 four, independent M1 four and original M2 two, all
PASS, and those ten are additional to `tests/`. Initial RED/focused runs are not
added to the final unique union. Full-suite elapsed time: 207.91 seconds.

The final 36 new cases cover ten invalid-record shapes (including a matching checksum
on authenticated but semantically/schema-invalid contents), valid-only counts
0/1/7/8/9/10, recoverable remote-failure orphans, timestamp/mtime versus ID ordering,
prior latest protection, remote/success-audit/pointer failure, cancellation and
permission/disk faults, direct retention counts/idempotence, backdated new latest,
missing/corrupt pointer repair, old-key preservation, 64/65 admission boundaries,
and partial pruning failure. Kept candidates are actually restored in the relevant
survival tests, not merely counted. No real DB/archive/release/history is involved.

After the first 26-test GREEN, ten further review cases were added and the ordering
fixture additionally perturbed mtimes. The final regression and full suite cover
that final 36-case module. Only the original 26-case version has a pre-fix RED receipt;
no pre-fix outcome is claimed for the added ten cases. The original A8V1 probe stayed
unchanged throughout. There were no test-authoring failures or relaxed expectations.

The known failures are `test_rebuild_documents_are_partitioned_without_loss`
(stale expectation of only the A0 audit Markdown report) and
`test_pinned_provider_and_runtime_load_without_network` (missing release-local Deno).
They were neither skipped nor fixed. Known audioop deprecation, Linux/systemd skips,
A3-N1/A3-I1 and documentation inventory limits remain. No clean full-suite claim.

## Exact commands and evidence type

PowerShell, repository root, existing environment; no installation:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$strict = @('-q', '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning', '-p', 'no:cacheprovider', '--tb=short')
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-backup-probe.py @strict --junitxml=docs/rebuild/final-audit/a8r2-original-red.xml
.\.venv\Scripts\python.exe -m pytest tests/integration/operations/test_backup_retention_contract.py @strict --junitxml=docs/rebuild/final-audit/a8r2-boundaries-red.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-backup-probe.py tests/integration/operations/test_backup_retention_contract.py tests/integration/operations/test_recovery.py @strict --junitxml=docs/rebuild/final-audit/a8r2-focused-green.xml
.\.venv\Scripts\python.exe -m pytest docs/rebuild/final-audit/a8v1-backup-probe.py docs/rebuild/final-audit/a8-retention-probe.py docs/rebuild/final-audit/a8v1-retention-probe.py tests/integration/operations tests/integration/data tests/unit/platform tests/architecture @strict --junitxml=docs/rebuild/final-audit/a8r2-regression-results.xml
.\.venv\Scripts\python.exe -m pytest tests/ @strict --junitxml=docs/rebuild/final-audit/a8r2-full-results.xml
```

Common flags were repeated literally in the executed invocations. XML trailing
whitespace is normalized for Git only; assertions/outcomes remain unchanged. The
final [document anchor/link tests](a8r2-doc-results.xml): 2 PASS in 0.49 seconds, a
subset of the full suite, not extra unique cases.

Root credential guard was read before test collection. Existing database fixtures route
to temporary SQLite/SQL paths; new tests use temporary real encrypted archives and
generated keys. Remote/services/build boundaries are fake. Existing Git adapter tests
use disposable local repositories. Full-suite subprocess/network call sites and opt-in
Linux guards were inspected: local synthetic children, offline version checks, ASGI
transports and JS harnesses; no live providers or production credentials. This is Windows
repository/synthetic evidence. WSL was unnecessary and was not started; no reinstall.

## Ownership, rollback, cleanup and next boundary

[Entry inventory](a8r2-entry-inventory.json) and [ownership receipt](a8r2-ownership-receipt.json)
record 70 inherited files. Exactly three mixed files receive owned deltas: CHANGELOG
insertion, active-state BA append and Phase 8 ledger-row replacement. Inverse byte
reconstruction preserves all 70 contents; the other 67 are byte-identical. The inherited
untracked document index, exports and all original A8/A8R1/A8V1 evidence remain intact.

Implementation and evidence are separate scoped local Conventional Commits. Staging
uses HEAD plus only owned patches for mixed files, never their whole working copies.
Each staged diff and `git diff --cached --check` is reviewed before commit. Managed
`.git` write escalation was used only for authorized staging/commits; no automatic
approval rejection occurred. One document assembly attempt stopped at ledger-column
indexing before writing that ledger; it was corrected before staging. Final HEAD/index/status
are supplied in the handoff.
Rollback is a scoped revert of `ca8078fc4b84e57b46a63ac534edc34480bce19f`, preserving
inherited CHANGELOG edits; the separate evidence commit can separately revert routing.
No production rollback or remote history rewrite is involved.

All owned pytest commands exited, fixture DB/executor/child cleanup completed, and
no owned server/browser/WSL/persistent worker or pending test write remains. No
unrelated process was stopped. All destructive test effects were confined to clearly
synthetic temporary fixtures. No actual archive/release/history cleanup was performed.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and untouched. No Pi/production
connection, real DB change/restore/migration, deploy, systemd/Cloudflare/network/security
change, live provider, production data/credentials, MyFood/my_money work, push or force push.

**STOP A8R2 for supervisor review.** M1 remains independently CLOSED, M2 remains
pending independent verification and Phase 8 remains FAIL. Next separate authorization:
fresh unchanged M1/M2 probes, independent publication/validation/retention/fault challenges,
and the remaining original Phase 8 gates listed in A8V1. Current timing/real Linux/Pi/SLO
limits remain explicit. No A8V2/A9/Integrated/Phase11 is started here. A0-A7 PASS retained;
friend activation HELD and Integrated deployment condition unmet.
