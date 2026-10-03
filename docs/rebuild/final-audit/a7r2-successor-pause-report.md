# A7R2 successor pause-state lifetime — scoped remediation PASS

2026-10-03. **Phase 7 remains FAIL. A7-M1 stays independently CLOSED; A7-M2 is
remediated locally, OPEN pending independent verification.** No A7V2/A8/Phase 11.

## Identity and authority

- Entry HEAD `22736424a32991d480ca3518085e948292eb40db`, branch `codex/rebuild-v2`.
  Implementation **`b914200e20905179f16a7f98ffca8d841db07746`**; subsequent evidence
  commit/final HEAD is recorded in the handoff. M1 fix remains `12a42ef9168da0540825fa1cb12f2c189da95411`.
- [Entry inventory](a7r2-entry-inventory.json): 11 modified / 59 untracked, 70 content
  hashes, empty index. Root AGENTS applies; `.agents/skills` and nested src/tests/docs
  AGENTS are absent. Entry branch/HEAD/inventory agree with the delegation.
- Read current active-state/ledger/document index, C10/C11/C12, canonical Phase 7
  report, A7V1 report/exact probe/XML, original A7 probe and A7R1 report/regressions;
  checked B08 BR-005, B12 FR-015 and current product retry semantics. Historical
  completion does not supersede A7V1 FAIL. No new contract contradiction found.
- Existing C10 requires 3s/8s retries and third-failure next song; C11 keeps pause,
  position and receipt identity within the same logical session. The explicit A7R2
  authorization covers restoring this boundary, with no new product decision.
- Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
  `r-8e9018d4b8061cde-3dac82a792fad576` remain distinct, unchanged records. No host access.

## Root cause and minimal repair

`disconnected` correctly retains music pause intent in `_resume_paused`, including
while TTS owns audio. The first two failed acquisitions/starts retry the same session.
On the third failure `_failed` calls `_advance`, which retires current/session/attempt,
resets position/failure count and creates a successor session, but left the old pause
flag alive. `started` then consumed that flag and paused the new song. With no queued
successor, the idle projection also retained pause and a later enqueue inherited it.

The only runtime change is `_resume_paused = False` plus its comment in `_advance`.
Reviewed all callers: enqueue from no current, queued connect, normal completion/loops,
manual skip, post-announcement advance and recovery exhaustion all retire or initialize
a logical session. `_prepare`, first/second retries and same-session TTS/reconnect do
not pass through that reset. Existing skip/leave clearing is retained, not refactored.
M1's disconnect assignment is unchanged. No new owner, task, timer, state field, lock,
UI behavior, dependency, retry policy, schema or snapshot format is introduced.

## Exact execution and evidence

All commands below used the existing Windows venv, repository cwd, and:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONIOENCODING='utf-8'
```

1. Original A7V1 M2 probe, unchanged, before the runtime edit:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml docs/rebuild/final-audit/a7v1-retry-exhaustion-probe.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r2-original-red-results.xml
```

**1 PASS / 1 FAIL / 0 SKIP / 0 XFAIL**, 0.40s, exit 1, session 94178.
Observed successor `('2', 'paused', True, False)` instead of playing/unpaused/audible.
[RED receipt](a7r2-original-red-results.xml). Original M2 SHA-256 before/after:
`b675a696316efc046131cba4d7778b43dc1f8c22aaac25823cc9e8ad25c9a24a`.

2. New 30-case regression, still before the runtime edit:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml tests/integration/music/test_pause_session_lifetime.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r2-regression-red-results.xml
```

Final valid RED: **22 PASS / 8 FAIL / 0 SKIP / 0 XFAIL**, 0.56s, exit 1, session 87308.
All eight failures are paused exhausted recovery: ordinary/TTS, acquire/start failure,
queued/later successor. [Receipt](a7r2-regression-red-results.xml).
The exact final test file was unchanged from this RED through all GREEN runs (SHA-256
`ef33b444c1c5e4950bd060a10fac1a462d1fd43ee9c192fcb43886bf7938c20e`).

Initial harness execution, session 23280, had **0 PASS / 30 synchronization FAIL**,
0.63s, before the runtime edit. Its [original receipt](a7r2-harness-initial-results.xml)
is separate. Twenty-four cases observed the preceding retry before the newly awakened
failure arrived; six captured revision before the successful start-result command
finished. Correction added waits for the expected failure count and start-job completion.
No assertion, fixture, product input or failure injection was weakened. The initial
command was the same as step 2; its output was renamed to preserve both executions.

3. After the repair: unchanged M2/M1 probes, new regression and M1 regression:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml docs/rebuild/final-audit/a7v1-retry-exhaustion-probe.py docs/rebuild/final-audit/a7-paused-disconnect-probe.py tests/integration/music/test_pause_session_lifetime.py tests/integration/music/test_tts_reconnect.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r2-focused-green-results.xml
```

**54 PASS / 0 FAIL / 0 SKIP / 0 XFAIL**, 0.59s, exit 0, session 88649:
M2 2, M1 2, new regression 30, M1 regression 20. [GREEN receipt](a7r2-focused-green-results.xml).
Thus unchanged M2 is **1/1 RED → 2/0 GREEN**, new regression **22/8 → 30/0**.
M1 original SHA-256 remains `5f81fc6ae055f27486a5d89d4fee6fe2729e1b9a2aeae0d0e08150df7b7ddba2`.

4. Affected contracts, including prior Music lifecycle/cleanup fixes:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml tests/integration/music/ tests/characterization/test_music_contracts.py tests/architecture/test_import_rules.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r2-regression-results.xml
```

**229 PASS / 1 known FAIL / 0 SKIP / 0 XFAIL**, 9.77s, exit 1, session 50840.
[Receipt](a7r2-regression-results.xml). Failure is the existing offline provider version
test trying to launch missing `.venv/Scripts/deno.exe`; no install/skip/xfail workaround.
Distinct affected union with the four original probe cases: **233 PASS / 1 FAIL**.

5. Full standard suite after isolation review, begun 11:59:55 KST:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml tests/ -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r2-full-results.xml
```

**1,389 PASS / 2 known FAIL / 27 SKIP / 0 XFAIL**, 100.52s, exit 1, session 59133.
[Full receipt](a7r2-full-results.xml). Second failure is the known stale final-audit
document inventory expectation (`test_rebuild_documents_are_partitioned_without_loss`).
All skips are existing opt-in Linux/systemd cases, not new exclusions. Audioop deprecation
remains. No clean full-suite claim. Final distinct current-code union, removing overlap
and adding the four original probe cases: **1,393 PASS / 2 FAIL / 27 SKIP / 0 XFAIL**.
RED and initial harness executions are not extra current passes or independent audit gates.
XML trace trailing whitespace is normalized only for Git; outcomes are unchanged.

## Coverage and limits

- New 24-case matrix: playing/paused × ordinary/TTS disconnect × acquisition/audio-start
  failures × queued successor/later enqueue/same-session recovery after two failures.
  Checks exact 3s/8s timing, 17s retained position vs zero successor position, session/queue,
  paused/audible effects, start receipt arguments, repeated stale success/failure callbacks,
  a subsequent announcement, close and supervisor teardown. Six more cases cover normal
  completion after reconnect/resume in NONE/SONG/QUEUE with fresh logical sessions.
- Unchanged M2 and M1 probes each include independently playing second-guild audio/session
  controls. M1's 20 regressions retain preparation/TTS/cancellation/stale callback and
  skip/leave/expiry/close coverage. Existing affected tests cover snapshots/old reader,
  receipt dedupe, queue/autoplay, actual temporary SQLite, cache/process failure and cleanup.
- Root credential guard disables/rejects dotenv reads; fixtures isolate DB/backup/cache.
  Full suite inspection confirmed temporary data, mocked external clients/commands,
  disposable local Git repositories and Linux/systemd opt-in guards. Local Python/Node
  children are synthetic; no live providers, Discord, YouTube, paid services or production.
- No WSL needed for this platform-independent state lifetime fix. No fresh Linux/Pi,
  real audible Voice, deployment, long-soak or complete independent Phase 7 gate claim.
  Known inventory/A2-N1, Deno, audioop, A3-N1/A3-I1 limits remain. A0–A6 retain independent PASS.

## Preservation, rollback and shutdown checkpoint

Only actor/test/scoped CHANGELOG form the implementation commit. Evidence commit owns
this report, inventory, six XML receipts, ownership receipt, active-state AV append and
Phase 7 ledger remediation-cell update. Original A7/A7R1/A7V1 files and untracked document
index are unchanged. [Ownership receipt](a7r2-ownership-receipt.json) records exact byte
reconstruction for three mixed documents; the other 67 inherited files are byte-identical.
Scoped staging uses HEAD plus owned deltas, never the whole mixed working files. Final
residual status must be the original 11 modified / 59 untracked with empty index.

Rollback: revert the scoped implementation commit, preserving inherited CHANGELOG work;
reverse the separate evidence commit only to undo its routing. No DB/data/production
rollback, history rewrite, remote push, dependency or service/routing/security change.

All six foreground pytest executions exited. At 12:02 KST no python/pythonw/pytest/ffmpeg
process remained; pre-existing Node PIDs 4644/12284/28216 (11:13:43 KST) were untouched.
No task-owned persistent server/browser/WSL was started. Final commit, preservation and
process checks are reported in the handoff, before the 12:35 test-start and 12:45 cleanup
cutoffs. No shutdown is issued. Once that handoff is saved there is no owned process or
pending write requiring the PC to stay on.

**STOP A7R2 for supervisor review.** Next is separately authorized independent verification
of M1/M2 and remaining Phase 7 gates. M2 is not independently closed here; Phase 7 stays
FAIL. No A7V2/A8/Integrated Audit/Phase 11. Friend activation HELD; MyFood untouched.
