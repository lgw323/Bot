# A4R2 - queued voice failure and shutdown remediation

2026-10-02. **A4R2 PASS, local remediation only. PHASE 4 remains FAIL pending fresh A4V2.**
A4-M1 remains independently CLOSED in its replacement-READY scope. A4-M2 is remediated,
not independently CLOSED. This is exactly one authorized microphase; no independent
audit, A5, Integrated Audit, deployment or cleanup was performed.

## Authority and Git ownership

- Entry candidate: `f0a4a07817a27b5c5327a2ba43679d314c98f822`.
- Final HEAD: `7ead8a2fae5501f384c26e6d894e5b6ca9a906e9`, branch `codex/rebuild-v2`.
  Local commit: `fix: drain voice observation outcomes before shutdown flush`.
- Read compact active-state, Phase 4 ledger and document index first, followed by
  [A4V1 exact reproduction](a4v1-phase-4-verification-report.md),
  [A4R1 report](a4r1-voice-reconnect-report.md), B20 Phase 4, C6 voice lifecycle,
  relevant accepted ADRs (especially ADR-019), current code/tests and root AGENTS.md.
  The latest explicit delegation authorizes only A4-M2 remediation and a scoped local
  code/test commit. No nested instructions or applicable local skill was found.
- [Entry inventory](a4r2-entry-inventory.json): **11 modified tracked / 65 untracked,
  empty index**; all 76 inherited file hashes matched before documentation edits.
  No active-writer or candidate drift was observed. `rg` is unavailable; existing
  PowerShell/Git and `.venv` Python were used. No subagents or package installs.
- Commit contains exactly three files, **+296/-11**:
  `src/discordbot/engagement/application/service.py`,
  `tests/integration/engagement/test_voice_reconnect.py`, and new
  `tests/integration/engagement/test_voice_shutdown.py`.
  Reviewed staged diff, tested-worktree equality and `git diff --cached --check`.
  Initial `.git/index.lock` sandbox denial was resolved by narrowly authorized
  staging/commit escalation; no automatic approval rejection or remote action.
- Uncommitted owned documentation: this report, entry inventory, active-state AG,
  Phase 4 ledger row, appended index section, and A4R2 changelog entry. Mixed inherited
  documentation is deliberately excluded from the code/test commit. Final tree:
  **11 modified tracked / 67 untracked, empty index**. Other inherited bytes preserved.

## Root cause and bounded change

Previously stop closed admission and immediately captured `_voice_faulted=False` in
the queued flush. An earlier admitted transaction could subsequently fail and roll
back, then set the service flag, while flush still used the stale boolean. SQL queue
ordering did not order the service coroutine's failure handling. The exact result was
700 seconds / 55 voice XP, instead of persisted 70 seconds / 5 XP.

The service now counts admitted voice observations (events and READY reconciliation)
until their success/failure/cancellation handling finishes. Stop closes admission,
captures the stop tick and existing DB request deadline, then awaits the drain before
reading the failure policy and submitting the existing flush. Successful observations
retain normal accrual to the captured stop tick; drain latency earns no extra time.
The counter handles multiple concurrent observations; one completion cannot hide
another pending failure. No new voice queue, task, global lock or storage API is added.
Text/read operations remain independent while voice work is pending.

Drain uses the existing configured request budget. Timeout raises typed ShutdownError
without flushing or clearing persisted state; cancellation also leaves ownership and
metadata intact. A later explicit stop can retry. Cancelled DB work may still run on
the worker, but the existing serialized writer orders its rollback before flush.
Flush transaction failure remains atomic/retryable. No retry loop was introduced.

Unchanged: XP formula and short-stay/fractional policy, SQLite schema/migrations,
backup/state formats, command text/permissions/visibility, Gateway stream/replay
semantics, guild/user keys and friend configuration. No historical XP repair.
This does not resolve or claim accuracy for active RESUME/disconnect timing.

## RED to PASS evidence

All execution was local Windows with temporary synthetic SQLite fixtures, fake clocks,
offline Gateway objects, bounded barriers and task/DB teardown. Root credential
barrier and temporary legacy DB/backup fixtures were reviewed. No live DB, Discord,
Gemini, YouTube, Pi or WSL execution was needed.

1. **Unmodified A4V1 probe, before source changes:** source extracted from the report
   into `%TEMP%/discordbot-a4r2-probe/test_a4v1_independent.py`.
   Windows file SHA-256 `2ecb25bc68a01dd726167e6d6cfb73e517e215ed63df5f87fe70705b7924df56`;
   LF-normalized source SHA-256 `c1666496403b5ab0b6624ff46924efe68cfcec8ecb0d40a8d41fc0f0fba3e139`.
   **4 PASS / 1 FAIL / 0 SKIP**, exit 1, 0.74s.
   Exact failing JSON: `faulted=true, seconds=700, expected=70, xp=55, expected_xp=5`.
2. New initial repository regressions before source changes:
   **2 PASS / 5 FAIL / 0 SKIP**, exit 1, 0.88s. Both event/READY failure and cancellation,
   plus overlapping observation outcomes, reproduced `700 != 70`.
3. After the fix, initial failure/reconnect selection: **26 PASS**, 3.27s.
   Final new regression module: **11 PASS / 0 FAIL / 0 SKIP**, 1.42s.
   Covers queued event/READY failure, cancellation and success; fixed stop tick;
   late admission rejection; all pending outcomes; running transaction cancellation;
   timeout/cancelled drain ownership and retry; flush rollback/retry and idempotence.
4. **A4V1-derived probe with synchronization adjusted only:**
   `%TEMP%/discordbot-a4r2-probe/test_a4r2_synchronized.py`, SHA-256
   `d32c68b1c2327cc66fc022a24dc2379b0ffe44053e16da2cdfff6fa97980d441`.
   **5 PASS / 0 FAIL / 0 SKIP**, exit 0, 0.69s. Race now **70s/5 XP**;
   original M1 shutdown/rejoin **70s/5 XP and 131s/10 XP**; pending READY **70s/5 XP**;
   continuity/replay/same-person two-guild result **[66, 0] seconds**.
   This is remediation evidence, not a new independent audit. The unmodified original
   probe is preserved, and no post-fix unmodified-probe PASS is claimed.
5. Final focused/dependent selection below: **131 PASS / 0 FAIL / 0 SKIP**, exit 0,
   10.04s, one existing audioop deprecation warning. Includes 94 pre-existing focused
   cases, 11 new regressions and 26 import/lifecycle dependency cases. Additional
   dependency selection is justified by the application-layer drain and aggregate
   cleanup ownership. No broad/full-suite rerun was justified by this bounded fix.

Commands (existing `.venv`, no install):

```powershell
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4r2-probe\test_a4v1_independent.py" --confcutdir="$env:TEMP\discordbot-a4r2-probe" -q -s --tb=short -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest tests/integration/engagement/test_voice_shutdown.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4r2-probe\test_a4r2_synchronized.py" --confcutdir="$env:TEMP\discordbot-a4r2-probe" -q -s --tb=short -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py tests/architecture/test_import_rules.py tests/integration/watch/test_cleanup_ownership.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

Synchronization delta in the derived probe, immediately after scheduling stop:

```diff
-                await asyncio.wait_for(queued.get(),2)
+                await asyncio.sleep(0)
+                assert not app._accepting
+                assert not tasks[-1].done()
+                assert queued.empty()
```

The old harness demanded a second DB write while the first observation was unresolved.
The corrected service intentionally defers flush admission. One event-loop yield runs
stop through admission closure to its drain wait; new assertions prove it waits without
queuing flush. Barrier, injected rollback, observations and exact seconds/XP assertions
are retained. The existing successful queued-reconciliation test uses the same stronger
ordering assertions; its 70/131-second expectations are unchanged. No skips or weakened
product assertions were introduced. Selections overlap; do not sum these runs.

No clean full-suite claim. Historical A3V3 1253 PASS / 2 known FAIL / 27 SKIP was not
rerun. A2-N1 inventory and missing Deno failures, audioop, A3-N1 MINOR and A3-I1 INFO
remain disclosed, unchanged, and outside this fix. A0-A3 prior PASS statuses retained.

## Safety, rollback and next gate

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`, remains distinct and untouched. No production
access, credential/real-data inspection, deployment/restart, restore/old snapshot,
DB mutation, V1/concurrent production writers, systemd/Cloudflare work or cleanup.
Friend rollout remains HELD; IDs/settings and separate MyFood work are untouched.
Conditional deployment approval requires a passing final Integrated Audit; that
condition is unmet and authorizes no deployment in A4R2.

Rollback is a reviewed normal revert of `7ead8a2fae5501f384c26e6d894e5b6ca9a906e9`;
no schema or data rollback. Remove only named A4R2 documentation additions and restore
the prior Phase 4 row if needed; never reset mixed files, bulk-stage or rewrite history.

**No A4R2 implementation blocker remains. Phase 4 is still FAIL.** Recommend a separate
fresh A4V2 of this exact candidate/worktree: independently challenge queued failure and
cancellation propagation, multiple pending observations, stop-time capture, timeout/
flush ownership and retries; retain M1, replay/idempotence and same-user guild separation;
complete the previously unverified active RESUME/disconnect timing gate against C6/ADR.
Any broader policy/design issue must return to the parent, not expand remediation.
Only independent A4V2 may close A4-M2 and determine Phase 4 status. Actual Gateway/Pi
timing remains unverified. **STOP after A4R2; no A4V2/A5 or automatic expansion.**
