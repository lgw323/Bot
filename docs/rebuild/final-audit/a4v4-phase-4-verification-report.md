# A4V4 - independent Phase 4 audit: PASS

2026-10-02. **PHASE 4 PASS. A4-M4 independently CLOSED; A4-M1/M2/M3 remain
independently CLOSED. No new MATERIAL, DRIFT or BLOCKED finding.** This verdict is
for the governing repository/synthetic Phase 4 gates. Live Gateway, Discord HTTP
and Pi operation are separate later-phase evidence boundaries, not newly verified.

## Authority, candidate and audit ownership

- Entry/audited evidence HEAD `9aef15c6ec5def59a93b68fb06a196d3706b9d40`, branch
  `codex/rebuild-v2`; runtime implementation `c6da7eba800de9816f0c9b7ffb73ca4599f5e3f6`.
  Current `src/`, Engagement integration and characterization have no diff from
  that candidate. The subsequent local evidence commit changes no product code/tests.
- Read active-state, Phase 4 ledger and document index first; then original B20
  Phase 4, C1 F029-F036/FR-031-037, C6, ADR-013/015/017/018/019, original Phase 4
  report, A4V3 report/unchanged reproducer, A4R4 report, A4V2 harness, current
  implementation/tests, production composition and root AGENTS.md. No nested
  AGENTS or relevant local skill applies; no subagent was used.
- [Entry inventory](a4v4-entry-inventory.json): **11 modified / 59 untracked files,
  empty index**, all 70 inherited hashes checked before documentation edits.
  Audit-owned changes are this report/inventory, active-state AL and only the
  Phase 4 ledger row. The inherited untracked document index gets a navigation
  addition but stays uncommitted; its preceding content remains intact.
- Current scoped authorization permits this one audit and local evidence commit.
  Earlier sleep/STOP text remains historical; no automatic continuation is authorized.

## Independent closure and common invariants

The unchanged A4V3 probe now passes all 14 cases, including the original M4
cancelled-stop/explicit-retry scenario: **161 seconds / 10 XP**, disconnected
control **100 seconds / 5 XP**. The old failure was 761 seconds / 60 XP.
M4 is independently CLOSED, not merely accepted from the remediation report.

The implementation retains one effective cutoff before any stop await. Retry
constructs a fresh DatabaseRequest but reuses that effective cutoff. The offline
offset is applied once; admission rejects later events/READY/disconnect/resume.
Pending service outcomes drain before choosing observed-only policy. SQLite owns
atomic credit and epoch deletion, so a rolled-back flush can retry and a committed
flush with lost acknowledgement does not credit twice. Successful start clears
the prior cutoff only after begin_epoch succeeds. No dictionary of per-user
accrual, new task, SQL format, formula or automatic resource retry was introduced.

Independent new evidence challenges combinations beyond rerunning repair tests:

| A4V4 scenario | Actual evidence |
| --- | --- |
| Real flush transaction holds uncommitted credit; first waiter reaches a real DatabaseDeadlineError or is cancelled; retry enters before the first SQL worker is released | Six cases: connected/resumed totals **[161,151]**, disconnected **[100,90]** for the same user in guilds 100/200. A separate reader sees [0,0] before commit. Four stop calls retain cutoff 1161/1100 and zero pending outcomes; retries have distinct requests and renewed deadlines. |
| Retry and two additional concurrent stops after first transaction rollback | One settlement only, runtime/voice tables empty, admission remains closed. Retry can queue behind still-owned SQL work; no reliance on a pre-retry writer barrier. |
| Successful stop/start after each preceding case, including still-disconnected state | Only a new 75-second connected stay is added in guild 100: totals 236 or 175; guild 200 unchanged. No inherited cutoff or gap double subtraction. |
| Replacement READY held in real SQLite across cancelled stop and retry; present guild 100, absent guild 200 | Snapshot tick 1100, retained flush tick 1161. Success **[131,60]**; rollback/cancellation **[70,60]**. All outcomes drain before the flush policy is chosen; M1/M2 are preserved together with M3/M4. |
| Pre-flush rejection followed by delayed retry around short-stay threshold | 59.75 seconds still stores **0**, 60.25 stores **60**. Retry delay cannot turn a discarded short stay into earned time. |

Each new scenario uses real service/event repository/temporary SQLite, fake clock
and offline transport. Real worker deadline tests hold SQL with a bounded event
until the deadline is observed; they do not sleep to guess ordering. The tests
release/reap their work in finally blocks. A successful current-source run is
evidence for these interleavings, not exhaustive model checking of all schedules.

## Fresh executions, no double counting

Existing Windows .venv; root dotenv/credential barrier and inspected temporary DB
fixtures. No dependency installation, WSL, real DB/backup, Discord login or network.

| Disjoint selection | Result |
| --- | --- |
| Engagement integration + Engagement characterization + adapted A4V2 + unchanged A4V3 | **172 PASS / 0 FAIL / 0 SKIP**, 17.27s, process exit 0 |
| New independent A4V4 probe, stop on first failure | **11 PASS / 0 FAIL / 0 SKIP**, 2.54s; pytest successful summary |
| Import/layer ownership + Engagement incomplete-cleanup consumer + aggregate reverse-order ownership | **14 PASS / 0 FAIL / 0 SKIP**, 1.20s, process exit 0 |

**197 passing pytest cases, no failures/skips**, across disjoint selections.
The first selection is 120 earlier focused + 22 A4R4 regressions + 16 adapted A4V2
+ 14 unchanged A4V3. Historical and overlapping remediation runs are not added.
The independent command was piped through PowerShell Tee-Object; its pipeline exit
alone is not treated as pytest evidence. The captured complete pytest summary below
records the successful 11-case run. There were no functional failures or probe edits
after first execution in A4V4. `rg` was unavailable and one early source lookup used
`engagement/service.py` before correcting to `application/service.py`; inspection
issues only, no setup/collection error. The user also supplied root AGENTS rules;
terminal rendering of Korean in some repository files was imperfect.

Commands from repository root (all include strict runtime/unraisable warning checks):

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py scratch/a4v4/test_a4v2_drain_barrier.py scratch/a4v4/test_a4v3_independent.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest scratch/a4v4/test_a4v4_independent.py -q -s -x --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning 2>&1 | Tee-Object -FilePath scratch/a4v4/independent-output.txt
.venv/Scripts/python.exe -m pytest tests/architecture/test_import_rules.py 'tests/integration/watch/test_cleanup_ownership.py::test_equivalent_nested_report_consumers_preserve_dependencies[engagement]' tests/integration/watch/test_cleanup_ownership.py::test_aggregate_child_stop_error_retains_reverse_order_ownership -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

The 14 adjacent cases resolve current import/ownership evidence for Phase 4 closure;
they do not audit Watch or adjacent phases. No broad/full-suite rerun was warranted
by this audit-only task after these gates passed. Known architecture inventory/Deno
failures remain unresolved; audioop DeprecationWarning remains in the first two
runs. A3-N1 connection-description MINOR and A3-I1 historical Watch INFO are retained.
**No clean full-suite claim.**

### Reproducer integrity and disclosed synchronization adaptation

Extracted Python blocks from committed A4V2/A4V3 reports. Normalized UTF-8/LF hashes:

- Unchanged A4V2 helper source `test_a4v2_exact.py`:
  `458ef4d61918962dd1c8dc83c16780034ed2e9b99aadb4e6d68f014945df2a83`.
- Unchanged A4V3 executed source `test_a4v3_independent.py`:
  `86fb5da03fce7ba8d8aa64d9a9685c74b85fd6fe9793d5d657d49fb0ae32ae08`.
- Executed adapted A4V2 `test_a4v2_drain_barrier.py`:
  `e7f7f7445e5c791d0d504cf6ec7d358849168d9334e0b08718e204c0d1294a1b`.

Independently reviewed the exact A4R4 adaptation: only stop_barrier changes from
waiting for a new clock sample to waiting for drain entry, with bounded failure
cleanup. This is valid because retries intentionally no longer sample a clock.
No test body, expected total or failure assertion changes. A4V3 still imports its
unchanged A4V2 helpers. The original 16-case A4V2 file was not rerun or advertised
as unchanged PASS. A4R4's 168 PASS/4 harness failures, clock-resolution corrections
and earlier A4R2 synchronization history remain disclosed in their original reports.

## Complete Phase 4 gate disposition

| Governing scope | Current evidence and disposition |
| --- | --- |
| B20 Phase 4 / C1 F029, FR-031: text/Jamo/level policy | PASS: actual V1 policy comparison, all 11,172 Hangul syllables, whitespace/Unicode and level curve; approved formula preserved. |
| C6 text transactional ownership | PASS: parallel duplicates, durable receipt/restart, capacity/expiry, busy/cancellation rollback, bot/DM exclusion and same-user guild isolation. No new cooldown or history-backfill claim. |
| C1 F030/FR-032 and C6 voice formula/session | PASS: completed minutes, short stays, fractional stored seconds, move/mute/deaf, duplicate/out-of-order tombstones, shutdown/restart, isolated multi-guild state. |
| A4-M1 READY reconciliation | CLOSED retained: absent/present/pending READY, cross-stream duration, queued snapshot, replacement and cancellation. New combined snapshot/retry checks pass. |
| A4-M2 pending observation ownership | CLOSED retained: success/failure/cancel drain, failed SQL acknowledgement handling, conservative observed-only flush and resource failure propagation. |
| A4-M3 disconnect/replay/RESUMED | CLOSED retained: original delayed leave and disconnected-stop bounds; repeated gaps, fractional intervals, live/replay events queued behind SQL and offline SDK dispatch pass. |
| A4-M4 interrupted stop/retry cutoff | Independently CLOSED: original unchanged M4 probe plus cancellation, drain timeout, flush rollback/deadline, lost acknowledgement, repeated/concurrent retries and new successful lifecycle checks. |
| C1 F031/F032, FR-033: profile/ranking | PASS: actual five-command signatures, private profile/master-other/self, missing profile, TOP10/ties/completed-minute parity, visibility and guild isolation. Underlying tested lifecycle totals now meet policy. |
| C1 F033-F036, FR-034-037: birthday | PASS: exact master authorization, register/delete rowcount, real calendar/leap-century and Feb29 fallback, sorted complete list/empty privacy, KST 09:00/catch-up, durable per-guild/date claim and cancellation/failure/restart semantics. At-most-once attempt may miss a notification; no exactly-once claim. |
| C6/C3/ADR-017/019: adapters/composition/lifecycle | PASS: SQL/SDK boundaries, import side-effect guards, bounded scheduler/idempotent READY, command error ACK behavior, listener/resource cleanup. Current production composition uses the same EngagementResource after database readiness; no new alternative accounting path. |
| C4/ADR-018/019: data compatibility | PASS: synthetic explicit-copy migration, unchanged source, V1 reader, full encrypted metadata roundtrip and fail-closed corruption/startup. Original migrations/schema/envelope unaffected by A4R4/A4V4. |
| ADR-013: cross-guild behavior | PASS: same user in two guilds across text/voice/profile/rank/birthday and notification-channel checks, plus new retry/READY isolation values above. |
| Live Gateway/Discord HTTP/Pi timing/capacity | NOT RUN; scoped limit deferred by original Phase 4 contract/report to staging/later audits. Synthetic SDK dispatch is not live reconnect evidence. |

Original Phase 4 completion is treated as historical scope, not a permanent
guarantee: M1-M4 exposed lifecycle gaps and required separate repairs. Current
tests exercise the production service/SQLite adapters, not an obsolete replacement.
Later executable composition still reaches those paths. Existing PRESERVE and
approved CORRECT expectations remain; no silent behavior waiver or assertion change.
No unresolved material Phase 4 gate remains within this repository/synthetic scope.

## Preservation, limitations and next boundary

Current EngagementResource retains its `_stopping` guard: an incomplete cleanup
does not automatically retry service.stop. This audit explicitly retries the
service API and proves its accounting invariant. No real impacted user, automatic
retry occurrence, live Gateway timestamp accuracy or production repair is claimed.
Concurrent start during incomplete stop remains outside the lifecycle contract.

Exact inherited paths/statuses/hashes are in the inventory. Eleven modified files:
CHANGELOG.md, README.md, docs/product-spec.md, docs/rebuild/README.md,
docs/rebuild/current/current-plan.md, final-audit-active-state.md,
final-audit-ledger.md, a3-phase-3-report.md, phase-10-full-sweep-report.md,
phase-10/phase-10-report.md and tests/browser/watch_fixture.py (inventory has full
paths). The 59 untracked files comprise the mixed document index, Phase 10B
authority/evidence, A0/A1/A2 reports, handoff ZIP/export tree, invitation guide and
two browser scripts. No inherited file is bulk-staged, reset, deleted or overwritten.
The three shared audit files retain their exact prior bytes after removing only
this audit's appended text/replacement row. New ignored scratch evidence stays local.

Local evidence staging uses HEAD plus only AL/Phase 4 row for shared tracked files;
staged diff and `git diff --cached --check` are reviewed before committing. The
audit evidence commit is the descendant final HEAD reported to the parent. Final
residual ownership is 11 modified / 59 untracked, empty index. Rollback is a reviewed
ordinary revert of this evidence commit; preserve mixed work, no history/data rewrite.

Production untouched: recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`
and pin `r-8e9018d4b8061cde-3dac82a792fad576` remain separate, unchanged identities.
No production/Pi access, deploy/restart, actual DB modification/older restore,
V1/concurrent writers, systemd/Cloudflare change, installation, cleanup or remote push.
Friend activation HELD. All final audits plus Integrated Audit deployment condition
is still unmet. My Food remains paused/unrelated. A0-A3 verdicts are unchanged;
A5-A10, Integrated Audit and Phase 11 were not started.

**STOP A4V4 for parent review.** The next narrow boundary is parent acceptance of
this Phase 4 closure; any separately assigned A5 is a fresh microphase, not started
here. All three test commands completed; no audit worker/process needs to remain alive.

## Exact independent source and output

Extract the unchanged A4V2/A4V3 report blocks as above. Recreate the A4V2 adapted
file with the exact stop_barrier block in the A4R4 report. Save the following new
source as `scratch/a4v4/test_a4v4_independent.py`; it imports only original A4V2
fixtures/helpers. These audit probes are not added to the product test tree.

Normalized UTF-8/LF source SHA-256: `8edf84ca23c6c5b67f416892573a2f7f20722f68d0ca9e2b48b128a13ecd12c7`.

```python
"""A4V4 audit evidence: synthetic fixtures only; no repository test edits."""
import asyncio
import json
import threading
from dataclasses import replace

import pytest
from test_a4v2_exact import harness, ready, voice, seconds, empty, packet
from discordbot.engagement.ports.events import VoicePresence
from discordbot.platform.errors import ConflictError, DatabaseUnavailableError
from discordbot.storage.ports.contracts import DatabaseDeadlineError


async def two_guilds(clock, bot):
    await ready(bot, 'a4v4')
    await voice(bot, 2, '101')
    clock.tick = 1010
    await voice(bot, 2, '201', guild=200)
    clock.tick = 1070
    for guild in (100, 200):
        await voice(bot, 3, '102', guild=guild)


@pytest.mark.parametrize('transport', ['connected', 'resumed', 'disconnected'])
@pytest.mark.parametrize('interrupt', ['deadline', 'cancel'])
def test_retry_queued_while_first_flush_still_owns_transaction(tmp_path, monkeypatch, transport, interrupt):
    async def scenario():
        from discordbot.engagement.adapters import event_repository
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await two_guilds(clock, bot)
            clock.tick = 1100
            if transport != 'connected':
                await bot.emit('on_disconnect')
                clock.tick = 1700
            if transport == 'resumed':
                await packet(bot, 'RESUMED', 4, {})
            clock.tick += 61
            cutoff = 1100 if transport == 'disconnected' else 1161
            entered, release, retry_entered = asyncio.Event(), threading.Event(), asyncio.Event()
            loop = asyncio.get_running_loop()
            progress, flush = event_repository._progress, app.events.flush_voice
            calls, credits, requests = [], [], []
            def held(conn, guild, user, *args, **kwargs):
                progress(conn, guild, user, *args, **kwargs)
                credits.append((guild, kwargs.get('seconds')))
                if len(credits) == 1:
                    loop.call_soon_threadsafe(entered.set)
                    assert release.wait(5), 'audit failed to release SQL worker'
            async def recording(epoch, tick, request, **kwargs):
                calls.append((tick, kwargs['observed_only'], app._voice_pending))
                requests.append(request)
                if len(calls) == 2:
                    retry_entered.set()
                return await flush(epoch, tick, request, **kwargs)
            monkeypatch.setattr(event_repository, '_progress', held)
            monkeypatch.setattr(app.events, 'flush_voice', recording)
            config = app.config
            if interrupt == 'deadline':
                app.config = replace(config, request_seconds=0.2)
            tasks = [asyncio.create_task(app.stop())]
            try:
                await asyncio.wait_for(entered.wait(), 2)
                # Reader sees pre-transaction totals while writer has uncommitted credit.
                assert [await seconds(app, g) for g in (100, 200)] == [0, 0]
                clock.tick += 600
                if interrupt == 'cancel':
                    tasks[0].cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[0]
                else:
                    with pytest.raises(DatabaseDeadlineError):
                        await asyncio.wait_for(tasks[0], 2)
                app.config = replace(config, request_seconds=6)
                tasks.append(asyncio.create_task(app.stop()))
                await asyncio.wait_for(retry_entered.wait(), 2)
                assert not tasks[1].done() and not release.is_set()
                assert not app._accepting and not app._voice_faulted
                with pytest.raises(ConflictError):
                    await app.voice_ready(owner.gateway.stream, ())
                clock.tick += 600
                release.set()
                await tasks[1]
                app.config = replace(config, request_seconds=7)
                await asyncio.gather(app.stop(), app.stop())
                expected = [int(cutoff-1000), int(cutoff-1010)]
                assert [await seconds(app, g) for g in (100, 200)] == expected
                assert calls == [(cutoff, False, 0)] * 4
                assert len({id(r) for r in requests}) == 4
                assert requests[1].deadline > requests[0].deadline
                await empty(db, app)
                # Reopen only after completed settlement, including a still-disconnected clock.
                clock.tick += 600
                await app.start()
                app.gateway_session('next')
                await app.voice(100, 10, 'next', 1, 101, False)
                clock.tick += 75
                await app.stop()
                assert [await seconds(app, g) for g in (100, 200)] == [expected[0]+75, expected[1]]
                await empty(db, app)
                print(json.dumps(dict(case='flush-owned-retry', transport=transport, interrupt=interrupt,
                                     cutoff=cutoff, settled=expected, new_lifecycle=expected[0]+75)))
            finally:
                release.set()
                app.config = config
                await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('outcome', ['success', 'rollback', 'cancel'])
def test_replacement_snapshot_outcome_after_cancelled_stop(tmp_path, monkeypatch, outcome):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await two_guilds(clock, bot)
            clock.tick = 1100
            await bot.emit('on_disconnect')
            clock.tick = 1700
            await ready(bot, 'replacement', cache=False)
            entered, release, draining = asyncio.Event(), threading.Event(), asyncio.Queue()
            loop = asyncio.get_running_loop()
            apply, wait, flush = app.events._apply_voice, app._voice_drained.wait, app.events.flush_voice
            ticks, calls = [], []
            def held(conn, event, capacity):
                ticks.append(event.tick)
                result = apply(conn, event, capacity)
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)
                if outcome == 'rollback':
                    raise DatabaseUnavailableError('A4V4 snapshot rollback')
                return result
            async def drain():
                draining.put_nowait(True)
                return await wait()
            async def recording(epoch, tick, request, **kwargs):
                calls.append((tick, kwargs['observed_only'], app._voice_pending))
                return await flush(epoch, tick, request, **kwargs)
            monkeypatch.setattr(app.events, '_apply_voice', held)
            monkeypatch.setattr(app._voice_drained, 'wait', drain)
            monkeypatch.setattr(app.events, 'flush_voice', recording)
            observation = asyncio.create_task(app.voice_ready(owner.gateway.stream, (VoicePresence(100,10,101,False),)))
            tasks = []
            try:
                await asyncio.wait_for(entered.wait(), 2)
                clock.tick = 1761
                tasks.append(asyncio.create_task(app.stop()))
                await asyncio.wait_for(draining.get(), 2)
                tasks[0].cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tasks[0]
                clock.tick += 600
                tasks.append(asyncio.create_task(app.stop()))
                await asyncio.wait_for(draining.get(), 2)
                assert not calls and app._voice_pending == 1
                if outcome == 'cancel':
                    observation.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await observation
                release.set()
                if outcome == 'rollback':
                    with pytest.raises(DatabaseUnavailableError):
                        await observation
                elif outcome == 'success':
                    await observation
                await tasks[1]
                expected = [131, 60] if outcome == 'success' else [70, 60]
                assert ticks == [1100]
                assert calls == [(1161, outcome != 'success', 0)]
                assert [await seconds(app, g) for g in (100, 200)] == expected
                await empty(db, app)
                print(json.dumps(dict(case='snapshot-cancelled-stop', outcome=outcome, settled=expected)))
            finally:
                release.set()
                await asyncio.gather(observation, *tasks, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('duration,expected', [(59.75,0),(60.25,60)])
def test_flush_rollback_retry_preserves_short_stay_threshold(tmp_path, monkeypatch, duration, expected):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await ready(bot, 'threshold')
            await voice(bot, 2, '101')
            clock.tick += duration
            flush = app.events.flush_voice
            async def fail(*args, **kwargs):
                raise DatabaseUnavailableError('synthetic pre-flush rejection')
            monkeypatch.setattr(app.events, 'flush_voice', fail)
            with pytest.raises(DatabaseUnavailableError):
                await app.stop()
            clock.tick += 600
            monkeypatch.setattr(app.events, 'flush_voice', flush)
            await app.stop()
            await app.stop()
            assert await seconds(app) == expected
            await empty(db, app)
            print(json.dumps(dict(case='short-stay-retry', duration=duration, seconds=expected)))
    asyncio.run(scenario())
```

Captured independent output:

```text
{"case": "flush-owned-retry", "transport": "connected", "interrupt": "deadline", "cutoff": 1161, "settled": [161, 151], "new_lifecycle": 236}
.{"case": "flush-owned-retry", "transport": "resumed", "interrupt": "deadline", "cutoff": 1161, "settled": [161, 151], "new_lifecycle": 236}
.{"case": "flush-owned-retry", "transport": "disconnected", "interrupt": "deadline", "cutoff": 1100, "settled": [100, 90], "new_lifecycle": 175}
.{"case": "flush-owned-retry", "transport": "connected", "interrupt": "cancel", "cutoff": 1161, "settled": [161, 151], "new_lifecycle": 236}
.{"case": "flush-owned-retry", "transport": "resumed", "interrupt": "cancel", "cutoff": 1161, "settled": [161, 151], "new_lifecycle": 236}
.{"case": "flush-owned-retry", "transport": "disconnected", "interrupt": "cancel", "cutoff": 1100, "settled": [100, 90], "new_lifecycle": 175}
.{"case": "snapshot-cancelled-stop", "outcome": "success", "settled": [131, 60]}
.{"case": "snapshot-cancelled-stop", "outcome": "rollback", "settled": [70, 60]}
.{"case": "snapshot-cancelled-stop", "outcome": "cancel", "settled": [70, 60]}
.{"case": "short-stay-retry", "duration": 59.75, "seconds": 0}
.{"case": "short-stay-retry", "duration": 60.25, "seconds": 60}
.
============================== warnings summary ===============================
scratch/a4v4/test_a4v4_independent.py::test_retry_queued_while_first_flush_still_owns_transaction[deadline-connected]
  C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot\.venv\Lib\site-packages\discord\player.py:30: DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13
    import audioop

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
11 passed, 1 warning in 2.54s
```
