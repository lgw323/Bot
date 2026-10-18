# A4V2 - independent Phase 4 audit: FAIL

2026-10-02. **A4V2 / PHASE 4 FAIL. A4-M1 remains CLOSED; A4-M2 independently CLOSED;
new A4-M3 MATERIAL OPEN.** Stop after this microphase. No remediation or A5.

## Candidate, authority and ownership

Audited runtime HEAD: `7ead8a2fae5501f384c26e6d894e5b6ca9a906e9` on
`codex/rebuild-v2`. Any following A4V2 commit is documentation only; the tested source
is exactly this candidate. A4R2 owns service.py, test_voice_reconnect.py and
new test_voice_shutdown.py (+296/-11), confirmed from its commit diff.

Read current active-state, ledger and document index first, then B20 Phase 4,
C6, C1 Engagement, accepted ADR-013/015/017/018/019, original Phase 4 report,
A4/A4R1/A4V1/A4R2 evidence, current implementation/tests and root AGENTS.md.
Current scoped authority wins over historical NEXT instructions. No applicable local
skill or nested source/test AGENTS.md; no delegation, installation or web research.

[Entry inventory](a4v2-entry-inventory.json): **11 modified / 67 untracked, empty index**,
matching the handoff. All 78 inherited file hashes matched immediately before audit
documentation edits. No candidate/competing-writer drift was observed. Implementation,
repository tests, schemas, formulas and product contracts were not edited.

Later user direction authorizes a local documentation commit before computer shutdown.
Only this report, its inventory, the A4V2 active-state addition and Phase 4 ledger row
are selected. The two shared files are staged from HEAD plus those exact scoped changes;
the earlier mixed additions remain in the working tree. The untracked mixed document
index receives only an A4V2 link and remains uncommitted. No bulk staging or reset.

## A4-M2 closure and synchronization review

The old probe waited for a flush SQL submission while an observation was unresolved.
That barrier encoded the defective ordering: the repaired service must defer flush
until observation success/failure/cancellation handling completes. A4R2 replaces it
with one event-loop yield plus admission-closed, stop-pending and no-flush-submitted
assertions. The writer hold and injected rollback remain; exact 70-second/5-XP
assertions are unchanged. This adjustment is justified, not a weakened accounting
assertion or evidence of an unmodified post-fix probe PASS.

Independent probes below use a clock callback to acknowledge stop entry, rather than
that scheduling yield. They hold the actual SQLite transaction with bounded events,
and observe every flush's tick, observed-only policy and pending count. Failure and
cancellation of event and READY transactions all settle **70s / 5 XP**. Success settles
**100s** for a mute at 1100, or **700s** for still-present same-stream READY at stop
1700. Advancing the clock to 2300 during drain adds no credit: first flush remains
`(1700, expected_fault_policy, 0)` in all six cases.

A separate barrier deliberately delays propagation of a completed SQL failure back
to the service while the SQL lane is already free. Stop still waits; it then credits
70 seconds. Thus the proof covers service outcome ordering, not just writer ordering.
Multiple admitted observations, successful duplicate completion while one failure
remains, text/read independence, simultaneous stops, closed late admission, bounded
timeout/cancelled drain, metadata preservation, explicit retry, flush rollback and
repeat/idempotent settlement also pass. Retry probes use a settled/muted observation;
they do not prove all possible unmuted retry timestamp policies. No such wider claim
is needed to close the exact stale-failure-flag defect. **A4-M2 CLOSED.**

## A4-M3 MATERIAL - disconnected/RESUME time is credited as live presence

Contract basis: B20 formula/policy gate; C1 F030/FR-032 unmuted-session duration;
C6 Voice XP/lifecycle observed intervals and uncertain observation fail-closed rule;
ADR-019 conservative uncertainty. Unknown departure time may be omitted; time after
an actual departure must not become durable voice XP. This finding does not assume
that every disconnect means the user left, or require reconstructing an unavailable
original event timestamp.

The actual EngagementResource registers only raw-receive and ready listeners
(`discord_runtime.py:117-118`); it has no disconnect boundary. VoiceGateway.receive
handles READY and voice updates, ignores RESUMED (`:40-64`), and supplies no historical
tick. EngagementService.voice assigns the current receipt-time clock (`service.py:112`).
Same-stream SQL accrual subtracts the prior observation tick (`event_repository.py:99`).
Shutdown also extrapolates a healthy-looking same-stream row (`:135-142`).
Thus disconnect is never marked uncertain and a replayed historical leave is treated
as a current leave. Sequence dedupe prevents duplicate settlement, but cannot correct
the wrong elapsed duration. This is distinct from M1 replacement READY and M2 failed
DB observation; both corrected paths still pass.

Exact synthetic history in one process epoch and one Gateway stream:

1. Join at t=1000, unmuted move at 1070: 70 seconds persisted as observed duration.
2. At 1100 transport disconnects and the synthetic user leaves. Legitimate total
   is at most 100 seconds; choosing observed-only 70 seconds would also be safe.
3. At 1700 either deliver the buffered leave (sequence 4), then RESUMED (5), then
   duplicate leave (4), or stop while still disconnected without receiving that leave.
4. Stop and read durable synthetic user seconds via the real repository.

| Path | Stored seconds / voice XP | Allowed upper bound | Outcome |
| --- | --- | --- | --- |
| Connected active RESUMED control, leave delivered at 1100 | 100 / 5 | 100 / 5 | PASS control |
| Same-stream delayed leave at 1700, then RESUMED/replay | **700 / 55** | 100 / 5 | FAIL |
| Disconnected shutdown at 1700, no replacement READY | **700 / 55** | 100 / 5 | FAIL |

Both faulty paths leave `_voice_faulted=False`: **600 excess seconds / 50 XP**.
The final probe has one pytest assertion covering both observations, not two counted
pytest failures. The clock and actual departure are fixture ground truth; there is
no extra event timestamp field supplied to production. Delivery occurs through the
listeners registered by the real EngagementResource on a synthetic bot. Local installed
discord.py client source confirms it dispatches disconnect during reconnect; no live
transport replay, production occurrence or impacted user is claimed.

**MATERIAL STOP:** no further tests, fixes, policy redesign or broader suite after
this result. Parent review must determine a narrow conservative disconnect/replay
boundary before separately authorizing remediation. An exact timing guarantee for
historical replay is not inferred from unavailable timestamps.

## Fresh execution and complete Phase 4 gate disposition

Existing Windows `.venv`, root dotenv/credential barrier, synthetic IDs, temporary
SQLite/bootstrap, fake clocks/Discord cache and bounded barriers only. Repository
fixtures redirect legacy DB/backup to temporary paths; inspected tests use mock sends.
Every probe drains its tasks, closes EngagementResource twice, checks supervisor
ownership and closes SQLite. No actual DB, credentials, network or Pi/WSL used.

| Execution | Current result |
| --- | --- |
| Engagement integration + Engagement characterization | **105 PASS / 0 FAIL / 0 SKIP**, 8.64s, exit 0 |
| New independent outcome/lifecycle/M1/guild probes (before timing test added) | **15 PASS / 0 FAIL / 0 SKIP**, 2.32s, exit 0 |
| New active RESUME/disconnect timing probe, selected alone | **0 PASS / 1 FAIL / 0 SKIP**, 15 deselected, 0.80s, exit 1 |

Known audioop warning in each execution. No broad/dependent/full-suite rerun after
material STOP. A4R2's 131 PASS and A3V3's 1253 PASS / 2 known FAIL / 27 SKIP are historical,
not current results. No clean full-suite PASS. A2-N1 stale inventory, missing Deno,
audioop, A3-N1 connection-description and A3-I1 historical Watch limits stay unchanged.

| Phase 4 gate | Evidence / disposition |
| --- | --- |
| Text XP/Jamo/level policy, bot/DM exclusion, receipt/restart/capacity/failure | Fresh test_policy/events/failures + characterization; 11,172 Hangul comparison and level curve, atomic rollback and guild isolation PASS. |
| Voice formula/short stays/mute/deaf/move/fractional data/process restart | Fresh policy/events/reconnect/failures and characterization PASS; completed-minute formula unchanged. |
| M1 replacement READY absence/continuity/pending snapshot | Independent 70s/5 XP and rejoin 131s/10 XP; pending READY 70s. CLOSED retained. |
| M2 pending failure/cancel/drain/flush order and stop tick | Independent event/READY failure/cancel/success, failure-propagation barrier, concurrent stops, retry and rollback PASS; CLOSED. |
| Same-user multi-guild + repeat READY/sequence replay | Independent [66, 0] seconds and fresh reconnect cases PASS; sub-minute duration kept only in present guild. |
| Active RESUME, historical replay and disconnected shutdown | Connected control PASS; delayed leave and disconnected stop FAIL A4-M3. Gate evaluated, not left as unspecified missing coverage. |
| Profile/ranking | Fresh exact five V1 signatures, self/master-other/private/missing/DM/guild checks; completed-minute parity/TOP10/ties/visibility PASS. M3 can corrupt underlying durable totals. |
| Birthday register/delete/list/master/calendar | Fresh master exact-match, valid leap date/century policy, legacy rowcount, guild isolation and list chunking PASS. |
| Birthday KST/delivery ownership | Fresh 09:00/year boundary, scheduler delay/lease/repeated start, daily guild claim, no duplicate after send/ACK failure/cancel, configured-channel guild validation PASS; synthetic only. |
| Data, architecture and composition | Fresh explicit migration gate, V1 reader, encrypted metadata roundtrip, corruption fail-closed, offline real Bot construction and cleanup PASS. Code review retains layer boundaries and startup/stop ordering. No independent Linux/host lifecycle rerun or whole-architecture certification. |
| Actual Gateway/Discord HTTP/Pi capacity and latency | NOT EXECUTED; synthetic Gateway behavior explicitly distinct from live verification. Historical Phase 10 profile/rank evidence is narrower, not timing proof. |

The complete Phase 4 gate disposition is therefore FAIL, despite other local gates
passing. A0-A3 retain their prior working-tree statuses; they were not re-audited.
A5-A10, Integrated Audit and Phase 11 remain unstarted in this session.

Commands (run from repository root; no package installation):

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
# Final combined source: first selection reproduces the same 15 passing cases.
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4v2-probe\test_a4v2_independent.py" --confcutdir="$env:TEMP\discordbot-a4v2-probe" -k "not active_resume" -q -s --tb=short -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4v2-probe\test_a4v2_independent.py" --confcutdir="$env:TEMP\discordbot-a4v2-probe" -k active_resume -q -s --tb=short -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

The first independent execution ran without `-k` before the final timing function was
appended; the `not active_resume` form is an equivalent future reproduction command,
not a claimed additional execution. Original 15 case source was unchanged.

## Shutdown handoff, retained work and next boundary

All three pytest commands completed with recorded exit codes; their background tasks,
workers and DBs were closed. No audit test process remains running and no execution
must be resumed. Keep the existing worktree, `.git`, entry inventory and this report:
it embeds the entire independent probe, so evidence does not depend on temporary files.
The temporary synthetic probe/fixtures may remain; no cleanup was performed.

Uncommitted inherited work is deliberately retained: 11 tracked modifications
(CHANGELOG, README, product-spec, rebuild README/current-plan, mixed active-state/ledger,
A3 report, historical Phase 10 reports and browser fixture), and 67 inherited untracked
paths (document index, Phase 10 evidence, A0/A1/A2 and A4-chain audit reports/inventories,
handoff exports, invitation guide and browser probes). The inventory enumerates every
path and hash. These contain unrelated or mixed historical ownership; committing them
as newly verified A4V2 work would be misleading. Shared authority residuals remain
uncommitted after selective staging; preserve them before shutdown. No new source/test
files are staged. The report/inventory plus two scoped authority updates form one
local audit-documentation commit; its SHA is reported by the caller after commit.
Rollback is a reviewed normal revert of that documentation commit while preserving
mixed worktree additions. No data rollback, reset or history rewrite.

Production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct, unchanged documentary identities.
No production access, deployment/restart, DB changes/restore, V1/concurrent writer,
systemd/Cloudflare, remote push, MyFood work or cleanup. Friend rollout remains HELD.
Conditional deployment approval still lacks Integrated Audit PASS and is not actionable.

**Next narrow boundary: parent review of A4-M3, then separately authorized disconnect/
RESUME observation-policy remediation and independent re-audit. Not started. STOP A4V2.**

## Exact independent probe source

Temporary-file SHA-256: `19d3f58860a989c9adec2e63b5dfd7a332b7228a7f42f82764584b8080ece488`.
UTF-8/LF source (without BOM) SHA-256: `458ef4d61918962dd1c8dc83c16780034ed2e9b99aadb4e6d68f014945df2a83`.
Copy the following into the temporary path for reproduction; this is evidence, not a
repository test-suite mutation. Only synthetic fake transport and temporary DBs run.

```python
"""A4V2 independent audit evidence. Only synthetic local SQLite and simulated transport."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import sys
import threading
from types import SimpleNamespace
import pytest
ROOT = Path(r'C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot')
runpy.run_path(str(ROOT / 'conftest.py'))
sys.path.insert(0, str(ROOT / 'src'))
from discordbot.engagement.adapters.discord_runtime import EngagementResource
from discordbot.engagement.domain.policy import Progress
from discordbot.engagement.ports.events import EngagementConfig, VoicePresence
from discordbot.platform.errors import ConflictError, DatabaseUnavailableError, ShutdownError
from discordbot.platform.tasks import TaskSupervisor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

class Clock:
    def __init__(self):
        self.tick = 1000.0
        self.stop_seen = None
    def monotonic(self):
        if self.stop_seen is not None:
            self.stop_seen.set()
        return self.tick
    def now(self):
        return datetime(2027, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.tick)

class Bot:
    _enable_debug_events = True
    def __init__(self):
        self.listeners = {}
        self.closed = False
        self.guilds = [SimpleNamespace(id=g, voice_channels=[], get_member=lambda u: SimpleNamespace(bot=False)) for g in (100, 200)]
    def get_guild(self, gid):
        return next(g for g in self.guilds if g.id == gid)
    async def add_cog(self, cog): pass
    async def remove_cog(self, name): pass
    def add_listener(self, callback, name):
        self.listeners.setdefault(name, []).append(callback)
    def remove_listener(self, callback, name):
        if callback in self.listeners.get(name, []): self.listeners[name].remove(callback)
    async def close(self): self.closed = True
    async def emit(self, name, *args):
        for callback in tuple(self.listeners.get(name, [])):
            await callback(*args)

@asynccontextmanager
async def harness(tmp_path):
    clock, bot = Clock(), Bot()
    db = SqliteDatabase(DatabaseConfig(tmp_path / 'synthetic.db'))
    await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    await db.start()
    owner = EngagementResource(bot, db, EngagementConfig(42), clock,
        TaskSupervisor(capacity=2, history_capacity=8, clock=clock), 'independent-a4v2')
    await owner.start()
    try:
        yield clock, bot, db, owner.service, owner
    finally:
        clock.stop_seen = None
        await owner.stop()
        await owner.stop()
        assert bot.closed
        assert not owner.supervisor.snapshot().active
        await db.stop()

async def packet(bot, kind, seq, data):
    await bot.emit('on_socket_raw_receive', json.dumps(dict(op=0, t=kind, s=seq, d=data)))
async def ready(bot, name, cache=True):
    await packet(bot, 'READY', 1, dict(session_id=name))
    if cache: await bot.emit('on_ready')
async def voice(bot, seq, channel, guild=100, muted=False):
    await packet(bot, 'VOICE_STATE_UPDATE', seq, dict(guild_id=str(guild), user_id='10',
        channel_id=channel, self_mute=muted, member=dict(user=dict(id='10', bot=False))))
async def seed(clock, bot):
    await ready(bot, 'session-a')
    await voice(bot, 2, '101')
    clock.tick = 1070
    await voice(bot, 3, '102')
async def seconds(app, guild=100):
    row = await app.repository.get_member(guild, 10, app.request())
    return row.total_vc_seconds if row else 0
async def empty(db, app):
    assert await db.read(app.request(), lambda c: (c.execute('SELECT count(*) FROM v2_engagement_voice').fetchone()[0],
        c.execute('SELECT count(*) FROM v2_engagement_runtime').fetchone()[0])) == (0, 0)
async def stop_barrier(app, clock):
    # Explicit callback reached only when stop captures its clock; no scheduling sleep.
    clock.stop_seen = asyncio.Event()
    task = asyncio.create_task(app.stop())
    await asyncio.wait_for(clock.stop_seen.wait(), 2)
    clock.stop_seen = None
    assert not app._accepting
    return task

@pytest.mark.parametrize('kind', ['event', 'ready'])
@pytest.mark.parametrize('outcome', ['failure', 'cancel', 'success'])
def test_transaction_outcome_before_flush(tmp_path, monkeypatch, kind, outcome):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            loop = asyncio.get_running_loop()
            entered, release = asyncio.Event(), threading.Event()
            original = app.events._apply_voice
            def transaction(conn, event, cap):
                result = original(conn, event, cap)
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)
                if outcome == 'failure': raise DatabaseUnavailableError('audit injected rollback')
                return result
            monkeypatch.setattr(app.events, '_apply_voice', transaction)
            flushes = []
            real_flush = app.events.flush_voice
            async def flush(epoch, tick, request, **kw):
                flushes.append((tick, kw['observed_only'], app._voice_pending))
                return await real_flush(epoch, tick, request, **kw)
            monkeypatch.setattr(app.events, 'flush_voice', flush)
            clock.tick = 1100
            observation = asyncio.create_task(app.voice(100, 10, owner.gateway.stream, 4, 102, True)
                if kind == 'event' else app.voice_ready(owner.gateway.stream, (VoicePresence(100, 10, 102, False),)))
            stop = None
            try:
                await asyncio.wait_for(entered.wait(), 2)
                clock.tick = 1700
                stop = await stop_barrier(app, clock)
                assert not stop.done() and not flushes
                with pytest.raises(ConflictError): await app.voice(100, 10, owner.gateway.stream, 5, None, False)
                with pytest.raises(ConflictError): await app.voice_ready(owner.gateway.stream, ())
                clock.tick = 2300
                if outcome == 'cancel':
                    observation.cancel()
                    with pytest.raises(asyncio.CancelledError): await observation
                release.set()
                if outcome == 'failure':
                    with pytest.raises(DatabaseUnavailableError): await observation
                elif outcome == 'success': await observation
                await stop
            finally:
                release.set()
                await asyncio.gather(*(t for t in (observation, stop) if t is not None), return_exceptions=True)
            expected = 70 if outcome != 'success' else 100 if kind == 'event' else 700
            assert flushes == [(1700, outcome != 'success', 0)]
            assert await seconds(app) == expected
            assert Progress(0, await seconds(app)).voice == expected // 60 * 5
            await app.stop()
            assert await seconds(app) == expected
            await empty(db, app)
            print(json.dumps(dict(case=kind+'-'+outcome, seconds=expected, first_flush=flushes[0])))
    asyncio.run(scenario())

def test_sql_failure_return_is_not_yet_service_outcome(tmp_path, monkeypatch):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            failed, release = asyncio.Event(), asyncio.Event()
            def reject(conn, event, capacity): raise DatabaseUnavailableError('audit rollback')
            monkeypatch.setattr(app.events, '_apply_voice', reject)
            real_apply = app.events.apply_voice
            async def delayed(*args):
                try: return await real_apply(*args)
                except DatabaseUnavailableError:
                    failed.set()
                    await release.wait()
                    raise
            monkeypatch.setattr(app.events, 'apply_voice', delayed)
            pending = asyncio.create_task(app.voice(100, 10, owner.gateway.stream, 4, 102, True))
            stop = None
            try:
                await asyncio.wait_for(failed.wait(), 2)
                assert not app._voice_faulted
                # SQL lane is free, but service outcome is still pending.
                await db.write(app.request(), lambda c: None)
                clock.tick = 1700
                stop = await stop_barrier(app, clock)
                assert not stop.done()
                release.set()
                with pytest.raises(DatabaseUnavailableError): await pending
                await stop
                assert await seconds(app) == 70
            finally:
                release.set()
                await asyncio.gather(*(t for t in (pending, stop) if t is not None), return_exceptions=True)
    asyncio.run(scenario())

def test_two_outcomes_and_concurrent_stops(tmp_path, monkeypatch):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            entered, release = asyncio.Event(), asyncio.Event()
            original = app.events.apply_voice
            async def delayed(event, *args):
                if event.sequence == 4:
                    entered.set()
                    await release.wait()
                    raise DatabaseUnavailableError('last pending failure')
                return await original(event, *args)
            monkeypatch.setattr(app.events, 'apply_voice', delayed)
            pending = asyncio.create_task(app.voice(100, 10, owner.gateway.stream, 4, 102, True))
            stops = []
            try:
                await asyncio.wait_for(entered.wait(), 2)
                assert not await app.voice(100, 10, owner.gateway.stream, 3, 102, False)
                assert await app.message(200, 10, 'synthetic', 'abc', clock.now())
                assert (await app.profile(200, 10)).text == 3
                clock.tick = 1700
                stops.append(await stop_barrier(app, clock))
                stops.append(await stop_barrier(app, clock))
                assert all(not t.done() for t in stops)
                release.set()
                with pytest.raises(DatabaseUnavailableError): await pending
                await asyncio.gather(*stops)
                assert await seconds(app) == 70
                assert await seconds(app, 200) == 0
                await empty(db, app)
            finally:
                release.set()
                await asyncio.gather(pending, *stops, return_exceptions=True)
    asyncio.run(scenario())

@pytest.mark.parametrize('interrupt', ['timeout', 'cancel'])
def test_interrupted_drain_preserves_work(tmp_path, monkeypatch, interrupt):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            entered, release = asyncio.Event(), asyncio.Event()
            original = app.events.apply_voice
            async def delay(*args):
                entered.set()
                await release.wait()
                return await original(*args)
            monkeypatch.setattr(app.events, 'apply_voice', delay)
            pending = asyncio.create_task(app.voice(100, 10, owner.gateway.stream, 4, 102, True))
            stop = None
            config = app.config
            try:
                await asyncio.wait_for(entered.wait(), 2)
                clock.tick = 1700
                app.config = replace(config, request_seconds=0.05)
                stop = await stop_barrier(app, clock)
                if interrupt == 'cancel':
                    stop.cancel()
                    with pytest.raises(asyncio.CancelledError): await stop
                else:
                    with pytest.raises(ShutdownError): await asyncio.wait_for(stop, 2)
                assert not pending.done()
                app.config = config
                assert await seconds(app) == 0
                assert await db.read(app.request(), lambda c: c.execute('SELECT duration FROM v2_engagement_voice').fetchone()) == (70,)
                release.set()
                await pending
                await app.stop()
                assert await seconds(app) == 70
                await empty(db, app)
            finally:
                app.config = config
                release.set()
                await asyncio.gather(*(t for t in (pending, stop) if t is not None), return_exceptions=True)
    asyncio.run(scenario())

def test_flush_rollback_and_retry(tmp_path, monkeypatch):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            # Persisted muted observation ensures retry is accounting-idempotent.
            await voice(bot, 4, '102', muted=True)
            from discordbot.engagement.adapters import event_repository
            original = event_repository._progress
            def fail(conn, *a, **kw):
                original(conn, *a, **kw)
                raise DatabaseUnavailableError('audit flush rollback')
            monkeypatch.setattr(event_repository, '_progress', fail)
            with pytest.raises(DatabaseUnavailableError): await app.stop()
            assert await seconds(app) == 0
            monkeypatch.setattr(event_repository, '_progress', original)
            clock.tick = 2300
            await asyncio.gather(app.stop(), app.stop())
            assert await seconds(app) == 70
            await empty(db, app)
    asyncio.run(scenario())

@pytest.mark.parametrize('finish', ['stop', 'rejoin', 'pending-ready'])
def test_m1_absent_replacement(tmp_path, finish):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await seed(clock, bot)
            await ready(bot, 'replacement', cache=finish != 'pending-ready')
            clock.tick = 1670
            expected = 70
            if finish == 'rejoin':
                await voice(bot, 2, '101')
                clock.tick += 61
                await voice(bot, 3, None)
                expected = 131
            await app.stop()
            assert await seconds(app) == expected
            assert Progress(0, expected).voice == (10 if finish == 'rejoin' else 5)
    asyncio.run(scenario())

def test_same_person_guild_continuity_and_replay(tmp_path):
    async def scenario():
        async with harness(tmp_path) as (clock, bot, db, app, owner):
            await ready(bot, 'session-a')
            for g in (100, 200): await voice(bot, 2, str(g+1), guild=g)
            clock.tick += 35.75
            for g in (100, 200): await voice(bot, 3, str(g+2), guild=g)
            clock.tick += 600
            state = SimpleNamespace(self_mute=False, mute=False, self_deaf=False, deaf=False)
            bot.guilds[0].voice_channels = [SimpleNamespace(id=101, members=[SimpleNamespace(id=10, bot=False, voice=state)])]
            await ready(bot, 'replacement')
            await bot.emit('on_ready')
            clock.tick += 30.5
            await voice(bot, 2, None)
            await voice(bot, 2, None)
            await voice(bot, 1, '101')
            await packet(bot, 'RESUMED', 3, {})
            await app.stop()
            assert [await seconds(app, g) for g in (100, 200)] == [66, 0]
    asyncio.run(scenario())

def test_active_resume_and_disconnected_shutdown_timing(tmp_path):
    async def scenario():
        results = []
        # Synthetic ground truth: join 1000; move 1070; actual leave 1100.
        # Delayed case replays that leave at 1700, in the SAME resumed stream.
        for mode in ('connected-control', 'resume-delayed-leave', 'disconnected-stop'):
            case = tmp_path / mode
            case.mkdir()
            async with harness(case) as (clock, bot, db, app, owner):
                await seed(clock, bot)
                stream = owner.gateway.stream
                clock.tick = 1100
                if mode == 'connected-control':
                    await packet(bot, 'RESUMED', 4, {})
                    await voice(bot, 5, None)
                else:
                    await bot.emit('on_disconnect')
                    # User leaves now; disconnected transport cannot deliver yet.
                    clock.tick = 1700
                    if mode == 'resume-delayed-leave':
                        await voice(bot, 4, None)
                        await packet(bot, 'RESUMED', 5, {})
                        await voice(bot, 4, None)  # Replay duplicate must not add.
                assert owner.gateway.stream == stream
                await app.stop()
                actual = await seconds(app)
                results.append(dict(case=mode, seconds=actual, upper_bound=100,
                    xp=Progress(0, actual).voice, max_xp=5, faulted=app._voice_faulted))
        print(json.dumps(results))
        assert results[0]['seconds'] == 100
        # Conservative omission of unknown time is allowed; 600s known absence is not.
        assert all(row['seconds'] <= row['upper_bound'] and row['xp'] <= row['max_xp']
            for row in results[1:]), results
    asyncio.run(scenario())
```
