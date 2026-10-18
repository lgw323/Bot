# A4V1 - independent Phase 4 verification

2026-10-02. **A4V1 FAIL; PHASE 4 FAIL. A4-M1 CLOSED in its original replacement-READY scope; A4-M2 MATERIAL OPEN.**
This single independent microphase stopped on a newly reproduced failure. No remediation or A5 started.

## Candidate, authority and ownership

Exact entry/final HEAD: `f0a4a07817a27b5c5327a2ba43679d314c98f822`, a local candidate, not deployed.
Its commit contains four implementation files and one regression test, +384/-37.
[Entry inventory](a4v1-entry-inventory.json) records all inherited paths/statuses/SHA-256:
**11 modified tracked / 63 untracked, index empty**, exactly matching the delegation.
All inherited file hashes remained identical immediately before documentation edits; HEAD/index also matched.
No active writer or authority drift was observed. The only tracked instruction file is root AGENTS.md;
no nested instructions were found in the scoped source/tests/docs, and no listed local skill applies to this code audit.
`rg` and bare `python` are unavailable; scoped Git/PowerShell and the existing `.venv` Python were used.

Read current active-state, ledger and document index first, then B20 Phase 4, B03 F029-F036,
B12 FR-031-037, C1 Engagement/command preservation, C6, and ADR-013/015/017/018/019.
Compared original Phase 4 report, [A4 failure](a4-phase-4-report.md),
[A4R1 remediation](a4r1-voice-reconnect-report.md), current source/tests and relevant later history.
C6/ADR-019 require observed-only shutdown after uncertain/failed voice observation and serialization
with preceding writes. No scoped supersession waives this rule. A4R1 explicitly left disconnect-without-READY
and RESUME timestamp accuracy for independent review.

Later changes include nested cleanup ownership (`d042e5e`), executable composition using the same
EngagementResource, and additive migration versions 4/5 from other contexts. These do not supersede
voice accounting. Phase 10B profile/ranking evidence is historical and narrower than Phase 4 closure;
no historical PASS was counted as a fresh result.

## MATERIAL A4-M2 - shutdown captures failure policy before preceding voice work resolves

**Expected:** when an admitted voice observation fails, the final flush settles only persisted observed
duration. Closing admission and ordering SQL operations must not bypass that failure decision.
**Actual:** `EngagementService.stop()` evaluates `_voice_faulted` before awaiting the writer lane.
An earlier admitted voice transaction can still be waiting and later fail. The service then sets
`_voice_faulted=True`, but the already queued flush retains `observed_only=False`, extrapolates stale
unmuted state, writes excess seconds/XP, and removes the runtime/session metadata.

Relevant current paths:
- `src/discordbot/engagement/application/service.py:40` captures the flag at stop submission;
  `:77-92` sets it only after the failed observation returns. READY failure has the same flag pattern at `:53-67`.
- `src/discordbot/engagement/adapters/event_repository.py:135-148` captures the boolean in the flush closure;
  writer serialization preserves SQL order but cannot refresh that value.
- `src/discordbot/engagement/adapters/discord_runtime.py:123` calls this service on resource shutdown;
  production composition constructs this same resource at `composition/production_discord.py:36`.

Independent deterministic reproduction uses real service/Gateway/SQLite code, one temporary DB,
a fake clock, a bounded writer barrier and an injected typed transaction failure after the real mute
transition executes. The exception rolls that transition back; no production data or network is involved.

1. At monotonic 1000, join unmuted. At 1070, move while unmuted: persist **70 observed seconds**.
2. Hold the writer lane. At 1100, admit a mute event; its transaction is queued first.
3. At 1700, submit shutdown while that observation is unresolved; its flush queues second.
4. Release the barrier. The mute transaction fails/rolls back and marks the service faulted.
5. Flush still extrapolates from 1070 to 1700. Durable result: **700 seconds / 55 voice XP**,
   required **70 seconds / 5 voice XP**: **630 excess seconds / 50 excess XP**.

Observed JSON:
```json
{"case":"failed-observation-races-stop","faulted":true,"seconds":700,"expected":70,"xp":55,"expected_xp":5}
```

This violates C6 Voice XP/lifecycle, ADR-019 and FR-032/CF-17/20. It affects durable XP and downstream
profile/ranking, so is MATERIAL. It is a distinct pre-existing failure/flush race, not evidence that
the narrow replacement-READY fix failed. `git show` of recorded production source
`8e9018d4b8061cde6006eee47fa4103522f77718` confirms the same early boolean capture, post-failure flag
assignment and flush extrapolation condition. This is source-level exposure only: no live occurrence,
production data discrepancy, or runtime reproduction is claimed. No historical XP repair is authorized.

Existing `test_failed_voice_observation_stops_extrapolation_at_shutdown` waits for failure before
calling stop. A4R1 cancellation test also resolves failure before stop; its queued shutdown test has
successful reconciliation. Those pass but miss this combination. No existing assertion was changed.

## Fresh executed evidence and scoped coverage

Isolation was reviewed first: root credential barrier disables dotenv/clears application settings;
repository test fixtures redirect V1 DB/backup to temporary paths; inspected cases use temporary SQLite,
fake clocks/Discord sends, bounded barriers and resource cleanup. No package installation was needed.

1. Focused repository selection:
   `.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
   **94 PASS / 0 FAIL / 0 SKIP**, exit 0, 6.67s; one known audioop deprecation warning.
2. New independent probe (source preserved below):
   `.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4v1-probe\test_a4v1_independent.py" --confcutdir="$env:TEMP\discordbot-a4v1-probe" -q -s --tb=no -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
   **4 PASS / 1 FAIL / 0 SKIP**, exit 1, 0.68s. Five distinct collected cases; stopped after this material result.

Do not sum these with A4/A4R1 or earlier runs. No full suite, dependency expansion, repeat soak or Linux
run followed the MATERIAL STOP. Earlier 1253 PASS / 2 known FAIL / 27 SKIP is historical only.
No clean full-suite PASS is claimed. A2-N1 inventory, Deno absence, audioop, A3-N1/A3-I1 remain unchanged.

| Scoped gate | Fresh evidence and disposition |
| --- | --- |
| Original A4-M1 absent READY/shutdown and rejoin | Independently **70s/5 XP** and **131s/10 XP**; pending cache-ready shutdown also **70s/5 XP**. **A4-M1 CLOSED only for this defined defect.** |
| Replacement continuity, repeated READY/replayed writes, same person in two guilds | Independent observed 35.75s retained for present guild, unobserved 600s omitted, another 30.5s yields 66s; absent guild's separate 35.75/59.9s stays yield 0. Duplicate leave, older join, repeat snapshot and RESUMED packet do not revive rows. Existing 13 A4R1 regressions also pass in the focused run. |
| Failure/flush/shutdown ownership | Existing sequential failure/cancellation and successful queued flush cases pass; new overlapping failed observation + stop **FAIL A4-M2**. No comprehensive ownership closure. |
| Disconnect without replacement READY; active-session RESUME/rejoin timing | **Not completed after MATERIAL STOP.** Existing/new RESUMED tests prove stream/replay idempotence only; they do not simulate a real disconnected interval or replayed historical event timing. No PASS inferred. |
| Text XP (F029/FR-031) | Fresh policy/event/failure tests cover 11,172 Hangul syllables vs V1, Jamo/whitespace, level curve, bot/DM exclusion, duplicate/concurrent receipt+XP, restart replay, capacity/busy/cancellation, same-user guild separation. Reviewed policy/service/transaction code agrees. |
| Profile/ranking (F031-032/FR-032-033) | Fresh V1 signature checks, private self/master-other behavior, missing/DM/guild separation, completed-minute parity, TOP 10/ties and requested visibility pass. A4-M2 can still corrupt their underlying voice totals. |
| Birthdays (F033-036/FR-034-037) | Fresh master/calendar/Feb-29-century/KST tests, registration/deletion/list guild separation, list chunking, configured-channel guild validation, repeated daily claims, send/ACK failure, cancellation and scheduler ownership pass. Evidence is synthetic; no real birthday send. |
| Data/composition boundaries | Fresh temporary copy/old reader/full encrypted metadata roundtrip, fail-closed metadata validation, explicit migration startup, real offline Bot construction and lifecycle cleanup pass. No schema/formula changes in A4R1 diff. Later migration version 5 is preserved. |

Remaining Phase 4 closure requires resolving A4-M2 and independently checking the failed race plus the
uncompleted disconnect/RESUME uncertainty cases. The focused suite supplies fresh evidence for other
engagement gates but cannot override the material failure. Actual Gateway, Discord HTTP and Raspberry Pi
behavior were not exercised; zero operational risk is not claimed. A0-A3 PASS status is retained;
A5-A10 remain NOT_AUDITED. No other phase is reclassified.

## Safety, owned documentation and next boundary

Owned changes: this new report, new entry inventory, appended active-state AF and index section,
and replacement of only the Phase 4 ledger row. All other inherited bytes, original reports/history,
implementation/tests and dependencies are preserved. Expected final tree **11 modified / 65 untracked**,
empty index, same HEAD. No staging/commit/push. Documentation rollback removes these named A4V1 additions
and restores only the prior Phase 4 row; never reset the shared dirty documents.

Production is untouched: no host/credential/real-data access, deploy/restart, DB write/restore/replay,
down-migration, V1 or concurrent writer, systemd/Cloudflare operation, release/backup/history cleanup.
Recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain distinct from the candidate.
Friend guild `1380554661140103298`, main `1380554661140103300`, music `1380554661597155328`
remain **HELD**, with no activation/configuration write. MyFood is unrelated and untouched.

**Next narrow boundary:** parent review, then separately authorize A4R2 for pending voice-observation
outcome ownership at shutdown. Ensure failed/cancelled preceding work cannot leave a stale extrapolating
flush decision; preserve successful observed continuity, bounded cleanup and schema/formula. Independent
A4V2 must follow. No repair, design expansion, A5, rollout, Integrated Audit or Phase 11 is started here.

## Exact independent probe source

Temporary source SHA-256: `2ecb25bc68a01dd726167e6d6cfb73e517e215ed63df5f87fe70705b7924df56`.
Copy to the temporary path above and run the recorded command. This is audit evidence, not a repository
test-suite modification. Failure injection and barriers are confined to the synthetic test process.

```python
"""Independent A4V1 evidence; synthetic database and fake Gateway, no network."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import sys
import threading
from types import SimpleNamespace
import pytest
ROOT = Path(r"C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot")
runpy.run_path(str(ROOT / "conftest.py"))
sys.path.insert(0, str(ROOT / "src"))
from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.discord_runtime import VoiceGateway
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.platform.errors import DatabaseUnavailableError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

class Clock:
    tick = 1000.0
    def monotonic(self): return self.tick
    def now(self): return datetime(2027, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.tick)

@asynccontextmanager
async def harness(tmp_path):
    clock = Clock()
    db = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
    await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
    await db.start()
    app = EngagementService(SqliteEngagementRepository(db), SqliteEngagementEvents(db),
        MasterAuthorization(42), EngagementConfig(42), clock, "independent-a4v1")
    guilds = [SimpleNamespace(id=g, voice_channels=[], get_member=lambda u: SimpleNamespace(bot=False)) for g in (100,200)]
    bot = SimpleNamespace(guilds=guilds, get_guild=lambda g: next(x for x in guilds if x.id == g))
    gateway = VoiceGateway(bot, app)
    await app.start()
    try: yield clock, db, app, gateway
    finally:
        await app.stop()
        await db.stop()

async def packet(gateway, kind, seq, data):
    await gateway.receive(json.dumps(dict(op=0,t=kind,s=seq,d=data)))
async def ready(gateway, name, snapshot=True):
    await packet(gateway,"READY",1,dict(session_id=name))
    if snapshot: await gateway.ready()
async def voice(gateway, seq, channel, guild=100, muted=False):
    await packet(gateway,"VOICE_STATE_UPDATE",seq,dict(guild_id=str(guild),user_id="10",channel_id=channel,self_mute=muted,member=dict(user=dict(id="10",bot=False))))
async def seconds(app,guild=100):
    row=await app.repository.get_member(guild,10,app.request())
    return 0 if row is None else row.total_vc_seconds

def occupants(gateway, guild_ids):
    for guild in gateway.bot.guilds:
        state=SimpleNamespace(self_mute=False,mute=False,self_deaf=False,deaf=False)
        member=SimpleNamespace(id=10,bot=False,voice=state)
        guild.voice_channels=[SimpleNamespace(id=guild.id+1,members=[member])] if guild.id in guild_ids else []

@pytest.mark.parametrize("finish",["shutdown","rejoin","pending-ready"])
def test_original_absence_independent(tmp_path,finish):
    async def scenario():
        async with harness(tmp_path) as (clock,db,app,gateway):
            await ready(gateway,"before")
            await voice(gateway,2,"101")
            clock.tick+=70
            await voice(gateway,3,"102")
            await ready(gateway,"replacement",snapshot=finish!="pending-ready")
            clock.tick+=600
            expected=70
            if finish=="rejoin":
                await voice(gateway,2,"101")
                clock.tick+=61
                await voice(gateway,3,None)
                expected=131
            await app.stop()
            observed=await seconds(app)
            print(json.dumps(dict(case=finish,seconds=observed,expected=expected,xp=int(observed//60)*5)))
            assert observed==expected
    asyncio.run(scenario())

def test_continuity_two_guilds_and_replayed_writes(tmp_path):
    async def scenario():
        async with harness(tmp_path) as (clock,db,app,gateway):
            await ready(gateway,"before")
            for g in (100,200): await voice(gateway,2,str(g+1),guild=g)
            clock.tick+=35.75
            for g in (100,200): await voice(gateway,3,str(g+2),guild=g)
            clock.tick+=600
            occupants(gateway,{100})
            await ready(gateway,"replacement")
            await gateway.ready()
            clock.tick+=30.5
            await voice(gateway,2,None)
            await voice(gateway,2,None)
            await voice(gateway,1,"101")
            await packet(gateway,"RESUMED",3,{})
            await gateway.ready()
            await voice(gateway,4,"201",guild=200)
            clock.tick+=59.9
            await voice(gateway,5,None,guild=200)
            await app.stop()
            actual=[await seconds(app,g) for g in (100,200)]
            print(json.dumps(dict(case="continuity-two-guilds-replay",seconds=actual,expected=[66,0])))
            assert actual==[66,0]
    asyncio.run(scenario())

def test_inflight_failed_observation_and_shutdown(tmp_path,monkeypatch):
    async def scenario():
        async with harness(tmp_path) as (clock,db,app,gateway):
            await ready(gateway,"stream")
            await voice(gateway,2,"101")
            clock.tick+=70
            await voice(gateway,3,"102")
            original_apply=app.events._apply_voice
            def injected_failure(conn,event,capacity):
                result=original_apply(conn,event,capacity)
                if event.sequence==4:
                    raise DatabaseUnavailableError("synthetic voice transaction failure")
                return result
            monkeypatch.setattr(app.events,"_apply_voice",injected_failure)
            loop=asyncio.get_running_loop()
            blocked=asyncio.Event()
            release=threading.Event()
            def hold(conn):
                loop.call_soon_threadsafe(blocked.set)
                assert release.wait(5)
            blocker=asyncio.create_task(db.write(app.request(),hold))
            tasks=[blocker]
            queued=asyncio.Queue()
            original_write=db.write
            async def observe_write(request,work):
                queued.put_nowait(True)
                return await original_write(request,work)
            try:
                await asyncio.wait_for(blocked.wait(),2)
                monkeypatch.setattr(db,"write",observe_write)
                clock.tick+=30
                # This mute observation is admitted first, fails in the writer transaction.
                tasks.append(asyncio.create_task(voice(gateway,4,"102",muted=True)))
                await asyncio.wait_for(queued.get(),2)
                clock.tick+=600
                tasks.append(asyncio.create_task(app.stop()))
                await asyncio.wait_for(queued.get(),2)
            finally:
                release.set()
                await asyncio.gather(*tasks)
            actual=await seconds(app)
            print(json.dumps(dict(case="failed-observation-races-stop",faulted=app._voice_faulted,seconds=actual,expected=70,xp=int(actual//60)*5,expected_xp=5)))
            assert app._voice_faulted
            assert actual==70, "shutdown must settle observed duration only after preceding observation fails"
    asyncio.run(scenario())
```
