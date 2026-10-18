# A8V3 independent Phase 8 verification

Date: 2026-10-04. Branch `codex/rebuild-v2`; audited entry HEAD
`f0d0065f7d2f6bf8a767f8af7e77cbcd6ca7d726`. M3 implementation
`0ac1ab55a0748320a56ff54809813663ac149943`.

**Phase 8 PASS for its repository operations contracts; M3 independently CLOSED,
M1/M2 remain CLOSED.** No new material defect found. This is not production
acceptance, A9, Integrated Audit or Phase 11. The original Phase 8 report and
ADR-023 explicitly defer actual host/service, ARM64 and live SLO acceptance to
later phases. Those deferred checks remain unrun here, not relabeled PASS.

## Authority and ownership baseline

Actual Git branch/HEAD matched the assignment; index was empty. Read AGENTS.md,
current active-state (including original audit semantics and latest BC), Phase 8
ledger and document index; original C13/C14/C15 contracts, canonical historical
Phase 8 report, B20 Phase 8 exit/rollback scope, ADR-023/024 and relevant deployment,
rollback, rehearsal and promotion runbooks. Read A8V2/A8R3 reports and unchanged
M1/M2/M3 probes; reviewed current filesystem/build/source, transaction/deployment,
recovery/CLI, service/timer/polkit and their test isolation/fixtures.

No `.agents` or applicable nested AGENTS/skill was present. No subagent or specialized
skill was required. `rg` was unavailable; PowerShell and existing Python were used.
One early absent-directory lookup triggered broader enumeration/access denials;
protected scratch contents were not read. Subsequent directory checks were explicit.
A mistyped historical report path and absent operations conftest were corrected by
reading canonical `phase-8-report.md` and actual root/tests credential/DB boundaries.

[Entry inventory](a8v3-entry-inventory.json): 70 inherited paths, 11 modified /
59 untracked, empty index. Independently verified the latest A8R3 ownership receipt:
67 exact final hashes plus inverse reconstruction of its three owned mixed-document
deltas all match that receipt. Existing source/test/dependency/format changes were
not introduced by this audit. Original probe/report bytes remain unchanged.

ADR-024 supersedes only group-readable immutable modes and credential ACL handling.
Phase 10's approved private Git backup adapter/readback and E3 four-hour timer
supersede the original port-only/uninstalled statements in their historical scope.
E1/E2 restore/publication and E3/E4 running observations are documentary evidence for
recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`. They do not verify this newer candidate or
waive inventory, retention, backup validation, rollback or stopped promotion.

## Independent finding dispositions

| Finding | A8V3 disposition | Fresh basis |
| --- | --- | --- |
| A8-M1 release retention | CLOSED retained | Original4 + remediation78 + independent4 all PASS unchanged |
| A8-M2 verified-backup retention | CLOSED retained | Original2 + remediation36 + independent2 all PASS unchanged; additional real validation resource cases below |
| A8-M3 nested manifest inventory | Independently CLOSED | Exact old modules reproduce original1 PASS/1 FAIL and remediation25 PASS/34 FAIL; current original2 + remediation59 PASS, plus independent boundaries and actual Linux checks |

[Baseline runner](a8v3-baseline-runner.py) loads only exact pre-M3 filesystem/build
modules from `5e846ae6a08e8fda210e6e4a06c457387012604f` into memory after the
credential guard. Dependencies and tests remain current: this is an old-module
negative control, not a full historical environment. It never replaces source/index.
The combined baseline is 26 PASS / 35 FAIL: the unchanged original probe fails with
`rejected=False, current=new`; all 34 prior regression failures independently recur.
Current original probe rejects the same additions and preserves `current=old`.
Its SHA256 remains `ca4079f1cf0f72ca0d9bc11aa258c104526ab59c06fc30eb740bd72aa1890e0c`.
M1/M2 pre-remediation controls were not repeated: their prior independent closures
are preserved, backed here by unchanged current assertions rather than new baseline claims.

Code review confirms validator exemption is only `path / "manifest.json"`; builder
exemption is only `path / ".building"`. Full inventory equality, checksums, containment,
link rejection and incomplete-release guard remain. Root candidate metadata is written
after inventory then removed at publication; the root admission marker is never a
published payload. Nested names are ordinary payload, including under manifest-named
parent directories and Windows/Unix/materialized-lib64 package layouts. Empty directories
remain legal; directory inventory and a new basename blacklist were not invented.

[Independent contract probe](a8v3-contract-probe.py) adds five release cases: a listed
root build marker still rejects, a root marker directory still rejects, and nested
payloads under each reserved parent name validate/reuse until an extra nested manifest
is introduced. The deploy owner temporarily restores owner write for the synthetic
post-publication addition; runtime immutability is not bypassed in production.

[Linux probe](a8v3-linux-probe.py) adds four actual Linux checks: CPython-style
`lib64 -> lib` is materialized with all three nested reserved payload names covered;
0440/0550 modes and real current symlink validate; nested manifest file/directory
symlinks cannot switch current; a killed disposable lock owner releases real flock
without removing/replacing its inode. Existing original2/regression59/filesystem-build25
and independent7 also ran on Linux. Real fsync paths executed; power-loss durability,
separate-user access, credential mounts and cgroups were not proved.

[Source probe](a8v3-source-probe.py) adds two independent paths through real SourceBuilder,
local Git archive, builder and publish. The temporary Git repository includes synthetic
excluded files; exact revision and policy-derived commit export only selected source,
and temporary export cleanup completes. Network fetch/resolve and venv/pip boundaries
are fake; no install, real remote or operational release is involved.

## Backup validation resource and timing evidence

Two independent cases use real synthetic SQLite, encryption, restore and application
validation. They start with eight or 31 paired archives plus latest; 31 pairs enter
create at 63 entries, below the existing 65-entry admission cap. A new archive causes
nine or 32 sequential validations. Every prior archive and prior latest remains until
validation completes; exactly eight valid archives survive pruning. No two completed
private candidate DBs overlap, and rehearsal DBs/sidecars are absent afterward.

Archives are 4,833 encrypted bytes; each observed completed private DB is 122,880 bytes.
First Windows observation: create approximately 0.515s / 2.032s; Linux observation:
0.375881s / 1.234123s. Final Windows rerun metrics are retained in the independent XML.
These tiny synthetic measurements are functional sequencing evidence, not throughput,
maximum RSS/disk use, large-data restore time or production timing acceptance.

Review retains A8V2's bounds: sequential O(candidate records) work; default 64 MiB
restore input, 120s request, 10s startup and 10s inspect budgets plus cleanup and
filesystem work. The 65-entry check is admission-time, not a total-operation deadline
or a bound on direct `retain` directory input. Per-candidate budgets do not add up to
one enforced 180s application deadline; backup service still has 180s start/30s stop,
remote transport its separate 90s budget. There is no newly measured Pi fit, RPO/RTO,
filesystem-stall or kill-during-publication guarantee. No timeout policy was changed.

## Complete scoped gate disposition

| Required repository gate | Result and evidence | Remaining boundary |
| --- | --- | --- |
| Release identity/inventory/root controls | PASS; old/current negative control, 59 unchanged regressions, five independent release cases, real Linux links/lib64/modes | Real installed ARM64 venv/wheel provenance and power-loss testing belong to host acceptance |
| Release retention | PASS; M1 86 cases, age/floor/current/rollback/activation protection across both entrypoints | No real release/history cleanup |
| Exact pins/source/offline build/reuse/failure | PASS; current build suite and two new real local Git export/build/publication cases | venv/pip install and remote fetch faked; real reviewed wheels not installed |
| Lock/pointer/tamper/path escape | PASS; Windows model with real replace, existing fault tests, real Linux symlink/fsync/flock and abrupt child exit | No host power-loss, hostile deploy owner or stalled filesystem claim |
| Deploy order/dependency-pair rollback/cancellation | PASS; current transaction fault suite, real LocalDeployment synthetic DB/backup/release pipelines, single rollback/initial failure/failed stop evidence | Services/commands faked; no operational deployment or readiness claim |
| Backup validation/retention/encryption/remote publication | PASS; M2 40 cases, additional sequencing/resource cases, recovery suite and disposable local bare-Git transport/readback tests | External destination/auth and current production timing not revalidated |
| Restore fallback/rehearsal/promotion | PASS; current restore and explicit promotion fault/guard tests, temporary DBs and actual atomic replacement; CLI guards reviewed | No production candidate, canonical overwrite or real maintenance window |
| Runtime/service/timer/polkit/config/credentials | PASS repository assets/adapters; independent unit scopes, four-hour persistent timer, bounded budgets and narrow start/stop rule reviewed; current asset/runtime/ACL suites executed | No systemd install/enable/start, polkit exercise, actual mounts/shared-group/WAL ownership in this audit |
| Manual/health/telemetry/audit | PASS; current tests cover one private response, lock/race/durable inbox, exact pair identity, shutdown and safe metrics/audit bounds | Live Discord/provider/socket and indefinite monitoring not inferred |
| Architecture/regression/documentation | Scoped assertions PASS except two inherited unrelated known failures in full suite, detailed below; link/anchor checks run after docs | No clean full-suite claim; known inventory/Deno debt retained |
| Historical evidence/supersessions | Documentary comparison complete; original historical limits retained, M1-M3 explain missed earlier boundaries | Historical production source/pin stays distinct |

The original B20/C13-C15/ADR-023 Phase 8 boundary is repository implementation with
synthetic deploy/rollback/restore proof. Original report explicitly assigns actual
systemd verification, credentials/groups, ARM64 packaging and live SLO to Phase 9;
C14 likewise defers actual RPO/RTO/old-key host drills. No new waiver or contract
reinterpretation is needed for the scoped PASS. A fresh current-release Pi/service,
ARM64, live provider, power-loss, production-scale backup timing or RPO/RTO gate cannot
be claimed here. If required by a subsequent gate, exact host/release/action approval,
maintenance/rollback and synthetic-versus-real-data boundaries are prerequisites.
No forbidden live gate was substituted with a synthetic PASS.

## Commands and counts

Windows commands use existing `.venv/Scripts/python.exe`, with
`PYTHONIOENCODING=utf-8`, `PYTHON_DOTENV_DISABLED=1`, `PYTHONDONTWRITEBYTECODE=1`.
Common flags: `-q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
-p no:cacheprovider --tb=short`. Every run writes the linked XML with `--junitxml`.

1. `python docs/rebuild/final-audit/a8v3-baseline-runner.py docs/rebuild/final-audit/a8v2-release-probe.py tests/integration/operations/test_release_inventory_contract.py`.
2. `python -m pytest` with unchanged a8v2-release, a8-retention, a8v1-retention,
   a8v1-backup, a8v2-backup probes and test_release_inventory_contract,
   test_retention_contract, test_backup_retention_contract under operations.
3. `python -m pytest docs/rebuild/final-audit/a8v3-contract-probe.py`.
4. `python -m pytest tests/integration/operations tests/integration/data tests/unit/platform tests/architecture`.
5. `python -m pytest tests/`.
6. `python -m pytest docs/rebuild/final-audit/a8v3-source-probe.py docs/rebuild/final-audit/a8v3-contract-probe.py -o junit_family=xunit1`.

[Linux runner](a8v3-linux-runner.py) records exact selection/flags; existing WSL Python
runs a code-only 368-file snapshot in a newly allocated directory under the authorized
`/home/dlrjsdn/discordbot-a2-linux-verify`. Root credential guard is imported explicitly;
`--confcutdir` excludes legacy DB fixtures. No installed environment is changed. Snapshot
hash and successful private-workspace cleanup are in [Linux receipt](a8v3-linux-evidence.json).

| Receipt | PASS | FAIL | SKIP | Evidence |
| --- | ---: | ---: | ---: | --- |
| [M3 negative control](a8v3-m3-baseline-results.xml) | 26 | 35 | 0 | Original2 + remediation59; 12.18s; excluded from current union |
| [Focused current](a8v3-focused-results.xml) | 187 | 0 | 0 | M1/M2/M3 original/remediation/independent; 149.41s |
| [First independent resource/release run](a8v3-contract-results.xml) | 7 | 0 | 0 | Windows; 4.89s; repeated below |
| [Affected regression](a8v3-regression-results.xml) | 809 | 1 | 0 | Operations/data/platform/architecture; 178.44s |
| [Final independent Windows](a8v3-independent-results.xml) | 9 | 0 | 0 | Release5 + resource2 + source2; 8.08s |
| [Real Linux](a8v3-linux-results.xml) | 97 | 0 | 0 | 93 repeated identities + four Linux-specific cases; 6.14s |
| [Full suite](a8v3-full-results.xml) | 1562 | 2 | 27 | 227.44s; known inventory/Deno failures |
| **Distinct current union** | **1589** | **2** | **27** | **1618 identities, zero XFAIL; platform repeats excluded** |

Final [documentation link/anchor checks](a8v3-doc-results.xml): 2 PASS in 1.34s;
these identities already occur in the full suite. The two known failures are
`test_rebuild_documents_are_partitioned_without_loss` (stale audit-file allowlist) and
`test_pinned_provider_and_runtime_load_without_network` (missing Deno runtime).

Baseline controls are excluded from the final union; duplicate selections and repeated
Windows/Linux runs are not added as new test identities. Detailed identity/count/hash
provenance is in [test evidence](a8v3-test-evidence.json). First seven-case Windows run
reported two harmless record_property/xunit2 compatibility warnings; properties were
present in XML. Final rerun uses xunit1. Owned new text artifacts are canonical LF;
receipt hashes match the staged artifacts after XML trailing-whitespace normalization. The release probe received an owner-write
portability line before Linux execution; no expectation, fixture outcome, skip or xfail
was weakened. No functional harness failure occurred. One ownership-reader attempt
used the host default decoding and failed before any write; UTF-8 rerun succeeded.

Known stale documentation inventory, missing Deno, 27 opt-in Linux/systemd skips,
audioop deprecation and A3-N1/A3-I1 limits remain explicit. Real Linux filesystem proof
here does not convert those systemd skips into passes. The original report's earlier
completion did not expose M1-M3; those historical misses and exact RED evidence remain.

## Preservation, cleanup and next boundary

Owned deliverables are only A8V3 probes/runners/XML/JSON/report and compact BD/Phase8
routing deltas. No runtime fix, dependency install/upgrade, schema/format change, source
history cleanup or assertion weakening. [Ownership receipt](a8v3-ownership-receipt.json)
checks all inherited70:68 exact hashes and2 inverse-owned authority deltas. Untracked
document index, handoff exports and prior audit evidence remain untouched.

Only owned new files and HEAD plus owned routing deltas are staged; inherited changes
are not bulk-staged. Staged diff and `git diff --cached --check` are reviewed before the
single local Conventional Commit. Final commit SHA and residual status are in the
handoff; report identifies audited code HEAD above to avoid a self-referential hash.
Rollback is a scoped revert of this audit commit while preserving inherited edits;
there is no product/data rollback. No push/force-push/reset.

All test sessions and owned child processes finish; fixtures close DBs/executors and
remove private intermediate plaintext. The Linux child is explicitly killed/reaped
within its test and the entire newly allocated Linux tree is removed after restoring
owner write on synthetic immutable directories. Existing WSL environment and unrelated
processes remain untouched. Local code-only transfer archive is removed at completion.
No owned persistent server/browser/worker, pending write or service change remains.
WSL access required sandbox escalation; authorized read and isolated execution succeeded.
No automatic approval review rejection occurred.

No Pi/production connection, actual backup/release/preservation cleanup, real DB
restore/reset/migration, deploy, systemd/routing/network/security change, credential/data
copying, external provider, MyFood or my_money operation. Recorded production identity
is unchanged. A0-A7 PASS preserved; friend activation HELD and Integrated deployment
condition unmet. **STOP A8V3 for supervisor review.** A9 or any live operation requires
its separate assignment; no A9, Integrated Audit or Phase11 work started.
