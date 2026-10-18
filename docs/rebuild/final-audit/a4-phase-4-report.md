# FINAL AUDIT A4 — Phase 4 Engagement

Date: 2026-10-02. **FAIL — A4-M1 MATERIAL, OPEN.** Audit stopped after reproduction;
no implementation/test repair, A5, Integrated Audit or Phase 11 work performed.

## Candidate and authority

- Candidate HEAD: `8498f7001e4b790e1fb14219a7d2a6c575ba14e7`.
  This audit covers current worktree code and scoped current documents, not HEAD alone.
- Entry matched the supervisor handoff exactly: **11 modified tracked / 59 untracked
  files, empty index**. [Exact entry paths, statuses and SHA-256 inventory](a4-entry-inventory.json).
  No unexpected mutation or authority contradiction was observed before documentation writes.
- Read active-state, ledger and document index first. Latest active-state AC and the
  explicit A4 assignment supersede historical NEXT SESSION instructions. A0–A3 remain
  PASS; this result changes only Phase 4. Root AGENTS.md applies; no `.agents` or `.codex`
  directory or nested tracked AGENTS.md/SKILL.md was present. No applicable local audit
  skill was found. `rg` was unavailable; scoped PowerShell/Python/Git reads were used.
- Exact scope from B20 Phase 4: **low-risk engagement — profile/rank/text/voice XP,
  birthday behind routes; formula/policy and guild isolation gates**. F029–F036,
  FR-031–037, with shared command/publicness/master/lifecycle/data constraints.
  Summary, Watch, Music and operations are dependencies/exposure only, not audited here.
- Governing comparison: [B20 roadmap](../baseline/20-migration-plan.md),
  [B12 FR-031–037](../baseline/12-functional-requirements.md), B08 BR-010/011/012,
  [C1 Engagement characterization](../phases/phase-01/characterization-contracts.md),
  [C6 Engagement contract](../phases/phase-04/engagement-contract.md),
  [ADR-013/015/017/018/019](../current/architecture-decision-log.md),
  scoped D22/T and product-spec XP/birthday sections. C3/C4 define inherited
  supervisor/storage boundaries; their prior PASS is not proof of Engagement behavior.
- Compared the [historical Phase 4 report](../phases/phase-04/phase-4-report.md), current
  domain/application/ports/SQLite/Discord/scheduler/composition and Engagement tests.
  The full ledger's governing list remains the routing map. Since a material defect
  triggered STOP, this report does **not** claim every remaining gate independently verified.

## A4-M1 — stale voice session accrues time after a new READY says user is absent

**Severity: MATERIAL. Root cause: missing reconciliation of absent voice members at
Gateway session replacement.** User-visible impact: durable voice seconds, XP, level
and ranking can be inflated after an ordinary lost-session reconnect. A normal later
shutdown or rejoin commits that inflation. This is not merely a display discrepancy.

Contract basis: FR-032 requires a guild/user's continuous voice session; C1 requires
unmuted duration and single settlement; C6 “Voice XP and lifecycle” requires observed
unmuted intervals, current-member READY seeding and preservation of **valid** duration
on a new Gateway session. A user absent from the authoritative new READY snapshot
cannot earn the following 600 seconds of voice presence. The reproduction intentionally
avoids choosing a policy for an unknown disconnect interval: all disputed time is
**after** the new READY, while the user is known absent.

Current path:

- `src/discordbot/engagement/adapters/discord_runtime.py:49` only replaces the stream
  hash for READY. `:67` seeds members that are present; it never closes prior rows
  absent from that snapshot. There is no invalidation/fault transition for this case.
- `src/discordbot/engagement/adapters/event_repository.py:91` extrapolates from an old
  unmuted row even when the next event has a different stream.
- The same file `:103`–`:114` flushes every remaining active row to shutdown time.
  `application/service.py:43` enables observed-only flush only after an application/DB
  voice error; the lost-session READY sequence produces none.
- `src/discordbot/composition/production_discord.py:36` constructs this same
  EngagementResource. This is a reachable current executable path, not a dead legacy
  adapter. No production observation or claim of actual affected users is made.

Synthetic reproduction uses real VoiceGateway → EngagementService → SQLite event
repository and schema/recovery, with a temporary DB, fake monotonic clock, fake guild
cache and synthetic IDs. It never logs in or calls the network:

1. In one process epoch, READY stream A; user 10 joins guild 100 channel 1001 at t=1000.
2. At t=1070 a move to channel 1002 persists a valid 70-second unmuted interval.
3. Transport/session is replaced after the user leaves; READY stream B and current
   guild voice-channel cache contain no occupants. Call `gateway.ready()`.
4. Advance 600 seconds with the user absent. Either stop the service, or rejoin for
   a fresh 61 seconds and leave, then stop.

| Settlement | Legitimate upper bound | Actual stored seconds | Voice XP upper bound / actual |
| --- | --- | --- | --- |
| Shutdown while absent | 70 | **670** | 5 / **55** |
| Rejoin for 61 seconds then leave | 131 | **731** | 10 / **60** |

Both cases assert the legitimate upper bound and fail. No assertion was weakened,
marked xfail or skipped. A4-M1 remains OPEN; no data correction or repair was attempted.

## Historical claims and later changes

The 2026-09-06 report records 95 focused PASS, 600 repeated concurrency PASS and
358 PASS / 9 xfailed at that time. Those are historical claims, not fresh evidence.
Its voice/replay/restart evidence does not cover an absent user across a replacement
Gateway session. In particular,
`test_voice_reconnect_new_stream_and_restart_do_not_invent_offline_time` creates a
**new process epoch**, which settles persisted duration through `begin_epoch`; it does
not exercise this same-process reconnect. Existing READY tests cover duplicate seeding
and a RESUMED packet after an already processed leave, not an unobserved leave followed
by a new READY. Historical broad PASS therefore does not close this gate.

The defect is already present in Phase 4 commits `089182b` / `60d09f5`; comparing
`60d09f5` to HEAD shows no event_repository change. The only subsequent Engagement
runtime change is A2 cleanup ownership (`d042e5e`), outside the faulty READY/accrual
logic. Phase 6/7 compatibility tests now expect migration version 5 rather than 3;
that is a later additive storage dependency, not a voice semantics supersession.
Production composition later wired the same resource into the full executable.

Phase 10B gate ledger rows 4/5 provide human confirmation of `/내정보` and `/랭킹`
for the recorded exact production release. They do not verify reconnect accounting,
voice accrual, birthday delivery or every Phase 4 contract. No scoped later decision
waiving the voice-presence requirement was found. No other phase is reclassified.

## Executed evidence and limits

1. Existing focused suite, repository `.venv`, credential boundary enabled:

   `.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`

   **81 PASS / 0 FAIL / 0 SKIP**, 5.13s, one known audioop deprecation warning.
   Reviewed temporary DB fixtures, mock sends, fake clock/barriers and cleanup first.

2. Independent probe below, saved only to `%TEMP%/discordbot-a4-probe/test_a4_voice_reconnect.py`:

   `.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4-probe\test_a4_voice_reconnect.py" --confcutdir="$env:TEMP\discordbot-a4-probe" -q -s --tb=no -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`

   **0 PASS / 2 FAIL / 0 SKIP**, 0.91s, completed exit 1. JSON observations above
   were emitted by the actual assertions. Source SHA-256:
   `6b9bec4ffae53f826ce771a573b8d8be2a907f13dd21164f9b3f80e6a77b7bd8`.
   An initial `--tb=short` attempt emitted both failures but did not finish reporting;
   that audit-owned runner was interrupted. Its incomplete run is not a separate test
   count. The completed `--tb=no` run is the authoritative probe result.

No full-suite rerun: MATERIAL STOP took precedence, and no implementation was changed.
The preceding A3V3 **1253 PASS / 2 known FAIL / 27 SKIP** is historical supporting
context only, not an A4 run or clean full-suite PASS. Focused/probe counts are distinct
selections; do not combine historical overlapping counts. No genuine Linux/process
requirement was needed to reproduce this application/SQLite defect, so WSL/systemd
was not accessed. No packages were installed or upgraded.

Known nonmaterial findings remain unchanged: A2-N1 stale document-inventory MINOR,
unrelated missing Deno test-path failure, audioop warning, A3-N1 stale product
connection description MINOR and A3-I1 historical Watch evidence INFO. None is a new
A4 blocker and none explains A4-M1.

## Documentation ownership, safety and next gate

Only this new report, the new safe entry inventory, the appended active-state A4
section, Phase 4 ledger row and a scoped document-index link belong to A4. Original
report/history and all other entry bytes are preserved. Existing dirty authority
files mix prior audit history; **no commit/stage/push** was made. Final expected state
is 11 modified tracked / 61 untracked files, empty index, same HEAD. Documentation
rollback means removing these A4 additions only; do not reset shared dirty files.

Production untouched: no SSH, credential/real-data access, deploy, DB write/restore,
replay/down-migration, V1 launch, concurrent writers, service/systemd/Cloudflare change,
or release/preservation/backup/history deletion. Recorded production source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`, remains distinct from the audit candidate.
Friend-guild configuration was not applied; rollout remains HELD. Normal production
writes were not disturbed; no older-state restoration is proposed. MyFood untouched.

**Next narrow recommendation: supervisor review, then separately authorize A4R1 for
Gateway replacement-session voice reconciliation**, preserving observed duration,
short-stay/mute/deaf/guild isolation, same-stream RESUME/replay and bounded ownership.
Specify the uncertainty boundary before implementing; add these regressions and
independently rerun A4 after repair. Do not silently repair historical XP or broaden
schema scope. A5 is not the next action while A4-M1 remains open. Integrated Audit,
Phase 11 and legacy cleanup remain unstarted and held.

## Exact audit probe source

Copy this source to the temporary path above and execute the recorded command from
this repository. It is audit evidence only, outside the repository test suite. It
uses root conftest's credential barrier before application imports and a new `tmp_path`
DB for each case. The ROOT constant identifies this inspected checkout.

```python
"""A4 audit evidence only: isolated new-READY voice reconciliation probe."""
import asyncio
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pytest

ROOT = Path(r"C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot")
runpy.run_path(str(ROOT / "conftest.py"))  # credential boundary before application imports
sys.path.insert(0, str(ROOT / "src"))
from discordbot.engagement.adapters.authorization import MasterAuthorization
from discordbot.engagement.adapters.discord_runtime import VoiceGateway
from discordbot.engagement.adapters.event_repository import SqliteEngagementEvents
from discordbot.engagement.adapters.sqlite_repository import SqliteEngagementRepository
from discordbot.engagement.application.service import EngagementService
from discordbot.engagement.ports.events import EngagementConfig
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

class Clock:
    tick = 1000.0
    def monotonic(self): return self.tick
    def now(self): return datetime(2027, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.tick)

@pytest.mark.parametrize("finish", ["shutdown", "rejoin"])
def test_new_ready_absent_member_cannot_accrue_voice_time(tmp_path, finish):
    async def scenario():
        clock = Clock()
        db = SqliteDatabase(DatabaseConfig(tmp_path / "synthetic.db"))
        await DataRecovery(db).bootstrap(DatabaseRequest.within(5))
        await db.start()
        app = EngagementService(SqliteEngagementRepository(db), SqliteEngagementEvents(db),
            MasterAuthorization(42), EngagementConfig(42), clock, "one-process")
        human = SimpleNamespace(bot=False)
        guild = SimpleNamespace(id=100, voice_channels=[], get_member=lambda uid: human)
        bot = SimpleNamespace(guilds=[guild], get_guild=lambda gid: guild)
        gateway = VoiceGateway(bot, app)
        async def ready(session):
            await gateway.receive(json.dumps({"op": 0, "t": "READY", "s": 1,
                "d": {"session_id": session}}))
            await gateway.ready()
        async def voice(seq, channel):
            await gateway.receive(json.dumps({"op": 0, "t": "VOICE_STATE_UPDATE", "s": seq,
                "d": {"guild_id": "100", "user_id": "10", "channel_id": channel,
                    "member": {"user": {"id": "10", "bot": False}}}}))
        try:
            await app.start()
            await ready("synthetic-old-stream")
            await voice(2, "1001")
            clock.tick += 70
            await voice(3, "1002")  # observed valid segment = 70 seconds
            # Lost transport/session; user left. New READY cache has no voice occupants.
            await ready("synthetic-new-stream")
            clock.tick += 600  # known absent for all 600 seconds after current READY
            expected_upper_bound = 70
            if finish == "rejoin":
                await voice(2, "1001")
                clock.tick += 61
                await voice(3, None)
                expected_upper_bound += 61
            await app.stop()
            row = await app.repository.get_member(100, 10, app.request())
            actual = 0 if row is None else row.total_vc_seconds
            print(json.dumps({"finish": finish, "actual_seconds": actual,
                "max_legitimate_seconds": expected_upper_bound,
                "actual_voice_xp": int(actual // 60) * 5,
                "max_legitimate_voice_xp": int(expected_upper_bound // 60) * 5}))
            assert actual <= expected_upper_bound, "absent user accrued phantom voice time after new READY"
        finally:
            await app.stop()
            await db.stop()
    asyncio.run(scenario())
```
