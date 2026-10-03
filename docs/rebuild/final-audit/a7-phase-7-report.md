# A7 independent Phase 7 music audit — FAIL

2026-10-03. **A7-M1 MATERIAL OPEN.** Audit only; no implementation remediation.

## Identity and authority

- Audit target: `codex/rebuild-v2`, HEAD `3092f49ce82ac44232535b39b779718a5bd0f414`.
  No runtime implementation changes made. Evidence commit is reported in the handoff.
- Recorded production source: `8e9018d4b8061cde6006eee47fa4103522f77718`;
  pin `r-8e9018d4b8061cde-3dac82a792fad576`. No production access or fresh host observation.
- [Entry inventory](a7-entry-inventory.json): 11 modified / 59 untracked / empty index,
  all 70 inherited content hashes verified unchanged before owned state updates.
- Root AGENTS applies; no nested AGENTS in src/tests/docs; checkout `.agents/skills` absent.
- Read current audit authority/index/Phase 7 row, canonical Phase 7 report and C10/C11/C12;
  relevant B20 Phase 7 gate, B12 FR-011–025, D22/D23 (including ADR-022), trace and
  product music contract. Reviewed later music commit history and P2 Music/TTS gates 7–19.
  F011–F028/F045 cover actors, controls, queue, favorites, autoplay, TTS, cache and restart.
  Historical report/live PASS is evidence of its stated scope, not inherited audit PASS.

## A7-M1 — disconnect during TTS discards paused music intent

**Severity: MATERIAL.** A user-paused song resumes without a resume action after a voice
connection interruption during its join announcement. C10 preserves pause/reconnect behavior;
C11 requires TTS to retain paused intent and reconnect to retain the logical music session.
No reviewed decision supersedes that requirement. Historical P2 gate19 also requires music
to remain paused after announcements; it does not test announcement-time disconnects.

Minimal deterministic sequence through the current real `MusicActor` and actual Music Cog:

1. Start a synthetic song and queued successor, advance the fake clock 17 seconds, pause.
2. Start synthetic TTS. Projection correctly retains `paused=True` while TTS is audible.
3. Deliver bot voice disconnect and reconnect to `MusicCog.on_voice_state_update`.
4. Wait for the resumed music attempt to settle. No resume command is issued.

| Observation | Expected | Actual |
| --- | --- | --- |
| Paused intent immediately after disconnect | true | false |
| Music status after reconnect | paused | playing |
| Music projection paused flag | true | false |
| Synthetic audio effect after reconnect | silent | audible |
| Logical session, current song, queue, position | unchanged / 17s | preserved |
| Separate guild control | continues playing | preserved |

The ordinary paused reconnect control passes with the same harness and assertions.
The independent audio fake sets audible on start and clears it on pause/stop; this proves
application effects, not real sound or Discord transport. Repository/provider/library are
AsyncMock adapters; no DB, media file, network, FFmpeg or browser process is used by the probe.
All actor/supervisor cleanup assertions pass even when the contract assertion fails.

Root cause: `src/discordbot/music/application/actor.py:457–458` overwrites
`_resume_paused` with `_status == "paused"`. TTS uses status `tts` and retains intent in
`_resume_paused`; the assignment discards that intent before reconnect preparation.
`runtime.py:280–285` routes real bot voice events into these operations;
`actor.py:371–380` then starts playback without the missing pause effect.
`git blame` attributes the assignment to original Phase 7 commit `f9cf9c82`.
Later consecutive-TTS fix `d14eba8` and pause/UI fix `998e2f2` did not close this combined path.
No evidence here invalidates the previously independently passed A0–A6 contracts.

## Fresh evidence and exact commands

Set `PYTHON_DOTENV_DISABLED=1` and `PYTHONIOENCODING=utf-8`. Use existing
`.venv/Scripts/python.exe -m pytest -c pyproject.toml`, with
`-q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.

Existing focused selection **8 PASS / 0 FAIL / 0 SKIP / 0 XFAIL**, 0.65 seconds:

- `tests/integration/music/test_actor.py::test_pause_elapsed_reconnect_preserves_session_and_pause`
- `tests/integration/music/test_actor.py::test_tts_resume_keeps_logical_session`
- `tests/integration/music/test_tts_admission.py::test_consecutive_announcements_preserve_paused_music_intent`
- `tests/integration/music/test_failures.py::test_checkpoint_during_tts_keeps_paused_session_intent`
- `tests/integration/music/test_pause_intent.py` (4 parameterized cases)

Independent [unchanged failing probe](a7-paused-disconnect-probe.py), command target
`docs/rebuild/final-audit/a7-paused-disconnect-probe.py`:
**1 PASS / 1 FAIL / 0 SKIP / 0 XFAIL**, 0.41 seconds, exit 1.
Failure node: `test_paused_intent_survives_voice_reconnect[disconnect-during-tts]`.
Assertion: observed `(False, 'playing', False, True)` versus `(True, 'paused', True, False)`.
Disjoint total: **9 PASS / 1 FAIL / 0 SKIP / 0 XFAIL**. No repeats counted.
Known Python audioop deprecation warning appeared; strict runtime/unraisable checks passed.

Root pytest credential guard disables dotenv and scrubs app config; existing tests route DB
paths to temporary synthetic paths. Selected snapshot tests use tmp_path. Inspected fixtures
use mocks/fake clock and clean owned tasks/views/executors. No production data was read.

At 02:09 UTC the first test launch failed to create a process because exec-server disconnected;
no test result/session was returned. A harmless command recovered at 02:11:47 UTC. Repository
HEAD and saved files were then checked before the two successful launches above. An interim
BLOCKED report was saved and superseded by this confirmed FAIL; it is not a separate finding.
Process sessions 50574 (exit0) and 82014 (exit1) completed. No test rerun after material RED.

## Scope disposition, ownership and safe stop

The material finding triggers the requested STOP. Queue/autoplay/cache/process/full restart
and broad dependent/full-suite checks are **not independently completed** in A7; do not infer
whole-phase coverage from the 9 passes or earlier reports. No Linux verification was needed
for this platform-independent state transition. No live Discord/YouTube/gTTS/Pi/paid service,
full-suite, soak, deployment or production correctness claim.
Known A2-N1 inventory test, unrelated missing Deno, audioop, A3-N1 and A3-I1 remain visible
and unchanged. No fresh full-suite PASS is claimed. A0–A6 retain their recorded PASS.

Owned changes only: this report, entry inventory, independent probe, active-state AS append
and Phase 7 ledger row. Mixed inherited content is preserved and excluded from staging. The two updated authority
files were rewritten with normalized line endings; their inherited text is retained. All
other 68 inherited files retain exact entry byte hashes. No inherited edit is committed.
Scoped local Conventional Commit follows staged diff/whitespace review; no push.
Rollback: revert that audit-only commit, preserving the inherited mixed documents; no runtime,
data or schema rollback. The intentional RED remains under final-audit evidence, outside
standard `pytest tests/` collection; it is neither skipped nor marked xfail.

Both test processes completed and probe cleanup confirms no active supervisor tasks/audio.
Final `Get-Process` inspection found no python/pythonw/pytest/ffmpeg/node process. Existing
Chrome processes predate A7 and are untouched; A7 started no browser/server. CIM parent lookup
was unavailable (access denied); Get-Process and completed session receipts suffice for these
foreground, child-free tests. No owned process or pending test write remains. Final audit
writes/commit and preservation recheck are completed in the handoff. From A7 it is safe to
restart/update the app or turn off the computer after that handoff. No PC shutdown performed.

**STOP A7 FAIL. Exact next boundary: supervisor review of A7-M1, then separately authorized
remediation and independent Phase 7 verification.** Do not start A8, Integrated Audit,
Phase 11, production changes or My Food work. Friend activation remains HELD.
