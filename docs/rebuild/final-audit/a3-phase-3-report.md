# Final Audit A3 — Phase 3

Date: 2026-09-27. **Verdict: FAIL.** One unresolved **MATERIAL** finding,
**A3-M1**, defeats the required unknown-schema rejection boundary. No remediation
was performed. This is a Phase 3 audit, not a verdict on Phases 4–10 or Integrated Audit.

## 1. Candidate, authority and scope

Read first: [active state](../current/final-audit-active-state.md),
[ledger](../current/final-audit-ledger.md), and [S0 document index](../current/final-audit-document-index.md).
Entry rows were A0/A1/A2 PASS and A3–A10 NOT_AUDITED.

- Git HEAD: `1538aa4274063b416ec50c706261fac1c6b05a46`.
- Runtime candidate: `3a4058caca4e6b9b4b900c458a0e98a825d13d44`.
- `git diff --name-only 3a4058c HEAD` contains only `CHANGELOG.md` and
  `docs/rebuild/phases/phase-02/platform-contract.md`. No storage runtime delta.
- The audit target includes the current worktree. Seven pre-existing tracked changes
  and existing untracked audit/Phase 10/handoff/browser artifacts were preserved.
  The pre-existing modified test is `tests/browser/watch_fixture.py`, outside A3.
- Recorded production identity remains source `8e9018d4b8061cde6006eee47fa4103522f77718`,
  release `r-8e9018d4b8061cde-3dac82a792fad576`. This is documentary evidence only;
  no host connection or production observation occurred.

Phase 3 supplies context-owned SQLite compatibility repositories, bounded DB
execution and startup validation, an expand-only migration ledger, verified
snapshots, encrypted/legacy backup readers and explicit recovery to a new path.

Authority reviewed through S0's Phase 3 mapping, using relevant sections only:

| Authority class | Documents and applicable sections |
| --- | --- |
| BASELINE / DESCRIPTIVE | B03 F001/F005 and persistence inventory; B06 relational model, recovery gaps and target meaning; B08 BR-017–019 and persisted-volume rule; B09 AUD-001/002/012/015/016/023 |
| NORMATIVE | B11 data/security/acceptance; B12 FR-001/006/009/020/025/031–032/045–047/050; B13 storage-related reliability, bounds, isolation, privacy and testability; B14 layers/storage/fail-closed ownership; B15 DB lanes and cancellation; B16 transaction/error policy; B17 DB telemetry/health/privacy; B18 persistence/credential boundaries; B19 repository/data failure strategy; B20 Phase 3 and migration/rollback gates; B21 dependency/public-contract rules |
| Accepted normative decisions in living documents | D22 Q-B01–04/Q-B07 and Phase 3 evidence limits; D23 ADR-002/010/013/014/017/018, plus storage-specific ADR-019/021/022/023 changes |
| Supplemental NORMATIVE | S1 product-spec §§4–5 (V1 context distinguished from V2); C3 platform ownership/termination contract; C4 [data compatibility contract](../phases/phase-03/data-compatibility-contract.md) |
| HISTORICAL, not independent proof | [Canonical Phase 3 report](../phases/phase-03/phase-3-report.md); C5 [actual-copy rehearsal](../phases/phase-03/migration-rehearsal.md); T's Phase 3 overlay; completed [E1](../current/phase-10b-e1-evidence.json)/[E2](../current/phase-10b-e2-evidence.json) recovery receipts |

Permanent requirements: preserve legacy keys/values and user-global favorites;
keep guild predicates; preserve fractional seconds, nullable legacy pairs and
raw titles/URLs; reject unknown/invalid schema and ledger; no implicit empty DB
or destructive recovery; copy-only migration/restore; atomic step/ledger commits;
bounded worker ownership and deadlines; authenticate whole-file new backups;
validate before publication; retain old readers and protect private data.

Out of scope: feature UX, XP/calendar formula implementation, Watch actor/write
lifecycle, Music JSON/default/ACK and play-accounting policy, remote transport,
scheduler/retention/key rotation, Pi capacity/durability/RPO/RTO measurements,
canonical promotion/cutover and legacy deletion. Later code was inspected only
where it consumes or changes these Phase 3 data boundaries.

Dependencies: Phase 0 accepted scope/compatibility decisions; Phase 1 legacy
schema/readers and corrective zero-byte expectation; Phase 2 executor, typed
errors, managed-resource readiness and cleanup ownership.

## 2. Historical implementation and explicit supersession

Git confirms the report's implementation commits `f13e374` (repositories/execution/
validation/ledger), `0b2193b` (recovery/rehearsal), and completion-document commit
`72a62bdf5529338f33b8666abc25b3c1758aad0f`. Historical claims include 282 passed /
12 xfailed, 800 repeated concurrency/migration checks and two actual-copy rehearsals.
Those old commands were not rerun on an old checkout and their counts are not new proof.

C5 records six-table reconciliation and V1 reader parity on isolated copies;
actual Watch tables were empty. Fresh synthetic tests cover nonempty Watch rows.
No actual DB, backup or ignored rehearsal output was opened for this audit.

| Difference | Classification and authority |
| --- | --- |
| B20 initially assigned music JSON to Phase 3 | **Explicit supersession:** C4's scope-discrepancy table, ADR-018 and T defer JSON to Phase 7 under the Phase 3 user direction |
| B15 proposed two readers; implementation uses one | **Explicit supersession/refinement:** ADR-018/C4 specify one bounded reader and one writer |
| B21 proposed a separate migrations directory | **Explicit supersession/refinement:** C4 locates the reviewed registry and SQL together in `storage/adapters/migrations.py` |
| Original migration ceiling 2 becomes 5 | **Compatible evolution:** ADR-019/021/022 authorize additive engagement/Watch/Music metadata. Versions 1/2 definitions remain unchanged; metadata reconciliation was added to snapshot/migrate/backup |
| Historical storage not wired to production; current executable consumes it | **Compatible evolution:** later composition and ADR-023 operations connect the same validation/recovery layer; this does not waive validation |
| Added probe diagnostics (`5e1a8b8`) and cleanup ownership marker (`d042e5e`) | **Compatible evolution:** fixed read probe and typed outcomes; retained cleanup ownership under the accepted A2 contract |
| Unknown generated columns accepted | **Original defect still present**, not a legitimate supersession or a newly introduced later-phase regression |

No later approval allowing unknown generated columns was found. The later metadata
allowlists apply to named, reviewed tables and do not authorize arbitrary legacy columns.

## 3. Requirement-to-current-evidence comparison

“Supported” below describes the inspected requirement only; it is not a partial A3 PASS.

| Material requirement | Original implementation | Current implementation / later change | Current evidence and conformance |
| --- | --- | --- | --- |
| Context ports and immutable DTOs; parameterized SQL | Context `ports/repository.py` and `adapters/sqlite_repository.py` | Same boundaries; Music adds `record_start`, engagement adds a separate event adapter | Repository assertions and architecture checks support preserved ownership |
| User-global favorites; guild-isolated membership/settings/counts/Watch | Explicit user/guild keys and playlist join | Same Phase 3 read/CRUD methods remain; no favorite membership insert | Two-guild/global-row tests, original-value and V1-reader comparisons support preservation |
| No rounding, URL normalization or read-side history trimming | Raw six-table projection, stable ordering and paging | Legacy projection remains; known nullable pairs projected as NULL | Fractional seconds, 27 favorites, 60 history rows, Unicode/quotes/newlines and nonempty Watch tests supported |
| Dedicated bounded DB lanes | One reader/writer, configured admission and same-thread connections | Same path through current bounded executor; no media executor/global DB lock | Real SQLite lock/barrier, queue/cancellation/deadline/progress tests supported |
| Short transactions and uncertain commit semantics | Read BEGIN/query-only, write BEGIN IMMEDIATE, checkpoint before commit | Same transaction code; typed nonretryable DB deadline and late worker observation | Read cannot mutate; pre-commit cancel rolls back; queued canceled mutation never runs. Post-commit ambiguity remains documented, not promised away |
| Fail-closed startup without restore/create side effects | `inspect_path` → `checked_validation` → `require_valid` | Shared gate still precedes readiness, but schema inspection omits generated columns | Missing/zero/corrupt/ordinary wrong-schema tests pass; **A3-M1 FAIL** for unknown generated columns |
| Exact known schema and semantic validation | Six-table PRAGMA layout and row checks | Approved metadata allowlists/checksums added; legacy PRAGMA path unchanged | Ordinary unknown columns/tables/triggers rejected; **A3-M1 FAIL**: hidden schema affects writes yet is accepted |
| Version/checksum/time and per-step rollback/resume | Registry versions 1/2, DDL+ledger transaction | Versions 3–5 explicitly additive; applied definitions checked | Tampering, gaps, failure rollback/fresh-connection resume and repeat migration tests supported, subject to legacy-schema gate defect |
| Preserve source; publish only new migration/restore DB | Verified snapshot and no-clobber hard link | Same publication primitives; metadata parity added | Source-byte preservation, existing destination refusal, failure cleanup and old-reader tests supported; acceptance quality affected by A3-M1 |
| Consistent snapshot, encrypted output and legacy readers | Pinned read transaction, SQLite backup, whole SQL Fernet, parser/authorizer | Same envelope; known extension tables/index permitted | Real concurrent cross-table write test, wrong-key/tamper/legacy/V1-reader round trips supported; shared validator misses A3-M1 |
| Restricted restore and fallback | SQL authorizer, bounded input/candidates, explicit destinations | Same primitives used by later operations | ATTACH/PRAGMA/extension/virtual table/partial dump rejection; invalid local→valid supplied candidate; last-good preservation supported |
| Lifecycle, private errors and rehearsal safety | Managed DB resource; bounded observations; aggregate-only isolated script | Runtime wiring and cleanup marker added | Startup gate/readiness, lane closure, redacted error and source-isolation tests supported. No new A2 lifecycle defect identified |

Current source reviewed: `src/discordbot/storage/{ports,adapters}/` core contracts,
execution, schema/extension definitions, migrations, recovery, codec, files and
input validation; three context repository ports/adapters; `scripts/rehearse_v2_data.py`;
data-related composition and operations call sites. Probe tests and the synthetic
production-candidate tests were included as direct data successors, not a Phase 10 audit.

## 4. A3-M1 — MATERIAL: unknown generated columns bypass schema validation

**Requirement:** C4, “Validation and explicit recovery,” lines 77–85 requires
`wrong_schema`/fail-closed for unknown columns. B12 FR-001, B14 failure isolation
and ADR-014/018 require validated compatibility before writable readiness and
verified recovery. C4 has no exception for generated columns.

**Exact defect:** `src/discordbot/storage/adapters/schema.py:106` reads
`PRAGMA table_info` and compares only its returned columns. On the current SQLite
runtime, that PRAGMA omits generated columns; the public gate therefore accepts
an unknown column. `projection()` and the legacy digest also cover only declared
known columns. An extra generated column can impose a new CHECK constraint while
all expected values and checksums still match.

Propagation: `execution.py:76` (`checked_validation`) and `:207` (`start`);
`recovery.py:49/60` (snapshot), `:101` (migration), `:121` (restore), and `:175`
(backup round-trip validation) reuse this validator. The real later executable
compatibility gate `operations/adapters/cli.py::validate_candidate` adds a version-5
check, not independent column validation. Both production composition roots consume it.

**Independent offline reproduction:** an inline Python process created a temporary
six-table DB with one synthetic membership and executed:

```sql
INSERT INTO users VALUES (10,100,1,1,0,NULL,NULL);
ALTER TABLE users ADD COLUMN unexpected INTEGER
  GENERATED ALWAYS AS (xp) VIRTUAL CHECK (unexpected < 2);
```

It then called the real `SqliteDatabase.inspect/start`, `DataRecovery.migrated_copy`,
`backup`, `restore_copy`, and `SqliteEngagementRepository.add_progress(100,10,1,0,...)`.
The backup key was freshly generated, all paths were in `TemporaryDirectory`, and
resources were stopped in `finally`. No mocks, production input or persisted test file.

Observed safe output:

```json
{
  "table_info_columns": 7,
  "table_xinfo_columns": 8,
  "inspect": "valid",
  "startup": "accepted",
  "migration": "valid",
  "backup": "valid",
  "restore": "valid",
  "unknown_column_retained": true,
  "ordinary_xp_increment": "DataIntegrityError"
}
```

The migration reached the current registry, and encrypted restore retained the
unknown column. Thus this is an observable false compatibility/readiness result
and propagation through verified artifacts, not merely missing test coverage.
No mutation of the source by migration/restore or plaintext publication was observed.

**Historical comparison:** loaded only `schema.py` from `git show 0b2193b:...` into
an isolated module and ran `create_legacy_schema`/`validate` on an in-memory DB with
the same synthetic schema. Output was `{"historical_phase3_validator": "valid"}`.
The historical/current diff leaves the faulty legacy PRAGMA comparison unchanged.
The defect predates later phases; historical PASS did not cover it.

**Test gap:** `test_failure_validation.py` checks a normal `ADD COLUMN unexpected
TEXT` but no generated/hidden column. `test_schema_contract.py` checks partial layouts.
The 127 passing data tests do not establish the universal unknown-column claim.

**Impact and risk:** Phase 3 validation/reconciliation is affected; consumers in
Phases 4/6/7 and recovery/release/cutover gates in Phases 8/9/10 may trust the false
result. This is not a new defect in A0–A2's audited decision, characterization or
lifecycle machinery. The permanent fail-closed requirement is violated at A3's
implementation boundary; A0/A1/A2 ledger PASS rows remain unchanged.

Production risk is conditional on an unexpected schema being presented; this audit
does not claim that production contains one or that user data has been lost. Git
comparison found no difference in `schema.py`, `recovery.py` or `backup_codec.py`
between recorded production source `8e9018d` and HEAD, so the same validator code
is potentially exposed there. Historical E1/E2 success on known schema is useful
positive evidence, not proof of rejection of this case. No production action is justified
or authorized by this finding.

**Smallest proposed A3R scope:** add synthetic regression coverage for unknown
generated/hidden columns, including public startup and migrated/backup/restore
acceptance; make the known-schema check enumerate all columns and reject unsupported
ones while retaining both approved nullable-pair variants and migrations 1–5.
Check the ledger layout for the same inspection blind spot. Preserve file formats,
existing data, valid-reader behavior and copy-only publication. Re-audit A3 and
the directly affected candidate/recovery gates after repair; do not redesign feature
logic, migrate real data or deploy as part of that fix. Rollback would be reverting
the isolated future code/test change; no data rollback is needed for this audit.

## 5. Test/evidence validity and retained paths

Fresh executions used repository `.venv`, `PYTHON_DOTENV_DISABLED=1`,
`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and strict runtime/unraisable warnings:

```text
python -m pytest tests/integration/data/ -q -p no:cacheprovider
  -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
127 passed in 8.27s

python -m pytest tests/characterization/test_database_recovery_contracts.py
  tests/architecture/test_import_rules.py -q -p no:cacheprovider
  -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
14 passed in 1.72s
```

Total fresh focused evidence: **141 passed**, plus current public-path and historical
synthetic probes above. No full strict suite was run and no whole-suite PASS is claimed.
No Deno-dependent test was needed; global A2-N1/Deno/audioop notes are not A3 findings.

Fixtures redirect V1 DB/backup paths to temporary directories. The legacy builder
uses synthetic rows, closes V2 resources and collects V1's legacy connection handles.
Recovery tests use generated keys. Fault injection substitutes failure boundaries,
not successful validation results. The snapshot barrier calls the real backup API
while the real writer commits. Probe contention uses a synthetic child process with
pipe synchronization and `communicate`/reaping. The rehearsal restores V1 globals in
`finally`, and its test asserts this explicitly. No concrete order/global-state
dependency was found in this scope; arbitrary order permutations were not executed.

The V1 reader is intentionally retained for rollback. Phase 3's `SqliteWatchRepository`
is now a compatibility/rehearsal reader; live Watch uses its later writer adapter.
Engagement's compatibility repository remains used by its service, Music's by live
composition. Their tests therefore prove their stated storage contracts, not complete
later-feature behavior. No additional unsafe duplicate production route was established.

## 6. Other findings, disposition and hygiene

- **BLOCKER:** none.
- **MATERIAL:** A3-M1, unresolved; A3 cannot PASS.
- **MINOR A3-N1 — documentation drift:** S1 `docs/product-spec.md:133` still describes
  Phase 3 as not connected to operations. Current composition and completed E1/E2
  contradict that present-tense status. C4/report statements about no wiring are valid
  historical scope, but S1 needs a dated historical label/current routing in a later
  documentation change. No runtime-policy ambiguity overrides C4's schema rule.
- **INFO A3-I1 — evidence boundary:** historical actual Watch tables were empty;
  nonempty compatibility is synthetic. Fresh production verification was neither
  required for the reproduced defect nor attempted.

Only the A3 ledger row, an appended compact A3 active-state result and this report
were changed. A0–A2 PASS and A4–A10 NOT_AUDITED are preserved. Runtime/source/tests,
dependencies, credentials, production, services, releases and preservations were not
changed. No SSH, real backup/restore, deployment, package installation, commit, push,
rebase/history rewrite, cleanup of user artifacts, A4, Integrated Audit or Phase 11.

`git diff --check` and explicit whitespace checks of these untracked audit documents
pass. The tracked worktree diff fingerprint is unchanged; other ledger rows and
the existing active-state prefix are preserved. Audit probes removed their temporary
DB/encrypted artifacts; no DB/log/cache/backup artifact was added to the repository.

**NEXT SESSION: FINAL AUDIT A3R — PHASE 3 REMEDIATION**

Stop here. No remediation or next audit has started.

## A3R — SQLite Schema Fail-Closed Remediation

Date: 2026-09-27. **A3R COMPLETE. A3-M1 REMEDIATED — INDEPENDENT A3V REQUIRED.**
This section supersedes the unresolved remediation disposition above, not A3's
independent verdict. **PHASE 3 remains FAIL**, pending independent A3V.
A0–A2 remain PASS; A4–A10 remain NOT_AUDITED. A3V was not started.

### Authority, identity and safety

The active state, ledger, document index and original A3 report were read first.
The applicable contract is C4's Validation and explicit recovery, Migration ledger
and rollback, and Backup and publication sections, supplemented by FR-001 and
accepted ADR-014/018. These require rejection of unknown columns, preserve only
the named nullable-pair variants, and validate before readiness/publication.
There is no approved generated-column exception or need to change the stored schema.

- Entry HEAD: `1538aa4274063b416ec50c706261fac1c6b05a46`.
- Previous runtime candidate: `3a4058caca4e6b9b4b900c458a0e98a825d13d44`.
- **New audit-candidate runtime SHA: `b7eecccf7c56613ac7bfc5d6bb78376eef1db48e`.**
  Contains the two storage source changes, synthetic regressions and A3R changelog entry.
- Recorded production source: `8e9018d4b8061cde6006eee47fa4103522f77718`;
  pin: `r-8e9018d4b8061cde-3dac82a792fad576`. Documentary identity only, not a fresh host check.
- The subsequent documentation-only commit records these audit updates separately;
  its identity is available from Git history and the session completion response.
  The runtime candidate is **not deployed**.

All DBs, encrypted artifacts and keys used here were locally generated synthetic
fixtures in temporary directories or memory. No actual DB/backup, repository `.env`,
production host, remote publication, service, systemd configuration, release or
preservation was accessed or changed. Existing unrelated worktree changes were preserved.

### Exact pre-fix causal proof and root cause

Before changing runtime source, an inline process used the real public adapters on
a newly created six-table DB and executed the same A3 statements:

```sql
INSERT INTO users VALUES (10,100,1,1,0,NULL,NULL);
ALTER TABLE users ADD COLUMN unexpected INTEGER
  GENERATED ALWAYS AS (xp) VIRTUAL CHECK (unexpected < 2);
```

SQLite `3.53.1` returned seven columns from `table_info(users)` and eight from
`table_xinfo(users)`; `unexpected` had `hidden=2`. The real observed sequence was:
inspect `valid`, startup accepted, migrated copy `valid`, encrypted backup `valid`,
isolated restore `valid`, unknown column retained, then repository
`add_progress(100,10,1,0,...)` raised `DataIntegrityError`. Source bytes stayed unchanged.
The write attempted XP 1→2 and violated `CHECK (unexpected < 2)`.

`schema.validate` compared the incomplete `table_info` result to the expected
column layout. The constraint was absent from that view; integrity checks passed
because the existing row satisfied it, and the digest projected only known columns.
Startup/open, snapshot/migration, rehearsal, backup source/round-trip and restore
all reuse `checked_validation`; they had no stronger independent column check.
`validate_ledger` independently repeated the same incomplete layout enumeration.
Extension tables already compare exact reviewed `sqlite_master.sql` definitions.

[SQLite's table_xinfo documentation](https://www.sqlite.org/pragma.html#pragma_table_xinfo)
confirms that the extra field distinguishes ordinary (0), hidden virtual-table (1),
virtual generated (2) and stored generated (3) columns; nonzero entries are omitted
by `table_info`. This was also measured locally, not assumed from documentation.

Before the runtime change, the first 43 regression cases produced **24 FAIL / 19 PASS
in 1.81s**. Failures were the six legacy tables and ledger (both generated kinds),
startup and all four recovery/rehearsal operations for users/ledger. The seven
extension tables were already correctly rejected by their DDL gate. After the fix,
the same 43 cases passed in 1.51s; seven additional classification/lifecycle cases
bring final new regression coverage to 50 cases, all passing in the focused suite.

### Implementation and compatibility

`schema.table_columns` is the shared inspector for fixed governed identifiers.
It returns typed `TableColumn` records with all seven `table_xinfo` fields, including
the explicitly named `hidden` classification. Legacy schema and ledger layout
validation reject any nonzero classification and compare the complete layout.
Legacy order/name/type/default/nullability/PK checks retain their prior strictness;
ledger name/type/PK and applied-definition checks are preserved. Extension DDL
checks remain exact and their column traversal now uses the same inspector.

Projection helpers use the complete view. Applied nullable-column checks and
expansion-presence checks explicitly require ordinary (`hidden=0`) columns.
The public migration path still rejects invalid input before invoking any migration;
the private step executor and migration registry were not redesigned.

No migration definition, checksum, schema version, backup envelope or user data
format changed. Current registry maximum remains **5**; `PRAGMA user_version`
remains **0**. Both nullable pairs may independently be wholly absent, giving four
approved combinations; all four pass the new end-to-end positive regressions.
Unknown columns are never dropped, repaired, normalized or used to trigger recovery.

### Boundary and behavioral results

| Boundary | Fresh synthetic evidence |
| --- | --- |
| Canonical inspector | All 14 governed tables reject unknown VIRTUAL and STORED generated columns. Matching expected nullable names/types are also rejected when generated. Real FTS5 `hidden=1` columns remain visible to the inspector; the unsupported virtual table is rejected by the existing schema gate. |
| Startup/open | Users produce `wrong_schema`, ledger produces `invalid_ledger`; `start` raises typed `DataIntegrityError`, closes both lanes, leaves zero admitted workers and denies subsequent XP admission. The real ProcessRuntime does not start the next feature or report ready. Valid schema starts normally. |
| Migration/rehearsal | `migrated_copy` and real `check_copy` reject users/ledger additions before expansion or publication. Source bytes remain identical and no destination appears. Valid variants migrate to version 5 with reconciliation intact. |
| Backup | Source validation rejects malformed users/ledger before replacing even a pre-existing synthetic last-good artifact; temporary candidates are removed. Valid migrated DB backup succeeds through encrypted round-trip validation. |
| Restore | Independently constructed encrypted malformed payloads decrypt and pass the SQL authorizer/SQLite quick check, but schema verification rejects them before publication. Input bytes stay identical. Valid backup restores, passes quick/integrity checks and opens through the application repository. |
| XP behavior | Introducing the exact constraint after valid startup deliberately bypasses only the startup boundary and proves the real repository mutation raises `DataIntegrityError`, rolling back to XP 1. Presenting that schema before startup now rejects it earlier. Canonical/approved variants perform XP 1→2 and preserve 0.25 voice seconds; restored rows match and support another XP update. |

The post-start DDL case is a causal test; continuous monitoring of external live
schema changes is not a new promise or an A3R implementation change.

### Targeted equivalent-call-site review

Search scope: `src/`, `scripts/`, retained `database_manager.py`, and data tests for
`table_info`, `table_xinfo`, column enumeration and expected-column comparisons.

| Site | Classification / disposition |
| --- | --- |
| `schema.validate` legacy layout | Same defect; fixed using complete columns plus explicit hidden classification. |
| `migrations.validate_ledger` layout | Exact equivalent defect; fixed through the same inspector; direct ledger/apply calls reject without mutation. |
| `schema.columns` / `projection` | Incomplete helper, not independent validation; now complete while projection still preserves the known-column contract. |
| Extension metadata traversal | Already protected by exact `sqlite_master.sql`; consolidated enumeration and explicit hidden rejection preserve that strength. |
| Ledger applied-column and `apply_pending` presence checks | Intentionally check ordinary writable expansion columns; use complete metadata and explicitly select `hidden=0`. |
| `execution`, `recovery`, `rehearse_v2_data`, candidate CLI and preparation/recovery consumers | Reuse `checked_validation`/`inspect`; no remaining equivalent independent incomplete inspector. No production operation was invoked. |
| V1 `database_manager._prepare_database_schema` (two `table_info` calls) | Intentionally different retained V1 automatic schema builder, not a canonical Phase 3 compatibility gate. Unchanged; no V1 cleanup or behavioral redesign. |

### Verification receipts

Every command used repository `.venv/Scripts/python.exe`,
`PYTHON_DOTENV_DISABLED=1`, `PYTHONDONTWRITEBYTECODE=1`, and these common arguments:
`-q -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.
Root credential isolation and temporary DB/backup fixtures were reviewed first;
dependent external transports/services are fakes, and Linux/systemd tests remain opt-in.

| Run | Exact result |
| --- | --- |
| `python -m pytest tests/integration/data/` | **177 PASS**, 9.97s (127 existing + 50 new) |
| Dependent/earlier-invariant command below | **80 PASS**, 11.66s; one existing audioop warning |
| `python -m pytest tests/ --collect-only` (once) | **1,135 collected**, 2.28s; previous 1,085 + 50 new |
| `python -m pytest tests/` strict (once) | **1,106 PASS / 2 known FAIL / 27 SKIP**, 82.00s; one existing audioop warning |

The dependent/earlier-invariant command selected exactly:

```text
tests/characterization/test_database_recovery_contracts.py
tests/architecture/test_import_rules.py
tests/integration/engagement/test_compatibility.py
tests/integration/music/test_data.py
tests/integration/watch/test_data.py
tests/integration/operations/test_recovery.py
tests/integration/operations/test_pipeline.py
tests/integration/operations/test_offhost_wiring.py
tests/test_collection_environment.py
tests/test_test_environment.py
tests/unit/platform/test_runtime.py
tests/unit/platform/test_optional_start.py
tests/integration/music/test_cleanup_ownership.py
tests/integration/watch/test_cleanup_ownership.py
```

A0's collection-before-import credential protection passes; its implementation is
unchanged. A2 lifecycle/optional-resource/nested-cleanup protection passes and its
runtime source is unchanged. These are directly relevant checks, not new A0–A2 audits.

Known full-suite failures are unchanged:
`tests/architecture/test_rebuild_documentation.py::test_rebuild_documents_are_partitioned_without_loss`
still allows only the A0 report (**A2-N1 MINOR**), and
`tests/integration/music/test_resources.py::test_pinned_provider_and_runtime_load_without_network`
cannot launch the absent local `deno.exe` (**environment INFO**).
There is **no new unexplained failure**, no RuntimeWarning/unraisable failure and no
claim of a clean whole-suite PASS. The 27 opt-in Linux cases were not run here.
No packages were installed and no full-suite retry loop occurred.

### Disposition, hygiene and rollback

**A3-M1 = REMEDIATED — pending independent A3V. PHASE 3 = FAIL.**
A3-N1 stale product wording and A3-I1 historical empty-Watch evidence limits remain
unchanged in audit history. No Phase 4–10 or Integrated Audit was performed.

Reviewed the complete code/test diff and selected changelog hunk before the runtime
commit; `git diff --check` and `git diff --cached --check` passed. Only that A3R
changelog hunk was staged, leaving the pre-existing Watch acceptance change intact.
Audit-document history is preserved. No actual DB/SQL backup, secret, runtime log,
cache or generated recovery artifact is included. No push, rebase/history rewrite,
deployment, production access or cleanup of unrelated files occurred.

Rollback is a revert of runtime commit `b7eecccf7c56613ac7bfc5d6bb78376eef1db48e`
before any future deployment; it requires no data/schema rollback. Reverting would
reintroduce the known validation blind spot. The documentation commit is independently
revertible and makes no runtime change. No rollback was executed.

**NEXT SESSION: FINAL AUDIT A3V — PHASE 3 INDEPENDENT RE-AUDIT**

Stop. A3V and A4 were not started.
