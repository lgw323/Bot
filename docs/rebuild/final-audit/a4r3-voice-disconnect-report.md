# A4R3 - disconnected voice time remediation

2026-10-02. **PASS for local remediation; PHASE 4 remains FAIL pending independent
A4V3.** M1/M2 remain independently CLOSED. M3 is remediated, not independently
CLOSED. Stop after this microphase; parent review and fresh A4V3 are separate work.

## Authority and candidate

Read current active-state AH, Phase 4 ledger and document index before A4V2's report
and exact committed probe; then B20 Phase 4, C1 F030/FR-032, C6 voice lifecycle,
ADR-013/015/017/018/019, historical Phase 4/A4 remediation evidence and current code.
Root AGENTS.md applies; no nested scoped instructions or applicable local skill.
The explicit user authorization permits this single narrow remediation and local
evidence commits, not a new audit, product policy or production action.

- Entry HEAD: `380b3156391eacdafdff32ccc4f3762924a014a3`, `codex/rebuild-v2`.
- Prior audited runtime: `7ead8a2fae5501f384c26e6d894e5b6ca9a906e9`.
- Implementation: `3aa5f73919967a7d41d509c75db627637d37c46c` (five files,
  +372/-4: two runtime files, 15 new regressions, one cleanup fake adjustment and
  only the A4R3 changelog entry).
- Historical evidence preservation: `914367d53d8689ef1afba5da0a805574fd61974d`.
  Eight A4/A4R1/A4V1/A4R2 reports/inventories match the committed A4V2 inventory;
  their historical counts/statuses are retained verbatim, not re-certified today.
- This report, [entry inventory](a4r3-entry-inventory.json), active-state AI and only
  the Phase 4 ledger row form a separate documentation commit after implementation.

## Exact cause and minimal remedy

EngagementResource had no disconnect listener; VoiceGateway ignored RESUMED.
Same-stream SQL used receipt-time monotonic ticks for replayed events and normal
shutdown extrapolation. Sequence dedupe prevented duplicate writes, but could not
remove the disconnected interval already included in duration. Thus a leave that
occurred at disconnect 1100 but arrived at 1700, or stop at 1700 while disconnected,
settled 700 seconds / 55 XP instead of at most 100 seconds / 5 XP.

Inspected installed discord.py **2.7.1** Client.connect, Bot.dispatch,
Client._schedule_event, DiscordWebSocket.received_message and parse_resumed locally.
Disconnect is dispatched on reconnect paths; raw payload listeners are scheduled
as tasks. The [Discord Gateway contract](https://docs.discord.com/developers/events/gateway#resuming)
specifies ordered replay followed by RESUMED, after which dispatches are new.
Socket connection alone therefore cannot mark the end of historical replay.

The service now keeps two process-local lifecycle scalars: the first disconnect
tick and cumulative excluded gap seconds. All voice events, READY snapshots and
shutdown use the same monotonic timeline with those gaps removed. During a gap,
replayed updates retain their real stream/sequence and state transitions but share
the frozen disconnect tick; their receipt latency contributes zero elapsed time.
RESUMED reopens live accrual. Replacement raw READY also reopens the timeline while
retaining M1's existing cross-stream reconciliation and persisted-only settlement.
Repeated disconnect/RESUMED notifications cannot move the boundary or add a gap twice.

The captured disconnect tick preserves connected time through that observation;
no original event timestamp is invented. A replayed leave settles the old stay,
a replayed join starts with zero elapsed time, and post-RESUMED live time accrues
normally. Fractional duration and guild/user keys remain in the existing SQLite
owner. No SQL, schema, migration, XP formula, command, permission or capacity changed.

Every lifecycle transition and event tick is captured before its first await.
M2's observation drain and fault policy stay intact: failed/cancelled observations
still fail closed and flush persisted duration only; RESUMED never clears that flag.
Stop captures its adjusted tick before draining, so delayed SQL completion cannot
earn time. Late callbacks cannot reopen closed admission. Listener removal includes
disconnect. No extra task, queue, global lock or per-user in-memory store was added.

Limits: this is the observed callback boundary, not proof of physical packet-loss
onset or historical departure timestamps. Unobservable gap time is omitted even
for a member who stayed present. M1 still settles only persisted prior-stream
duration on replacement READY. Crash recovery still uses persisted duration only.
No live Gateway, Discord HTTP, Pi or whole-system timing proof is claimed.

## RED and resulting checks

All completed runs used the existing Windows `.venv`, credential boundary, synthetic
IDs, temporary SQLite and fake clocks/transport. The SDK dispatch regression initializes
a real Bot offline, without login/network. Resources/tasks/listeners are cleaned up.

1. Extracted A4V2's committed Python block without edits to
   `scratch/a4r3/test_a4v2_exact.py` (ignored local reproduction artifact).
   SHA-256 stayed `458ef4d61918962dd1c8dc83c16780034ed2e9b99aadb4e6d68f014945df2a83`.
   Before editing runtime:
   `.venv\Scripts\python.exe -m pytest -c pyproject.toml scratch/a4r3/test_a4v2_exact.py -q -s -k active_resume_and_disconnected_shutdown_timing`
   produced **0 PASS / 1 FAIL / 0 SKIP, 15 deselected**, 0.91s. Connected control:
   100s/5 XP; delayed leave and disconnected stop: **700s/55 XP each**.
2. First 12 new regressions before runtime edits: **5 PASS / 7 FAIL / 0 SKIP**, 1.90s.
   After repair, those 12 plus unchanged original 16 probes: **28 PASS / 0 FAIL /
   0 SKIP**, 4.09s. Exact M3 outputs were **100s/5 XP for all three modes**.
   Assertions, limits and original probe synchronization were not changed.
3. Final focused selection, including three further adjoining-order regressions:
   `.venv\Scripts\python.exe -m pytest tests/integration/engagement/ tests/characterization/test_engagement_contracts.py scratch/a4r3/test_a4v2_exact.py -q`
   **136 PASS / 0 FAIL / 0 SKIP**, 13.07s: 105 existing focused cases, 15 new cases,
   16 unchanged A4V2 cases. M1/M2, replay/idempotence and same-user guild isolation pass.
4. Direct dependency checks for the changed application boundary and listener cleanup:
   `.venv\Scripts\python.exe -m pytest tests/architecture/test_import_rules.py tests/integration/watch/test_cleanup_ownership.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
   Initially **25 PASS / 1 FAIL / 0 SKIP**: the cleanup fake lacked `disconnected`.
   Added only that fake attribute; original ownership assertions stayed unchanged.
   Final **26 PASS / 0 FAIL / 0 SKIP**, 1.71s. These 26 and the final 136 are disjoint;
   intermediate selections overlap and must not be added again.

Two preliminary external-temp invocations were runner issues, not runtime findings:
one stalled before reporting and was interrupted; one collected an inaccessible
Windows ancestor and ended with **1 collection ERROR**, no test verdict. The identical
source then ran successfully from the isolated ignored scratch directory above.

No full-suite rerun or clean-suite claim. Known inventory/Deno failures are not fixed
or reclassified. The audioop deprecation warning appeared in the completed runs.
A3-N1 connection-description MINOR and A3-I1 historical Watch INFO remain unchanged.
No package installation, WSL reuse or actual application data access was needed.

## Ownership, rollback and stop boundary

Entry inventory is exactly **11 modified / 67 untracked, empty index**. All 78
inherited hashes matched before scoped documentation edits. The three shared files
(changelog, active-state, ledger) retain their inherited content; index staging uses
HEAD plus only A4R3 changes. Mixed document index, prior authority/history and unrelated
files stay uncommitted. Eight separable inherited A4 evidence files are now committed;
expected remaining tree is **11 modified / 59 untracked, empty index**. No inherited
file was deleted, overwritten with HEAD or bulk-staged. Staged diffs, tested-source
equality and `git diff --cached --check` were inspected before commits. Initial sandbox
index-lock denial was resolved by scoped authorized escalation; no review rejection.

Rollback is a reviewed ordinary revert of the implementation commit; evidence commits
are independently revertible documentation. Preserve mixed worktree changes. No data
rollback, schema rollback, reset, force push or history cleanup.

Production remains separately recorded at source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`. No production/Pi access, deployment, restart,
DB writes/restore, V1/concurrent writers, systemd/Cloudflare or remote push occurred.
Friend rollout remains HELD; My Food is paused. Conditional deployment approval still
requires all final audits including Integrated Audit PASS and is not actionable here.

**Next: parent review, then fresh independent A4V3 only.** Verify exact unchanged M3
probe, replay bursts with leave/rejoin/mute, repeated gaps, real SDK callback ordering
and delayed transactions across RESUMED/shutdown; retain M1/M2 fault and READY gates,
fractional/short-stay accounting and same-user guild isolation. Distinguish synthetic
proof from live transport limits. Only that independent audit may close M3 and change
Phase 4's verdict. No independent audit was started here. A5, Integrated Audit,
Phase 11, release cleanup and My Food were not resumed. **STOP A4R3.**
