# A4R4 - cancelled voice shutdown retry remediation

2026-10-02. **PASS for local remediation; PHASE 4 remains FAIL pending fresh
independent A4V4.** M1/M2/M3 remain independently CLOSED in their established
scopes. M4 is remediated locally, not independently CLOSED. The resumed overnight
instruction authorizes only A4R4 here; parent review and A4V4 remain separate tasks.

## Authority and ownership

Read active-state AJ, Phase 4 ledger and document index first; then the committed
A4V3 report/exact reproducer, original B20 Phase 4, C1 F030/FR-032, C6 voice lifecycle,
ADR-013/015/017/018/019, original Phase 4 report, A4R3 evidence and current service,
SQLite owner, resource lifecycle and tests. Root AGENTS.md applies; no nested scoped
AGENTS or applicable local skill. No subagent or independent audit was started.

- Entry branch `codex/rebuild-v2`, HEAD `6257337de8e2646941be8be4f6ab226c72a17114`.
- [Entry inventory](a4r4-entry-inventory.json): 11 modified / 59 untracked paths,
  empty index, all 70 file hashes recorded and verified before documentation edits.
- Runtime/test/changelog commit: `c6da7eba800de9816f0c9b7ffb73ca4599f5e3f6`.
  Three files, +237/-1; one service scalar, bounded stop/start changes, 22 regressions
  and only the A4R4 changelog entry. No SQL/schema/formula/adapter change.
- This report/inventory, active-state AK and only the Phase 4 ledger row are a
  separate local evidence commit. Its SHA is the descendant HEAD in Git history.
  The mixed untracked document index receives an A4R4 link but stays uncommitted.

## Cause and common lifecycle invariant

The existing `stop()` closes admission before draining observations, but its cutoff
was a local variable recomputed on every invocation. After RESUMED, the effective
clock runs again. Cancelling the stop waiter leaves admission closed and admitted
observations alive; it does not itself fault their successful outcomes. A later
explicit stop therefore extrapolated 600 seconds during which new observations
were prohibited. Flush retry after transaction rollback had the same moving cutoff.
A muted row or `observed_only=True` hid the accounting error in older retry tests.

This fourth lifecycle finding was assessed against the shared invariant, rather
than adding a RESUMED-specific branch:

**Only admitted, ordered observations may extend trusted voice time. Closing
admission fixes one effective cutoff for all termination attempts in that lifecycle;
completion/cancellation of a waiter cannot create elapsed time or change ownership.**

| Boundary | Owner and retained invariant |
| --- | --- |
| Event or READY admission | Capture effective event tick before await; pending work owns its outcome until service handling completes. |
| Transport disconnect / resume (M3) | Retain first observed monotonic disconnect tick and cumulative excluded offset; frozen replay tick resumes only after RESUMED/READY. |
| Replacement stream (M1) | Retain current stream and reconcile prior-stream persisted duration; stop cannot extrapolate stale-stream membership. |
| Observation failure/cancellation (M2) | Drain all admitted outcomes before reading the fault flag; uncertainty allows persisted observed duration only. |
| Stop / stop retry (M4) | Close admission and retain the first already-adjusted effective tick before await; every drain/flush retry uses that tick. |
| Flush commit / lost acknowledgement | SQLite transaction owns credit and epoch deletion; retry remains idempotent whether the first transaction rolled back or committed. |

`_voice_stop_tick` stores the *effective* tick, not a raw wall/monotonic value that
would need the offline offset applied a second time. Admission stays closed after
cancel, timeout or flush failure; late event/READY/disconnect/resume callbacks cannot
mutate stream/offsets. Each retry still gets a fresh bounded DatabaseRequest. The
fault flag is intentionally read after drain, not frozen when stop begins. No new
background task, shielding, automatic retry, queue, per-user state or lifecycle
manager is introduced. Successful `start()` clears the cutoff after begin_epoch,
so a completed stop followed by another successful start does not inherit an old
cutoff. Concurrent start during an incomplete stop is not a newly supported policy.

This repair needs no new product choice or broader architecture rewrite. The
service retains terminal accounting data while the existing SQLite writer owns
settlement. The current EngagementResource `_stopping` guard remains unchanged:
automatic retry and any actual production occurrence were **not established**.
That limitation must not be confused with the explicitly exercised service retry.

## Unchanged RED and fresh verification

Only synthetic local data: existing Windows .venv, root credential/dotenv barrier,
reviewed temporary DB/bootstrap fixtures, fake clocks/IDs and offline fake/SDK Bot.
No Discord login, network, real DB/SQL backup or Pi access. Workers/tasks are released
and reaped by fixtures/finally blocks; strict runtime/unraisable warning checks apply
to the final selection. No dependency installation or WSL use was needed.

The committed A4V2 and A4V3 Python blocks were extracted unchanged from entry HEAD
into ignored `scratch/a4r4/`. Normalized UTF-8/LF SHA-256:

- A4V2 `test_a4v2_exact.py`:
  `458ef4d61918962dd1c8dc83c16780034ed2e9b99aadb4e6d68f014945df2a83`.
- A4V3 `test_a4v3_independent.py`:
  `86fb5da03fce7ba8d8aa64d9a9685c74b85fd6fe9793d5d657d49fb0ae32ae08`.

Before any runtime edit:

```text
.venv/Scripts/python.exe -m pytest -c pyproject.toml scratch/a4r4/test_a4v3_independent.py -q -s -k cancelled_stop_retry_keeps_original_admission_boundary --tb=short
{"case": "cancelled-stop-retry", "resumed": false, "seconds": 100, "expected": 100, "xp": 5, "expected_xp": 5}
{"case": "cancelled-stop-retry", "resumed": true, "seconds": 761, "expected": 161, "xp": 60, "expected_xp": 10}
E   assert 761 == 161
1 failed, 1 passed, 12 deselected, 1 warning in 0.73s
```

This is the original test/assertion/fixture, not a rewritten failing scenario.

| Run | Actual result |
| --- | --- |
| First 21 new regressions, before runtime edit | 6 PASS / 15 FAIL / 0 SKIP, 3.06s; connected/resumed repeated drain and interrupted flush retry moved cutoff. |
| First repair, new 21 plus unchanged A4V3 14 | 35 PASS / 0 FAIL / 0 SKIP, 5.12s. |
| Expanded selection with successful restart case and deadline assertion, original A4V2 harness | 168 PASS / 4 FAIL / 0 SKIP, 19.40s; three clock-resolution assumptions and one superseded synchronization hook, explained below. |
| Final focused selection | **172 PASS / 0 FAIL / 0 SKIP**, 17.49s; audioop deprecation warning only. |

Final command:

```text
.venv/Scripts/python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py scratch/a4r4/test_a4v2_drain_barrier.py scratch/a4r4/test_a4v3_independent.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
172 passed, 1 warning in 17.49s
```

Final selection: 120 existing focused cases + 22 new regressions + 16 adapted A4V2
cases + 14 unchanged A4V3 cases. Earlier runs overlap and are not added to this count.
The unchanged original M4 case now stores **161s / 10 XP**; disconnected control
remains **100s / 5 XP**. The original M3 paths and M1/M2 cases pass within this scope.

New coverage explicitly asserts two cancelled/timed-out drains; immutable event and
stop timestamps through connected/resumed/disconnected paths; pending observation
success/failure/cancellation; denied late admissions; same user in two guilds
(success totals 161/151 or 100/90, uncertain totals 70/60); real flush rollback and
in-flight cancellation; cancellation after committed credit but before acknowledgement;
repeated idempotent stop; fresh request deadlines; and successful stop/start accounting.

### Disclosed harness corrections, no weakened assertions

The added strict deadline ordering assertion initially assumed Windows monotonic
clock resolution advanced between adjacent requests. It produced equal deadlines.
It remains strict: successive retries now receive explicit valid 6s/7s budgets,
while the first has 5s. This proves newly constructed deadlines deterministically
without sleeps or altering the database deadline implementation.

The original A4V2 `test_two_outcomes_and_concurrent_stops` waits for a fresh clock
read on each stop, including its second concurrent stop. Retaining a cutoff removes
that second clock read, so the unchanged harness times out. That original-source
failure is preserved and is **not** claimed as an unchanged 16-case PASS. A separate
copy replaces only `stop_barrier` with actual drain-entry synchronization. All test
bodies, expected totals, failure assertions and time limits remain unchanged; the
replacement additionally cancels/reaps its own task if its synchronization fails.
A4V3 remains byte-identical and imports its original A4V2 helpers.

To recreate `test_a4v2_drain_barrier.py`, replace only the original `stop_barrier`
function (through the next decorator) with:

```python
async def stop_barrier(app, clock):
    # Observe the drain itself; retries intentionally do not sample a new tick.
    reached = asyncio.Event()
    original_wait = app._voice_drained.wait
    async def wait():
        reached.set()
        return await original_wait()
    app._voice_drained.wait = wait
    task = asyncio.create_task(app.stop())
    try:
        await asyncio.wait_for(reached.wait(), 2)
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
    finally:
        app._voice_drained.wait = original_wait
    assert not app._accepting
    return task
```

Adapted normalized source SHA-256:
`e7f7f7445e5c791d0d504cf6ec7d358849168d9334e0b08718e204c0d1294a1b`.
No production code was made to sample a new clock merely to satisfy this old hook.

No broader/full-suite run was justified for this service-only repair. Known
architecture inventory and Deno failures remain unresolved; audioop remains a
DeprecationWarning. A3-N1 connection-description MINOR and A3-I1 historical Watch
INFO remain unchanged. No clean full-suite, fresh independent audit, live Gateway
or host-timing PASS is claimed.

## Preservation, rollback and next boundary

Exact unrelated inherited paths/statuses/hashes are listed in the entry inventory.
The 11 modified paths are CHANGELOG.md, README.md, docs/product-spec.md,
docs/rebuild/README.md, docs/rebuild/current/current-plan.md, the active-state and
ledger, docs/rebuild/final-audit/a3-phase-3-report.md,
docs/rebuild/phase-10-full-sweep-report.md,
docs/rebuild/phases/phase-10/phase-10-report.md and tests/browser/watch_fixture.py.
The 59 untracked paths comprise the mixed document index, Phase 10B authority/evidence,
A0/A1/A2 reports, handoff ZIP/export tree, server-invite guide and two browser scripts;
none is bulk-staged. Only A4R4 deltas in shared authority/changelog are staged against
HEAD. The mixed index's A4R4 navigation addition stays uncommitted with its prior text.

Expected/final residual ownership is **11 modified / 59 untracked, empty index**.
Inherited content is verified byte-for-byte after removing only the exact A4R4
additions/replacement row. Staged source equals tested source; staged diffs and
`git diff --cached --check` are reviewed before both commits. Initial sandbox
index-lock denial was resolved by scoped authorized escalation; no auto-review
rejection. No reset, bulk-stage, inherited-file overwrite, deletion or remote push.

Rollback: reviewed ordinary revert of the implementation commit; the evidence commit
is separately revertible. Preserve mixed worktree changes; no schema/data rollback.
Production remains separately recorded at source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`. No production/Pi access, deployment/restart,
DB writes/historical restore, V1/concurrent writers, systemd/Cloudflare changes or
release/history cleanup. Friend-server activation is not authorized. My Food remains
paused and untouched. Conditional deployment approval requires all final audits plus
Integrated Audit PASS; that condition is unmet.

**STOP A4R4.** Parent review, then only fresh independent A4V4 may close M4. Its narrow
scope: reproduce the committed original M4 case; challenge retained cutoff across
repeated cancellation, timeout, concurrent stop and flush commit/rollback ambiguity;
verify timestamp/offset consistency and admitted failure handling; retain M1/M2/M3,
connected observed time, disconnected exclusion, idempotence and same-user multi-guild
isolation. Review the disclosed synchronization change independently. Do not infer
automatic retry or production incidence. No A4V4, A5, Integrated Audit or other phase
was started by this microphase.
