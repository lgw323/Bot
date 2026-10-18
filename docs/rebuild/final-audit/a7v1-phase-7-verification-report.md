# A7V1 independent Phase 7 verification — FAIL

2026-10-03. **Phase 7 FAIL. A7-M1 independently CLOSED; A7-M2 MATERIAL OPEN.**
Stop for supervisor review and separate remediation. No implementation was changed.

## Identity, authority and entry

- Branch `codex/rebuild-v2`; entry/audited HEAD
  `9987e10896aaf11616edf228f7c2c010b6c0ae54`.
  A7R1 implementation `12a42ef9168da0540825fa1cb12f2c189da95411`.
  Original A7 target `3092f49ce82ac44232535b39b779718a5bd0f414`, evidence `04f6b8d`.
  Final audit-only commit is reported in the handoff.
- [Entry inventory](a7v1-entry-inventory.json): 11 modified / 59 untracked paths,
  70 SHA-256 hashes, empty index. Actual Git agrees with the briefing. Checkout
  `.agents/skills` and nested src/tests/docs AGENTS files are absent. Root AGENTS applies.
- Read current active-state, Phase 7 ledger row and document index; A7 report/probe,
  A7R1 report/regressions; original B20 Phase 7, B12 FR-011–025, B08 BR-003/005/007,
  relevant D22/Q-H05/H07/M01 and D23/ADR-022; C10/C11/C12 and canonical Phase 7 report.
  Reviewed relevant product music semantics, trace overlay, P2 gates 7–19 and retained
  V1 retry/next-song code. No accepted decision was found that makes a new song inherit
  the retired song's pause intent. Audit STOP rules supersede historical continuation.
- Recorded production source remains `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
  `r-8e9018d4b8061cde-3dac82a792fad576`. These are records, not a fresh host observation.

## A7-M1 disposition — independently CLOSED

The entire `src/` diff from original A7 to this target is the disconnect assignment:
retain `_resume_paused` OR current status `paused`, with its explanatory comment.
The original C11 contract retains pause/position within the same logical music session.
The change satisfies the original reported sequence without modifying its assertions.

- Unchanged A7 probe SHA-256:
  `5f81fc6ae055f27486a5d89d4fee6fe2729e1b9a2aeae0d0e08150df7b7ddba2`.
- Current source: original A7 2 PASS plus A7R1 20 cases PASS, 0 FAIL/SKIP/XFAIL.
- Independent negative control: [baseline launcher](a7v1-baseline-probe.py) loads the
  exact original Git actor blob into that process only. All other runtime source is
  identical; no checkout file is replaced. Original actor SHA-256
  `637775aea9a6e21415c45ae4a0d0f8aad359990e0c256936e1203a5a09bb58ac`.
  The unchanged A7 probe gives 1 PASS / 1 FAIL: `(False, 'playing', False, True)`.
  Current gives the expected `(True, 'paused', True, False)`.
- Reviewed real Cog voice routing, actor dispatch/work/attempt boundaries and audio
  start/stop/pause effects. A7R1's cases exercise playing/paused, TTS generation/start/
  completion/failure/between-announcements, observed cancellation, repeated reconnects,
  stale/duplicate end notifications, music preparation interruption, explicit resume,
  skip/leave/grace-expiry/close. The original two-guild probe confirms control isolation.
- This closes the precise M1 failure, not all session-termination combinations or Phase 7.
  A7R1's broader 201 PASS/1 Deno FAIL remains historical remediation evidence, not an
  independently rerun whole-phase gate. The new defect below is outside its 20 cases.

## A7-M2 — exhausted recovery carries pause into the successor session

**MATERIAL OPEN.** A paused song's reconnect recovery fails three times. The actor
correctly skips that song and assigns the queued successor a new logical session, but
then pauses the successor immediately, leaving the jukebox silent without a pause input
for that song. Playing-state control advances and plays normally.

[Minimal deterministic probe](a7v1-retry-exhaustion-probe.py), real MusicCog → MusicActor:

1. Two guilds each start synthetic song 1 with song 2 queued. Advance fake time 17s.
2. Pause target song 1, play TTS, deliver bot disconnect and reconnect via actual Cog.
3. Make only song 1 media acquisition fail. Verify first 3s and second 8s retry timers,
   retaining its original session. Wake each new retry using fake events.
4. Third failure retires song 1. Song 2 acquisition and audio start succeed.
5. Assert the successor has a new session, elapsed 0, empty remaining queue and normal
   playing/unpaused/audible effects. Other guild's session/audio remain unchanged.

| Observation | Expected | Actual |
| --- | --- | --- |
| Song 1 acquisition failures | 3 | 3 |
| First/second retry | 3s / 8s | 3s / 8s |
| New current/session | song 2 / new session | preserved |
| Successor elapsed / remaining queue | 0 / empty | preserved |
| Successor status / paused / synthetic audible | playing / false / true | **paused / true / false** |
| Playing-state control | song 2 playing | PASS |
| Other guild | original session still playing | PASS |
| Actor/supervisor/audio teardown | no owned work/audio | PASS |

Contract basis: B08 BR-005, B12 FR-015 and C10 retain 3s/8s/third-failure skip to
the next song; C11 scopes reconnect/TTS pause recovery to the same logical session.
The preserved next-song behavior is concrete in V1 `cogs/music/music_core.py:678–707`
(third failure removes the song and signals next playback), `:588–597` (starts the next
audio and resets pause timing). V2's existing `test_retry_exact_3_8_third_skip` also
expects the successor playing; A7R1's termination tests explicitly prevent pause leakage
on manual skip/leave/expiry/close but omit automatic exhaustion. This is a session-boundary
defect, not a request to abandon M1's pause preservation while retrying the same song.

Root cause in `src/discordbot/music/application/actor.py`: `_failed` at 240–242 calls
`_advance` after the third failure. `_advance` at 217–224 replaces current/session and
timing without retiring `_resume_paused`. `started` at 371–380 consumes that old flag
and pauses the new audio. Disconnect correctly preserves the flag at 457–459; reverting
A7R1 would reopen M1. The advance/reset helper is unchanged by A7R1. No pre-fix M2
execution or claim about all alternative exhaustion paths is made.

The historical Phase 7 report's retry and interruption claims cover separate scenarios;
P2 gate19 confirms pause restoration to the same song, not retry exhaustion into another.
Neither historical PASS establishes this missing combination. No finding here invalidates
recorded A0–A6 PASS; affected dependency contracts are session/count/snapshot consistency,
CF-03/05 and cleanup ownership, to be included in separate remediation verification.

## Fresh commands and counts

All use existing Windows venv, `PYTHON_DOTENV_DISABLED=1`, `PYTHONIOENCODING=utf-8`,
explicit `-c pyproject.toml`, `-q --tb=short`, and strict
`-W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.

| Execution | Result | Evidence |
| --- | --- | --- |
| `python -m pytest ... a7-paused-disconnect-probe.py tests/integration/music/test_tts_reconnect.py` | 22 PASS, 0 FAIL/SKIP/XFAIL; 0.41s | [focused XML](a7v1-focused-results.xml), session 71325 exit 0 |
| `python docs/rebuild/final-audit/a7v1-baseline-probe.py` | negative control 1 PASS / 1 FAIL; 0.41s | [baseline XML](a7v1-baseline-results.xml), session 9203 exit 1 |
| Initial new-probe harness | 0 PASS / 2 synchronization FAIL; 0.42s | [retained initial XML](a7v1-retry-harness-initial-results.xml), session 67216 exit 1 |
| `python -m pytest ... docs/rebuild/final-audit/a7v1-retry-exhaustion-probe.py` | 1 PASS / 1 MATERIAL FAIL; 0.42s | [final M2 XML](a7v1-retry-exhaustion-results.xml), session 75327 exit 1 |

**Final distinct current-code cases: 23 PASS / 1 FAIL / 0 SKIP / 0 XFAIL (24).**
The baseline negative control is separate. The initial harness failed before reaching the
contract assertion because `Sleep.pending` retains the cancelled 8s disconnect timer.
It woke before the new 8s retry registered. The only harness correction captures the old
timer events before reconnect and waits for a new event; all product assertions, data,
failure injection and code remain unchanged. Its two failed executions are disclosed,
not converted into passes or product failures. Across all four commands there were 28
case executions (24 pass / 4 fail); that raw count is not the distinct audit verdict.
XML failure-trace trailing spaces were normalized for Git; counts and assertions are unchanged.

Root credential guard was reviewed; tests/conftest routes DB to temporary paths. These
probes use no DB/files/media/network at all beyond pytest receipts: actual Cog/Actor,
synthetic audio state, fake clock/sleeper, AsyncMock provider/library/repository. They
establish application effects, not real audible Discord Voice. Teardown runs in finally
and checks audio silence and empty supervisor even on the failing assertion.

No additional functional tests were started after the confirmed M2 RED. Read-only source
review then established contract provenance. Full suite and broader Music regression were
not run due the explicit MATERIAL STOP. Known inventory/A2-N1, missing Deno, audioop,
A3-N1/A3-I1 remain; no clean full-suite PASS or fresh Deno result is claimed.

## Remaining Phase 7 gates and next boundary

| Gate | A7V1 disposition |
| --- | --- |
| Original M1 same-session paused reconnect | independently PASS / CLOSED |
| Playing/paused TTS, repeated/stale callbacks and explicit termination cases | 20 current regression cases PASS; bounded scope above |
| Automatic retry exhaustion → successor ownership | **FAIL: A7-M2** |
| Queue/loops/all controls/pagination/favorites/autoplay | not independently completed; stop at M2 |
| Global cache/provider bounds/actual local child cleanup/security diagnostics | source/contract partially reviewed; required current gate execution remains |
| Full restart, old-reader compatibility, snapshot ACK/corruption/partial guild recovery/count receipts | not independently completed |
| Complete lifecycle/concurrency/architecture/dependent regression and scoped soak | not completed; historical results cannot substitute |
| Real providers/Discord Voice/Pi/long soak/deployment | not attempted; preserve C10–C12's explicit later-phase limits |

Next: supervisor review of A7-M2, separately authorized **A7R2** addressing pause ownership
at automatic session retirement, then fresh independent verification of M1/M2 and remaining
Phase 7 gates. No fix, assertion weakening, contract change, A8, Integrated Audit or Phase 11.
Friend activation remains HELD; deployment condition unmet; MyFood untouched.

## Preservation, commit and shutdown checkpoint

Owned files are this report, entry inventory, [ownership receipt](a7v1-ownership-receipt.json),
baseline launcher, M2 probe, four XML receipts,
and only active-state AU / Phase 7 ledger deltas. Original A7/A7R1 files and document index
remain untouched. Active-state append and ledger-row replacement preserve the inherited
bytes; inverse removal/replacement reconstructs their exact entry hashes. All other 68
inherited paths remain byte-identical. No inherited change is staged. No data/schema,
dependencies, `.env`, backup, deployment, remote, OS policy or implementation write.

Scoped local Conventional Commit follows explicit staged diff and whitespace review.
Rollback is reversal of this audit-only commit while preserving inherited mixed documents;
no production/data rollback is involved. Deliberately RED evidence stays outside standard
`pytest tests/` collection and has no skip/xfail marker.

All four foreground test sessions exited; no servers/browser/FFmpeg/WSL were started.
Post-test process inspection found no python/pythonw/pytest/ffmpeg process. Pre-existing
node PIDs 4644, 12284 and 28216 started 11:13:43 KST and remain untouched. No owned process
or pending test write remains. Final documentation/commit/preservation checks are completed
in the handoff, before 12:35 KST test-start and 12:45 KST cleanup cutoffs. No shutdown was
issued. From A7V1 work it is safe to turn off the PC after handoff.
