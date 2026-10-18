# A4R1 — replacement Gateway voice reconciliation

2026-10-02. **A4R1 PASS — local remediation candidate only. PHASE 4 remains FAIL.**
A4-M1 is remediated, pending independent A4V1; it is not independently CLOSED.
This is the single authorized A4R1 microphase, not an A4 re-audit or A5.

## Authority and candidate

- Entry HEAD: `8498f7001e4b790e1fb14219a7d2a6c575ba14e7`.
- Final local candidate/HEAD: `f0a4a07817a27b5c5327a2ba43679d314c98f822`.
  Commit: `fix: reconcile voice sessions on replacement Gateway READY`.
- Read active-state, ledger and document index first, then the independent
  [A4 report](a4-phase-4-report.md), its inventory, B20 Phase 4, C6 voice lifecycle,
  FR-031–037, C1, scoped ADR-013/015/017/018/019 and historical Phase 4 report.
  The supervisor's explicit narrow remediation approval supersedes the earlier
  audit-only STOP; it does not authorize re-audit, rollout or contract changes.
- Root AGENTS.md applies. No nested tracked instructions or applicable local skills,
  `.agents` or `.codex` directory found. No subagents used. `rg` is unavailable;
  scoped Git/Python/PowerShell reads were used instead.
- [Entry ownership inventory](a4r1-entry-inventory.json): **11 modified tracked /
  61 untracked files, index empty**, exactly matching the handoff. Prior A4 inventory
  hashes matched except its explicitly recorded A4 authority additions. Before A4R1
  documentation edits, every inherited entry file remained byte-identical.

## Causal change and lifecycle boundary

The former raw READY callback changed only an in-memory stream hash. Absent prior
rows remained active; both a later event in a new stream and shutdown extrapolated
from their old timestamps. The result was phantom time after authoritative absence.

The fix uses the existing writer transaction and schema:

1. Raw READY records the current stream synchronously in the service. Shutdown before
   the delayed cache-ready callback can settle older-stream observations but cannot
   extrapolate those rows into the replacement session.
2. `on_ready` takes one cache snapshot without awaiting and submits one transactional
   reconciliation plus sequence-zero seeding. An absent prior-stream row settles only
   its persisted duration (existing >=60-second/integer policy) and is removed.
3. A present prior-stream row retains its observed duration, including sub-minute and
   fractional duration, and rebases at the new observation. `_apply_voice` never adds
   elapsed time across distinct streams. Current-stream sequenced events and leave
   tombstones take precedence over snapshot seeds, preserving replay/idempotence.
4. A later absent-user rejoin starts fresh; two separate short stays do not combine.
   Guild/user keys preserve same-user multi-guild isolation.
5. Snapshot settlement and seeding commit or roll back together. Capacity/DB failure
   or cancellation uses the existing fail-closed voice admission and observed-only
   flush semantics. Queued transactions precede the shutdown flush in the existing
   writer lane; closed admission prevents late snapshot resurrection.

Implementation references: `discord_runtime.py:40,68`, `service.py:40,47,53`,
`event_repository.py:86,109,135`, plus the typed `VoicePresence`/event port.
No schema/migration/backup format, XP formula, grants, commands, permission or
publicness change. No historical XP repair and no V1 code change.

**Uncertainty boundary:** a transport disconnect alone is not proof of a user's
leave. Same-stream RESUMED/replay handling remains as contracted; this remediation
addresses replacement READY. Across a replacement stream, the interval after the
last persisted observation is not invented, even for a currently present member.
Stored observed duration is retained. The exact departure/rejoin time during a lost
Gateway session cannot be recovered from the replacement snapshot. This implements
C6/ADR-019 observed-duration semantics, not a new offline-credit policy. It does not
claim a separate audit of disconnect-without-READY or timestamp accuracy on RESUME.

The installed discord.py source was inspected locally: raw receive is dispatched
as a callback and `parse_ready` clears/rebuilds the guild cache, with a delayed ready
callback after guild loading. Therefore raw READY cannot safely enumerate the old
cache; reconciliation belongs to the completed ready snapshot. No network was used.

## Executed RED and PASS evidence

All tests used the existing Windows repository `.venv`, root credential barrier,
synthetic IDs, fake clocks/cache/send, temporary SQLite databases and bounded worker
barriers. No packages installed, production data read, Discord login or WSL needed.

1. Before implementation, new exact regression assertions:

   `.venv\Scripts\python.exe -m pytest tests/integration/engagement/test_voice_reconnect.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`

   **0 PASS / 2 FAIL / 0 SKIP**, exit 1, 0.34s. Shutdown: `670 != 70`;
   rejoin/leave: `731 != 131`. These reproduce independent A4-M1 exactly.

2. Initial fix with the existing focused selection plus the two original regressions:
   **83 PASS / 0 FAIL / 0 SKIP**, 5.31s. An intermediate boundary selection then
   passed **12 PASS / 0 FAIL / 0 SKIP**, 1.55s; cancellation coverage was added afterward.

3. Final focused plus directly affected dependency checks:

   `.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py tests/architecture/test_import_rules.py tests/integration/watch/test_cleanup_ownership.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`

   **120 PASS / 0 FAIL / 0 SKIP**, exit 0, 7.79s; one known audioop deprecation.
   Selection = 81 existing focused + 13 new regressions + 26 architecture/cleanup
   dependency cases. The two added dependency modules are justified by the changed
   application/port boundary and the production aggregate's Engagement lifecycle.
   No full-suite rerun was needed for this bounded change under the scoped instruction.

4. Exact independent A4 probe source copied from its report, unmodified, to
   `%TEMP%/discordbot-a4r1-probe/test_a4_voice_reconnect.py`:

   `.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a4r1-probe\test_a4_voice_reconnect.py" --confcutdir="$env:TEMP\discordbot-a4r1-probe" -q -s --tb=no -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`

   **2 PASS / 0 FAIL / 0 SKIP**, exit 0, 0.34s. Actuals: **70 seconds / 5 voice XP**
   and **131 seconds / 10 voice XP**. Source SHA-256 still
   `6b9bec4ffae53f826ce771a573b8d8be2a907f13dd21164f9b3f80e6a77b7bd8`.
   Rerunning this old probe is remediation evidence, not fresh independent verification.

The 13 committed regressions cover both original outcomes; pending READY shutdown;
continuous sub-minute preservation versus departed short stays across guilds; all
four mute/deaf flags; sequenced events/tombstones before snapshot; repeated replacement
and rejected stale callbacks; transaction rollback on capacity failure; queued
reconciliation then flush; and cancellation rollback with observed-only shutdown.
Existing RESUME, same-stream replay, restart epoch, fractional stored data, formula,
profile/rank, birthdays, encrypted metadata roundtrip and composition tests passed.
Selections overlap; do not add intermediate counts together.

No clean full-suite claim. A3V3's 1253 PASS / 2 known FAIL / 27 SKIP remains historical.
Known A2-N1 inventory, missing Deno, audioop, A3-N1 connection-description and A3-I1
historical Watch evidence remain unchanged. A0–A3 retain their prior PASS status.

## Ownership, rollback and safety

- Commit contains exactly four Engagement implementation files and
  `tests/integration/engagement/test_voice_reconnect.py`: **5 files, +384/-37**.
  Reviewed the code diff and staged test diff, verified staged file ownership and
  equality with the tested worktree, and ran `git diff --cached --check` successfully.
  The sandbox initially denied `.git/index.lock`; narrowly scoped staging/commit
  escalation succeeded. There was no automatic approval rejection or remote action.
- Uncommitted A4R1 evidence: this report and the entry inventory. Scoped additions
  only to mixed `CHANGELOG.md`, active-state, Phase 4 ledger row and document index.
  The original A4 report/inventory and all other inherited files are preserved.
  Final expected working tree: **11 modified tracked / 63 untracked, empty index**.
- Rollback is a normal revert of the local candidate commit after review; remove only
  the explicitly marked A4R1 documentation additions if rolling back docs. Do not reset
  shared dirty files, rewrite history, restore old data or down-migrate metadata.
- Production documentary source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
  `r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and unchanged. No production
  access, credentials/data, deploy, DB write/replay/restore, stop/restart, V1 launch,
  concurrent writers, systemd, Cloudflare, remote push or cleanup. MyFood untouched.
- Friend guild `1380554661140103298` (main `1380554661140103300`, music
  `1380554661597155328`) remains **HELD**; no activation or config write occurred.

## Remaining gate and proposed A4V1

**A4R1 PASS; PHASE 4 FAIL; A4-M1 pending independent closure.** No implementation
blocker remains in this microphase. Actual Gateway/Pi behavior and deployment were
not exercised; unknown lost-session intervals remain intentionally uncredited.

After supervisor review, independently inspect this exact candidate and current
worktree against B20/C6/approved ADR and F029–F036/FR-031–037. Reproduce the original
absent-user shutdown/rejoin cases independently; challenge continuous occupancy,
short-stay/guild isolation, repeat READY/RESUME/replay, pre-ready events, failure/
cancellation and queued shutdown. Complete the Phase 4 gates left unverified by the
original material STOP, including profile/ranking parity, birthday delivery and
lifecycle/data compatibility. Verify test isolation and doc ownership. Only that
fresh A4V1 may close A4-M1 and decide Phase 4 PASS. A5, Integrated Audit, Phase 11,
friend activation and deployment remain unstarted/held. **STOP after A4R1.**
