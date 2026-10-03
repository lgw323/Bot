# A7R1 paused music across TTS reconnect

2026-10-03. **Scoped remediation PASS; Phase 7 remains FAIL. A7-M1 remains OPEN,
remediated pending independent verification.** No A7V1, A8, Integrated Audit or Phase 11.

## Identity and authority

- Entry branch `codex/rebuild-v2`, HEAD `04f6b8db456c91dcd443f70b5c89cc3be9dc1731`;
  original A7 audited source `3092f49ce82ac44232535b39b779718a5bd0f414`.
- Implementation commit: `12a42ef9168da0540825fa1cb12f2c189da95411`.
  The following documentation commit records evidence only; final HEAD is in the handoff.
- Read root AGENTS, current active-state/ledger/document index, A7 report and unchanged
  probe, C10/C11/C12 and canonical Phase 7 report, B20 Phase 7 gate, relevant FR and
  ADR-022, and product music contract. Checkout `.agents/skills` and nested AGENTS are absent.
  Current authority agrees with the requested A0-A6 PASS / Phase 7 FAIL boundary.
- [Entry inventory](a7r1-entry-inventory.json): 11 modified / 59 untracked, empty index,
  70 inherited hashes. Comparison with A7 inventory confirms the disclosed 68 unchanged
  files and two authority files updated by A7 with newline normalization. Those entry
  bytes, including their existing mixed line endings, are the A7R1 preservation baseline.
- Production remains separately recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`,
  pin `r-8e9018d4b8061cde-3dac82a792fad576`. No production observation or operation.

## Root cause and exact repair

TTS temporarily uses status `tts_starting`/`tts`; music's user pause intent lives in
`_resume_paused`. Disconnect unconditionally replaced that flag with `status == "paused"`,
which is false during TTS. Reconnect consequently reached the normal music start path
without its pause effect. Repeated disconnects and a disconnect during music preparation
could discard the same retained intent. The actual Cog forwards these voice events to
the actor; the defect is the actor assignment, not an alternate test-only route.

The only runtime change is one assignment plus its explanatory comment in
`src/discordbot/music/application/actor.py`: retain an already saved pause flag OR the
current paused status. It runs in the existing mailbox before audio stop. Existing
successful start, explicit resume, skip and leave/reset paths still consume or clear it.
No new state, task, timer, retry, lock, schema, snapshot field, dependency or UI behavior.
The change restores C10/C11's existing pause/session contract under the user's explicit
A7R1 remediation authorization; no new product decision is needed.

Queue/current/session, 17-second position, loop/autoplay/volume, 8-second reconnect grace,
1.5-second join announcement, work-token and attempt rejection, and cleanup remain on
their existing paths. The separate guild continues playing in the unchanged A7 probe.

## Unchanged RED to GREEN and exact commands

Every test command used the existing Windows venv and these PowerShell settings:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONIOENCODING='utf-8'
```

1. Before any implementation edit, original A7 probe unchanged:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml docs/rebuild/final-audit/a7-paused-disconnect-probe.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

**1 PASS / 1 FAIL / 0 SKIP / 0 XFAIL**, 0.42s, exit 1, session 85094.
`disconnect-during-tts` again observed `(False, 'playing', False, True)` instead of
`(True, 'paused', True, False)`. Ordinary reconnect and cleanup assertions passed.
Probe SHA-256 before/after: `5f81fc6ae055f27486a5d89d4fee6fe2729e1b9a2aeae0d0e08150df7b7ddba2`.

2. Added regression file, still before implementation edit:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml tests/integration/music/test_tts_reconnect.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

**8 PASS / 12 FAIL / 0 SKIP / 0 XFAIL**, 0.56s, exit 1, session 9081.
Failures all expose lost pause intent; playing controls pass. Assertions and fixtures
were not weakened or changed between this RED and the following GREEN.

3. After the one-line repair, original probe plus new regression file:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml docs/rebuild/final-audit/a7-paused-disconnect-probe.py tests/integration/music/test_tts_reconnect.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

**22 PASS / 0 FAIL / 0 SKIP / 0 XFAIL**, 0.41s, exit 0, session 90161.
Original probe now verifies paused/silent with the same session, queue and 17s position.

4. Bounded affected-contract regression, including prior Music cleanup/dispatch fixes:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml tests/integration/music/ tests/characterization/test_music_contracts.py tests/architecture/test_import_rules.py -q --tb=short -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning --junitxml=docs/rebuild/final-audit/a7r1-regression-results.xml
```

**199 PASS / 1 known FAIL / 0 SKIP / 0 XFAIL**, 10.72s, exit 1, session 26312.
[JUnit evidence](a7r1-regression-results.xml) contains 200 distinct cases: 181 Music,
7 Music characterization, 12 import/ownership architecture. The 20 new cases are included.
Known failure: `test_resources.py::test_pinned_provider_and_runtime_load_without_network`,
at the release-local Deno `--version` launch; `.venv/Scripts/deno.exe` is absent.
No dependency installation, assertion change, skip or xfail was used to hide it.

**Final unique union: 201 PASS / 1 known FAIL / 0 SKIP / 0 XFAIL (202 cases).**
This is 199 broad passes plus the two original A7 cases, not 199+22.
Baseline RED runs and repeated GREEN cases are not additional passes. A clean full-suite
claim is expressly not made. Full `pytest tests/` was not run: this microphase selected
the affected Music contracts and cross-module import/ownership checks, not unrelated phases.

## Coverage and evidence limits

- New 12-case Cog/Actor matrix: playing versus paused, TTS generation/start/play/completed/
  failed/between-announcements, cancellation observed, repeated disconnect/reconnect,
  stale/duplicate success and failure callbacks, expired old reconnect timer, renewed
  join announcement, pause/silence and explicit resume effects, session/queue/position/settings.
- Four cases interrupt reconnect during music preparation/start, with both pause states.
  Four cases verify intent is cleared on skip, leave, grace expiry and close.
- Existing affected tests cover 3s/8s retry, autoplay, queue/loop, consecutive announcements,
  paused checkpoint/restore and legacy shape, receipt dedupe, guild/global data scope,
  stale media lease return, bounded media/process/cache failure, Discord dispatch and
  real Music cleanup after optional-resource degradation (prior A2 remediation contract).
- Original and new probes use real Cog/Actor with synthetic audio and mocked provider,
  library and repository. Broader tests also use temporary SQLite/files, offline SDK
  objects, real local Python child processes and mocked FFmpeg spawning. Root credential
  guard disables dotenv; test fixtures isolate DB/cache/snapshots and reap owned work.
- No live Discord/YouTube/gTTS/Gemini/paid service, production DB, Pi, WSL, browser,
  deployment, service/routing/security change, soak or real audible Voice proof.
  Linux process verification is unnecessary for this platform-independent state assignment.
- Known inventory/A2-N1, Deno, audioop deprecation, A3-N1 and A3-I1 limitations remain.
  A0-A6 verdicts are retained, not re-audited. Remaining whole-Phase-7 gates belong to A7V1.

## Ownership, rollback and safe stop

Owned changes: actor assignment/comment, one 20-case test file, this report, entry inventory,
JUnit receipt, scoped CHANGELOG entry, active-state AT append and Phase 7 ledger row.
The document index, original A7 report/probe and all other inherited files are untouched.
Mixed documents retain their inherited bytes; only owned deltas are staged against HEAD.
Removing the three owned mixed-document deltas reconstructs all 70 entry hashes; 67 files
remain literally byte-identical. Residual status remains the original 11 modified / 59
untracked paths with empty index after the documentation commit. No bulk staging/reset/push.

The implementation commit includes its verification/rollback instructions. Revert that
scoped commit to undo the repair; no DB or production rollback is involved. Revert the
separate evidence commit only to undo its audit routing, preserving mixed inherited work.

All four test sessions exited. Probe/fixture teardown closed actors, supervisors, views,
executors, temporary DB handles and local child processes. Post-test `Get-Process` found
no python/pythonw/pytest/ffmpeg process. Three node processes (4644, 12284, 28216) started
at 11:13:43 KST, before A7R1 entry at 11:19 KST; they were not task-owned and were untouched.
No task-owned server/browser was started. No owned process or pending test write remains;
final documentation writes/commits and preservation checks finish before handoff, well
before the 12:35/12:45/12:50 KST limits. No PC shutdown performed. From A7R1 work it is
safe to turn off the PC after handoff; unrelated applications remain the user's responsibility.

**STOP A7R1. Next boundary: supervisor review, then separately authorized independent
A7V1 of A7-M1 and the remaining Phase 7 gates. Phase 7 stays FAIL and A7-M1 stays OPEN
pending that verification.** A8/Integrated Audit/Phase 11 unstarted; friend activation
HELD, production identity unchanged, MyFood untouched.
