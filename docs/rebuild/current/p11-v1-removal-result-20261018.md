# P11 local V1 source retirement — 2026-10-18

**Completed locally: 26 original V1 source paths and 19 V1-only test files removed.**
All 45 were tracked, unchanged against local Git after CRLF normalization, checked
again for exact checkout SHA256 immediately before removal, and remain recoverable
from `6ce25d2dfd894ae340b64ebd59823d87463bbed8`. No unique edits were discarded.
This is source cleanup, not a new deployment or a new production health claim.

## Preserved contracts and source boundary

- The actual DB oracle remains the exact Git blob in
  [`compatibility/v1`](../../../compatibility/v1/README.md).
- Nine selected Engagement/Music source files remain there: six exact Git blobs,
  three with only the absolute DB import redirected to the isolated namespace.
  The original/executed hashes and adaptations are in
  [the oracle manifest](../../../compatibility/v1/oracles-manifest.json).
  Namespace scaffolding verifies the manifest and sources before import; LF
  attributes keep the checks stable after Windows checkout.
- Shared fixtures isolate only the optional reference. V2-only exports still
  collect and execute without any V1 module. No runtime source under `src/` changed;
  the architecture test forbids V2 imports of the reference.
- Offline data rehearsal and surviving DB/Engagement/Music/Watch comparison tests
  use explicit reference imports. There is no `sys.modules` alias for the old bot.
- Credential collection canaries now use two synthetic dotenv import styles;
  the actual root credential guard is unchanged. Unsafe controls still fail and
  protected collection plus direct-read rejection still pass.
- New stopped-release source exports accept the explicit reference namespace and
  reject removed root V1 paths. This only affects future exports; existing frozen
  archives, source manifests and installed releases were not rewritten.

## Exact removal and retirement evidence

[The recovery/retirement manifest](p11-v1-retirement-manifest-20261018.json) records
all 45 paths, original checkout and Git blob SHA256 values, source commit,
127 retired test function names in the 19 whole files, and 11 retired V1-only
cases from mixed characterization files. Counts are function definitions, not
parametrized pytest case counts. Nine retained V2 CORRECT function ASTs in the
three mixed files were compared with their pre-batch copies and are unchanged.
The V1 missing-token startup assertion inside the old credential canary was also
retired with that startup path; credential-boundary assertions remain.

Original source paths removed:

- `main_bot.py`
- `database_manager.py`
- `cogs/application_commands.py`
- `cogs/birthday/birthday_core.py`
- `cogs/leveling/leveling_core.py`
- `cogs/logging/log_agent.py`
- `cogs/logging/__init__.py`
- `cogs/music/music_agent.py`
- `cogs/music/music_core.py`
- `cogs/music/music_playback.py`
- `cogs/music/music_session_restorer.py`
- `cogs/music/music_state_store.py`
- `cogs/music/music_ui.py`
- `cogs/music/music_utils.py`
- `cogs/music/__init__.py`
- `cogs/summary/summarizer_agent.py`
- `cogs/summary/summary_listeners.py`
- `cogs/summary/__init__.py`
- `cogs/watch_together/watch_agent.py`
- `cogs/watch_together/watch_server.py`
- `cogs/watch_together/__init__.py`
- `cogs/watch_together/templates/player.html`
- `scripts/auto_backup.sh`
- `scripts/auto_update.sh`
- `scripts/install_pot_provider.sh`
- `envtemplate.txt`

V1-only test files removed:

- `tests/test_application_commands.py`
- `tests/test_auto_backup_script.py`
- `tests/test_auto_update_script.py`
- `tests/test_database_manager.py`
- `tests/test_leveling_core.py`
- `tests/test_log_agent.py`
- `tests/test_main_bot.py`
- `tests/test_music_agent.py`
- `tests/test_music_core.py`
- `tests/test_music_playback.py`
- `tests/test_music_state_store.py`
- `tests/test_music_ui.py`
- `tests/test_music_utils.py`
- `tests/test_pot_provider_script.py`
- `tests/test_summarizer_agent.py`
- `tests/test_summary_listeners.py`
- `tests/test_system_integrity.py`
- `tests/test_watch_together.py`
- `tests/characterization/test_discord_contracts.py`

| Retired coverage family | Current retained coverage and this run's limit |
| --- | --- |
| DB schema/readers/backup | Frozen actual DB plus data integration/rehearsal; DB characterization executed now. The prior 45-case reference-transition run is separate evidence, not counted again. |
| Engagement command/formula | Actual Birthday/Leveling comparisons and V2 policy/Discord/compatibility tests executed. |
| Music behavior/UI/state | Surviving Music characterization, favorites dispatch and V2-to-old snapshot reader executed; other V2 Music tests collected but not all executed. |
| Summary and Watch V1-only cases | Existing V2 Summary Discord and Watch Discord/transport/lifecycle tests executed; mixed V2 CORRECT tests preserved. This is not a claim of one-for-one equivalence for every retired test. |
| Old startup/logging/update/backup/install scripts | Their V1-specific tests retired with those entrypoints. Current V2 platform runtime/telemetry and operations suites retained and collected; no broad execution claim. |

## Actual validation

- **172 passed**, one existing `audioop` deprecation warning, pytest 11.90s;
  bounded runner 12.594s, exit 0, direct child reaped.
- **1897 tests collected**, one identical warning, pytest 2.12s;
  bounded runner 2.828s, exit 0. Collection is not full-suite execution.
- Exact deleted-path set equals the approved 26 + 19 manifest; every Git recovery
  blob SHA256 matches. `src/` diff and index are empty.
- `git diff --check` and `git diff --cached --check` passed. The latter checks an
  empty index and is not a staged-content review.
- No package installation, dependency upgrade, commit, push, remote query,
  credential access, canonical DB read/write, production login or restart occurred.

Local raw receipts and exact selected test identities are under
`scratch/p11-v1-removal-20261018-01/`: `affected-result.json`,
`affected-output.txt`, `collection-result.json`, `collection-output.txt`,
`exact-removal-manifest.json`, `retired-mixed-cases.json`, and
`final-preservation.json`. Scratch is not proposed for publication.
Async tests used the normally approved local execution route because an earlier
sandbox run had stalled in Windows asyncio socketpair creation; no security
setting or access route changed. No full suite, Pi campaign or deployment was run.

## Current documentation and intentional retention

README now describes local V2 development/testing and links the reviewed release
runbooks instead of `python main_bot.py` and the old `.env` template. The operations
guide marks its old V1 setup/cron commands as historical, while retaining their
record. Product contracts and changelog identify this source boundary.
Existing historical reports and original reference receipts remain available.
One baseline document's removed `main_bot.py` link now points to the exact Git
recovery manifest; its historical behavior description and line references remain.
Actual DB/SQL backups, secrets, ignored caches, Git history, rollback assets,
unrelated inherited dirty files and installed release trees are untouched.

No fresh Pi observation was made. Last known active release remains
`r-6ce25d2dfd894ae3-bd1ffa96253a4d84`; rollback is
`r-8e9018d4b8061cde-3dac82a792fad576`. Installed cleanup remains **9/12 deleted,
3 retained plus 4 protected** at the October 18 07:37 UTC receipt.
The remaining three remote releases and five exact audit fields are a separate
bounded follow-up; this local work neither resolves nor reopens that operation.

## Atomic commit and publication preparation (not executed)

1. `refactor: retire V1 runtime and isolate compatibility references`:
   include the exact 45 deletions, explicit compatibility sources/manifests,
   `.gitattributes`, rehearsal and test consumer edits, source-export allowlist
   with its tests, and only the README/operations/product-spec/changelog hunks
   required by removal, plus the single baseline source-link repair. Include the recovery manifest and this result report.
   These belong together: separating deletion from surviving oracle consumers
   would break collection. The previous local DB-reference steps are dependencies
   of this same coherent change, not unrelated edits to omit accidentally.
2. `docs: reconcile P11 cleanup checkpoints`: stage only the matching compact-state,
   active-state, ledger, plan and index additions, together with prior local P11
   evidence if it has not yet been published. Separate unrelated operational
   cleanup/formal-release documentation and tools by their own responsibility.
3. Before an authorized commit, review exact staged paths and hunks, verify no
   data/secrets/cache or unrelated inherited work, run cached diff checks, and
   record focused results plus the full-suite-not-run limitation. The ordinary
   full-source commit/review gate is still documented; this request only authorized
   focused execution and collection, so it was not performed or waived here.
4. Only after publication is authorized: inspect current remote/base divergence,
   make atomic commits, push without force and create/update a PR with purpose,
   compatibility, actual validation, rollback and checklist. No remote divergence,
   authentication or merge-conflict status was guessed in this local task.

`publication-scope.json` in the scratch receipt directory enumerates the proposed
code/required-document paths and hunk-only shared documents. Nothing is staged,
committed or pushed; GitHub therefore does not yet contain this cleanup. There is
no pending authentication request or denied action. Publication awaits authorization,
staged review and the applicable source gate, not another deployment audit.

Rollback: recover each removed source/test from the recorded local commit into a
separate temporary review directory first, compare it, then restore only those
paths with approval. Revert the coupled reference/import/test cleanup together if
rolling back the entire source boundary. Never replace unrelated dirty files or
production data, and do not use history rewrite or a working-tree hard reset.
