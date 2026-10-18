# A7V2 independent Phase 7 verification - PASS

2026-10-03. **Phase 7 PASS for its repository/synthetic contract. A7-M1 remains
CLOSED; A7-M2 independently CLOSED.** No implementation change or successor task.
This is not a clean full-suite, live Voice, deployment, or Pi certification.

## Identity and authority

- Branch `codex/rebuild-v2`; entry and audited runtime HEAD
  `d9d0141f70be165d030fc1bfed5538fea312730b`. M2 implementation
  `b914200e20905179f16a7f98ffca8d841db07746`; M1 implementation
  `12a42ef9168da0540825fa1cb12f2c189da95411`. Final audit-only commit is in the handoff.
- [Entry inventory](a7v2-entry-inventory.json): exactly 11 modified / 59 untracked
  contents, empty index. Root AGENTS applies; checkout `.agents/skills` and nested
  src/tests/docs AGENTS are absent. Initial routing and supplied identities agree.
- Read active-state/Phase 7 ledger/document index, B20 Phase 7, B08 BR-003/005/007,
  B12 FR-011-025, relevant B11/B13-B19/B21 sections, D22 Q-H01/05/07/M01-M04,
  D23 ADR-022, C1/C2/C3 and C10-C12, canonical Phase 7 report, trace/product semantics,
  scoped P2 gates 7-19, A7/A7R1/A7V1/A7R2 reports and exact original probes/regressions.
  Inspected current actor, adapters, DTOs, production composition and affected tests.
- Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
  `r-8e9018d4b8061cde-3dac82a792fad576` remain distinct and unchanged documentary
  identities. No production observation, credential/data access, Pi or WSL operation.

## Independent M1 and M2 disposition

The entire runtime diff from pre-A7R2 `22736424a32991d480ca3518085e948292eb40db`
is the assignment/comment in `MusicActor._advance`: clear `_resume_paused` when
retiring the logical session. The M1 disconnect OR-assignment remains intact.
First/second recovery failures call `_prepare` through a retry and preserve session,
position and pause. Third failure calls `_advance` and creates an unpaused successor
at elapsed zero. No successor leaves an unpaused idle state for a later enqueue.

Reviewed all `_advance` callers: initial enqueue/connect, normal completion/loops,
manual skip, post-announcement advance and exhaustion initialize/replace a logical
session. Same-session TTS/reconnect preparation does not pass through that reset.
The start-result attempt check, stale work token checks, receipt accounting and
disconnect generation remain unchanged. This fixes M2 without reopening M1.

[Independent baseline launcher](a7v2-baseline-probe.py) loads an exact historical
actor Git blob only into its process; it never replaces checkout files. Unchanged
probes and current regression assertions are run against each baseline and current code.

| Check | Original actor result | Current result | Disposition |
| --- | --- | --- | --- |
| Original A7 M1, actor `3092f49...` | 1 PASS / 1 FAIL; paused TTS reconnect becomes playing/audible | 2 PASS; same session, 17s, paused/silent | M1 remains CLOSED |
| Original A7V1 M2, actor `2273642...` | 1 PASS / 1 FAIL; successor `('2','paused',True,False)` | 2 PASS; successor `('2','playing',False,True)` | M2 CLOSED |
| A7R2 30-case regression on pre-fix actor | 22 PASS / 8 FAIL | 30 PASS | Same-session vs queued/later successor distinction verified |
| A7R1 interruption regression | baseline not repeated for these 20 cases | 20 PASS | TTS generation/start/completion/failure, cancellation, repeat/stale events and termination retained |

Original M1 probe SHA-256 `5f81fc6ae055f27486a5d89d4fee6fe2729e1b9a2aeae0d0e08150df7b7ddba2`;
M2 `b675a696316efc046131cba4d7778b43dc1f8c22aaac25823cc9e8ad25c9a24a`.
They and the remediation regressions were not edited. The two original probes use
real Cog-to-Actor routing with independent synthetic audio for a second guild;
they verify application audible/silent effects, not actual Discord sound.

## Remaining Phase 7 gates

All PASS rows below concern current repository behavior under the stated synthetic
boundaries. Historical listening evidence is supplementary, not counted as fresh tests.

| Gate / authority | Current independent evidence | Disposition |
| --- | --- | --- |
| F011-F016 commands, visibility, channel/voice policy, playlist/FIFO, dashboard | `test_discord`, `test_lifecycle`, provider playlist cases; actual SDK ViewStore dispatch in favorites/dashboard-gap tests; code review | PASS |
| F017-F023 playback, queue, loop, retry, stale controls and guild isolation; CF01-03 | Actor/failure/pause regressions; M1/M2 unchanged probes; stable IDs, duplicate callbacks and current-session guards | PASS |
| Queue clear/confirmation and revision/expiry | New independent confirm/cancel/stale/exact-30s cases preserve current track and affect only intended queue | PASS |
| F024 autoplay / CF04 | Existing success/local-failure/stale-result tests; new 0.29/0.30 featured-artist boundary, 90/600 duration exclusions, URL/title dedupe, fresh successor | PASS |
| F025-F026 global favorites, paging, counts / CF21 | Actual temporary SQLite, 26/101-entry SDK paging, user/guild isolation, receipt transaction/dedupe, encrypted synthetic backup restore | PASS |
| F027 TTS / CF05 | Announcement admission/order, paused/repeated/reconnect/cancel/stale callbacks; generation/start failure, skip/leave/expiry/close; original M1/M2 controls | PASS |
| Global cache, process/PCM bounds and cleanup / CF15/20 | Real temporary cache, pins/TTL/corruption/disk fault/cancelled publish; actual local Python children through ProcessPool and DiscordAudio pipe/start/stop/reap; kill escalation fake | PASS, Windows synthetic scope |
| F028/F045 full restart and count reconciliation | New real MusicResource stop/start + temporary SQLite verifies playing/paused state, voice channel, current/queue, 17s, volume .35, QUEUE/autoplay, same receipt then new successor receipt | PASS |
| Snapshot crash, ACK/corruption/partial guild, rollback reader / CF06 | Existing atomic replace fault, checksum/version/stale ACK and partial restore tests; actual V1 reader; new abrupt local writer exit after fsync before replace retains exact old state and ignores uncommitted temp | PASS |
| Lifecycle, optional degradation, privacy, architecture / CF16/19/20 | Ready storms, responder signatures, cleanup ownership, content-free diagnostics; import/layer/task/executor rules; affected and full suite | PASS for audited contracts; known failures below |
| Scoped repeatability soak, B20/C2 | 21 selected cases x 100 fresh pytest child processes; every round PASS, 2,100 executions, 157.98s total child runtime | PASS; not 2,100 distinct tests or Pi soak |
| Pinned provider/Deno runtime smoke | yt-dlp version child runs offline; missing Windows `deno.exe` fails its version launch | Known environment limitation, not waived/installed |
| Real Discord/YouTube/gTTS/Pi/long resource soak | No new execution; C10-C12 and B19 leave these to staging/later operational gates | Outside this repository PASS; not newly certified |

[Contract probe](a7v2-contract-probe.py), [abrupt-exit probe](a7v2-snapshot-crash-probe.py),
[soak launcher](a7v2-soak-probe.py), [100-round receipt](a7v2-soak-results.json).
The crash probe uses an actual child `os._exit(73)` at the publish boundary, not OS
power loss or a claim that the filesystem always completes fsync. Its synthetic
orphan temporary file stays inside pytest's temporary directory.

## Commands, counts and harness disclosure

Existing `.venv/Scripts/python.exe`, `PYTHON_DOTENV_DISABLED=1`, `PYTHONIOENCODING=utf-8`.
All pytest runs use `-c pyproject.toml -q --tb=short -W error::RuntimeWarning
-W error::pytest.PytestUnraisableExceptionWarning` and the linked `--junitxml` receipt.

| Target/command suffix | Fresh result | Receipt |
| --- | --- | --- |
| Original M1/M2 probes + `test_tts_reconnect.py` + `test_pause_session_lifetime.py` | 54 PASS, 0.59s | [focused](a7v2-focused-results.xml) |
| `a7v2-baseline-probe.py m1` | 1 PASS / 1 negative-control FAIL, 0.40s | [M1 baseline](a7v2-baseline-m1-results.xml) |
| `a7v2-baseline-probe.py m2` | 23 PASS / 9 negative-control FAIL, 0.60s; split 1/1 + 22/8 | [M2 baseline](a7v2-baseline-m2-results.xml) |
| `tests/integration/music/ tests/characterization/test_music_contracts.py tests/architecture/test_import_rules.py` | 229 PASS / 1 known FAIL, 10.51s | [affected](a7v2-regression-results.xml) |
| `docs/rebuild/final-audit/a7v2-contract-probe.py` | 8 PASS, 0.64s | [contract](a7v2-contract-results.xml) |
| `docs/rebuild/final-audit/a7v2-snapshot-crash-probe.py` | 1 PASS, 0.31s | [crash](a7v2-snapshot-crash-results.xml) |
| `tests/` | 1,389 PASS / 2 known FAIL / 27 SKIP, 95.98s | [full](a7v2-full-results.xml) |
| `a7v2-soak-probe.py` | 100 rounds / 2,100 PASS executions, 0 FAIL/SKIP | [last round XML](a7v2-soak-last-results.xml) |

Final distinct current-code union: **1,402 PASS / 2 FAIL / 27 SKIP / 0 XFAIL**
(1,431 cases). Full suite + four original probe cases + nine new independent cases.
The affected-only union is **242 PASS / 1 known FAIL**. Repeated focused/soak passes,
baseline controls and initial harness executions do not inflate either unique count.
[Machine-readable counts and case identities](a7v2-counts.json).

The new contract probe initially reported **6 PASS / 2 synchronization FAIL**
([retained initial XML](a7v2-contract-initial-results.xml)). Both failed in the fake
rig's 300 zero-delay turns before real SQLite executor completion, before any new
restart assertion. Changed only restart waits to poll at 1ms with a 3s deadline;
explicit connect/enqueue are identical to the reused `playing` helper. All inputs,
failure injections and assertions remain. All 100 final soak rounds include these
two cases without failure. Initial failures are harness evidence, not product RED.
Earlier A7V1/A7R2 harness failures remain historical and separately disclosed there.
XML trace trailing whitespace is normalized only for Git; assertions and outcomes
are unchanged, and the count receipt hashes the normalized files.

Known failures: `test_rebuild_documents_are_partitioned_without_loss` still expects
only A0 in final-audit; `test_pinned_provider_and_runtime_load_without_network` fails
on missing release-local Deno. All 27 skips are existing opt-in Linux/systemd cases.
Audioop deprecation and A3-N1/A3-I1 limitations remain. No skips/xfails/assertions
were added to suppress any failure; no dependency install or environment repair.

## History, supersessions and limits

- Original Phase 7 report at `e0449c2` is unchanged as text (checkout CRLF explains
  byte inequality). Nine directly relevant PRESERVE functions in music/component
  characterization retain identical ASTs. Original 592/85/2300 counts remain
  historical claims, not fresh reruns on that old implementation.
- Its broad paused-interruption claim lacked the M1/M2 combinations, as earlier
  independent RED demonstrated. History remains intact; this report closes only
  after current independent negative controls, regression, new gates and soak.
- C10's original unwired composition and V1 one-shot snapshot wording are historical
  boundaries; ADR-022/C11 explicitly define V2 metadata/ACK replacement, and later
  production composition wires Music after DB/Gateway readiness. No format changed here.
- Original generic 10s shutdown claims in B13/C2 are scoped by the explicit later
  C3 A2R2/R3/R4/R5 ownership/containment contract, not silently reinterpreted as
  unconditional cleanup. Current incomplete cleanup is retained and reported FAILED.
- Validation-only fail-fast/full-sweep behavior is separately scoped; normal retries
  remain 3s/8s/third-skip. P2 gates 7-19 are historical human evidence for their exact
  release, not current real-provider verification. No additional unresolved material
  contract contradiction was established. The known stale inventory failure remains.

## Preservation, rollback and shutdown checkpoint

Owned changes are this report, A7V2 probes/inventory/XML/count/soak/ownership receipts,
active-state AW append and the Phase 7 ledger row. All implementation, existing tests,
historical reports and the untracked document index remain untouched. Mixed authority
files preserve inherited bytes; inverse scoped edits reconstruct entry hashes.
The [ownership receipt](a7v2-ownership-receipt.json) records all 70 inherited contents.
Only HEAD plus owned authority deltas are staged; no bulk staging of mixed files.

Scoped local Conventional Commit follows staged-diff/whitespace review. Rollback is
reversal of this audit-only commit while retaining inherited mixed-document work;
no runtime/data rollback or history rewrite. Exact final HEAD/index/status are in the
handoff. No push, deployment, production writes/migration/backup, service/security/
routing changes, dependency changes, My Food work or PC shutdown.

All test sessions and the 100-round launcher completed before 12:35 KST. Final process
inspection found no Python/pythonw/pytest/FFmpeg process. Pre-existing Node PIDs
4644/12284/28216, started 11:13:43 KST, remain untouched. No server/browser/WSL was
started. Documentation/commit checks finish before 12:45 KST; no owned process or
pending test write requires the PC to remain on. It is safe to turn off from A7V2
after the final handoff; other applications' unsaved work is outside this audit.

**STOP A7V2.** A0-A6 PASS retained; A7 now PASS. Next boundary is supervisor review,
then a separately authorized A8 session. No A8, Integrated Audit or Phase 11 started.
Friend activation remains HELD and the deployment condition remains unmet.
