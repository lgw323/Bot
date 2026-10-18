# A6V1 - Independent Phase 6 verification

2026-10-03. **PHASE 6 PASS; A6-M1 independently CLOSED.**
No new MATERIAL, required DRIFT or BLOCKED finding. Stop for supervisor review.
This is a repository/local-synthetic verdict, not production deployment or live-provider approval.

## Scope, authority and interruption

Entry and resumed HEAD: `e12b6e4fb3263eb702752d872ce902625785a0d9`,
branch `codex/rebuild-v2`. Implementation under verification:
`ecd8ef2d69d27199c41eb8941615fa177d1e8834`.
The three final-audit authority files were read first on entry and inspected again on resume.
Reviewed C8/C9, B03 F037-F043, B12 FR-038-044, B20 Phase6 exit, C1 compatibility,
C2 CF-10/11/12/13/16/19/20, accepted ADR-004/005/012/021, scoped D22/trace/product rules,
original Phase6 report, A6 unchanged appendix, A6R1 report and P2 Gates23/26/27/29.
Repository AGENTS applies. No relevant additional checkout skill or nested AGENTS was found;
no plugin or sub-agent was used. No implementation, existing test or dependency was changed.

The first turn stopped immediately on the user's shutdown request. Its 184 completed pytest
results and initial Chrome/baseline results remain in the conversation tool receipts, not saved
raw log files. On October3, the user explicitly authorized continuation of A6V1 only.
The saved inventory/probes and baseline export survived; all70 inherited hashes matched and
HEAD/index matched. The unfinished browser probe had only been compiled, not executed.
The resumed checks below complete it. No previous result is silently represented as a fresh
October3 pytest rerun. The later instruction to finish this task and pause for an app update
is the final next-work boundary; no other microphase is authorized by this report.

## M1 reproduction and independent closure

Original defect: administrator terminal4001 left the owned iframe playing42->44s despite
terminal=true/no reconnect. The original A6 appendix was extracted byte-for-byte, unedited,
and completed **2 PASS**: server cleanup/other-guild isolation and active browser media stop.
A fresh direct execution of its exact Node scenario on resume (same case, not extra count):

```json
{"terminal":true,"targetState":-1,"targetTime":42,"targetSockets":1,"targetCommands":["playing","destroy"],"controlState":1,"controlTime":44}
```

The actual Chrome probe independently confirmed the required physical iframe/media lifetime:
target42.228868s -> unloaded0 -> still0 after1s; control42.034468s ->43.005558s.
Exactly one target join/destroy; no new iframe after online/pageshow/API callback.
The **same unmodified** `tests/browser/watch_terminal_chrome.py` fails against the exact
pre-remediation template from `8d04ed571578076837928a41131ae99b8519f69f` with
`AssertionError: terminal iframe remains attached`. This differential was observed on both
pre-pause Chrome154.0.8037.92 and resumed Chrome154.0.8037.93. The browser version changed
outside this audit; no install/update was performed. Candidate/baseline repetitions are not
additional unique tests. The baseline failure is an expected negative control, not a current defect.

Source review confirms local terminal ownership is revoked before provider callbacks:
`terminatePlayback` clears player readiness/pending state/timers/page listeners, releases its
player reference, invokes destroy and removes the DOM iframe in finally. API readiness,
playback callbacks and publishing paths cannot revive terminal state. HTTP403/404 and the
session_closed event share this path; the event does not wait for the close handshake.
Current-socket identity guards keep retired4001 callbacks from terminating a replacement.
No change to authorization, grace, HTTP/WS schema or other rooms is required for closure.

## Fixture validity and actual-browser boundaries

Reviewed the complete A6R1 fixture diff. Adding native-like destroy/removeEventListener and
clearInterval support supplies missing API surfaces; no existing media/reconnect assertion
was deleted or weakened. `activeListeners` models registration while the separate `listeners`
map intentionally retains stale callback handles. Timer/interval maps expose release, not just
state flags. The VM destroy records the stopping clock; that model alone is not proof of a
real iframe. The unchanged original regression and actual HTMLAudioElement differential
supply that independent evidence. Fake DOM remove is supplemented by actual Chrome removal.

The synthetic Chrome provider's destroy removes its iframe; it does not manually freeze the
media clock. It uses generated silent WAV with HTTP ranges and genuine iframe audio. Only
the remote provider script URL is substituted in the shipped HTML; inline product JS is
unchanged. Proxy/DNS restrictions block external hosts. Browser/server ports are dynamic
loopback, profiles private and disposable, and audio muted. No shared Chrome/MyFood browser
was attached. This is not real YouTube behavior or audible/live Discord evidence.

[Independent browser probe](a6v1-browser-probe.py) adds five actual-DOM cases, reusing only
the reviewed local transport/profile machinery. Provider command counters and CDP pre-document
listener/interval accounting do not replace product cleanup. Each case verifies another room
continues, then delivers three rounds of late readiness/state/error/autoplay/API/page/socket
callbacks and checks no new media command/construction, no periodic timer/page listener,
null pending/player state and stopped target clock. Pre-API checks zero constructions; the
other cases check exactly one cleanup. One finite terminal toast is permitted by A6R1.

| Additional Chrome case | Observed result |
| --- | --- |
| before-api | terminal before provider construction; late API callback cannot construct; control advances |
| before-ready | existing iframe/media, readiness withheld; terminal unloads it; late ready cannot restart |
| session-event | server event arrives while client close completion is deliberately withheld; media stops immediately |
| destroy-throws | provider destroy throws without removing DOM; production finally still unloads the actual iframe |
| reconnect | actual4008 closes transport, one replacement joins; retired4001/stale playback ignored; current4001 still stops media |

Every additional case also renders adversarial synthetic chat/name/title/by text in genuine DOM
and checks no injected img node/code, then250 messages retain exactly200 entries. These shared
assertions are not counted separately. Normal/paused refresh, recovery click, play/pause/seek,
late video acknowledgement, pending load/add response, terminal4002/4003, HTTP403/404 and
reentrant destruction are covered by the44 VM cases and current server hydration tests.

## Complete scoped gate disposition

All rows below PASS for the stated Phase6 repository/synthetic contract. Staging/live gates
remain limits, not silently inherited PASS. Paths are under `tests/integration/watch/` unless
otherwise stated. Current code in `watch/application/`, `watch/adapters/`, composition roots
and corresponding assertions were inspected, including later hydration/lifecycle changes.

| Governing gate | Independent evidence / current-code conclusion |
| --- | --- |
| F037 / FR-003,004,010,038 / CF-19 | test_discord + characterization + independent invite-order probe: unchanged parameterless command/public invite, private errors, one ACK/followup, durable create -> admin send/bind -> invite/bind, failure/cancellation compensation and duplicate delivery |
| F038 / FR-039,041 | test_transports plus independent inputs/security: exact page/playlist routes and body/query semantics, inactive HTML404, nonce CSP/no-store/nosniff/no-referrer, no CORS/login/host additions; actual DOM escaping/200-entry bound |
| F039 / FR-040 / CF-10 | test_runtime/test_transports: seven client types, both state/playing inputs, presence/leave, ordered revisions with sender-exclusion gaps, ASGI join/invalid4003/protocol4002, invalid JSON/frame/rates; bounded slow peer does not block fast peer |
| F040 / FR-039,040 / CF-12 | test_runtime/test_lifecycle/test_metadata_security: trimmed URL-keyed duplicate-to-tail, CRUD/session separation, playlist cap, close/add/connect ordering and late metadata cannot revive; fixed oEmbed origin/no redirect/retry, 2 active+4 waiters,64KiB, safe fallback |
| F041 / FR-042 / CF-11 | lifecycle/runtime boundary cases29.999/30/34.999/35, last leave, reconnect4.99 and expiry5s, absolute lifetime; server time authority retained |
| F042 / FR-005,043 / Gate29 | original full signed-loopback/temp-SQLite cleanup probe, test_discord and independent cleanup retry: exact master denial, idempotent terminal4001, target peers/session/playlist and known invite/admin cleanup; M1 physical browser closure and other room continuity now independently pass |
| F043 / FR-044 / CF-13 | test_lifecycle/processes: readiness withheld through stale cleanup failure, different unexpired writer rejects ownership, replacement cleans dead owner/receipts, old actor rejects mutation; source heartbeat cannot renew lost lease |
| C8 durable intent / tombstones | create/abort/bind tests; independent concurrent same identity creates one session, another guild distinct; bind same pair idempotent/conflict rejects; terminal retry cannot recreate |
| C8 failed-close recovery | independent forced durable-close failure: actor remains terminal, peers4001, additions/resolution denied; restored writer + maintenance completes durable closure without resurrection |
| C8 cleanup receipts | independent failed Discord deletion retains pending receipt; retry clears views/ack, repeated cleanup harmless. Source retains uncleaned receipts under10000 cap and deletes only cleaned/expired rows; unknown response-lost message IDs remain documented limit |
| C8 capacities / CF-10,12 | session/client/total/mailbox/playlist and metadata capacity tests, deadline/cancelled waiter, slow-send timeout, independent create concurrency. Source hard ceilings/replay256/views128/cleanup100 and batch8 reviewed; conservative caps, no Pi load/SLO claim |
| C9 trust/route separation | real signed in-process client/server integration and metadata-security tests: literal loopback only, public app excludes internal route, exact Origin/CSRF, authentication body/host/time/signature/replay. Independent ±30/±31 boundaries, nonce256/replay/61s expiry and wrong-origin WS |
| C9 wire/privacy | independent extra/nonfinite/oversized path/header/content inputs fail closed; client rejects correlation mismatch, duplicate JSON, oversized response, wrong shape and redirect with one call/no retry; safe telemetry/errors, digest-only storage and nonce page proof |
| C8/C9 process ownership / ADR-004,021 | test_processes +12 architecture checks: separate import closures/state owners/supervisors/apps, no import-time runtime side effects, inactive loopback listeners, DB before admission; Watch dependency failure preserves Gateway health |
| CF-16 / CF-20 / ADR-005 | maintenance idempotence, bounded stop/cancel/drain, no owned peer/task remainder; cleanup ownership tests propagate nested incomplete cleanup and retain dependencies. Genuine Linux kill/cgroup/Pi shutdown timing belongs to later operational gates |
| C8 migration/data compatibility | test_data: temporary migration/checksum, unchanged1-3 ledger, old V1 Watch reader, guild-scoped reads, digest identity, full encrypted synthetic backup/restore metadata; no actual DB/backup access or format changes |
| Gates23/26 accepted refresh | test_playback_browser/test_browser_client + runtime hydration: video/position and paused intent, late API ordering, one recovery gesture, no stale overwrite. User-approved ordinary play action remains accepted; automatic single-browser resumption is optional |
| Gate27 multi-client controls/isolation | VM multi-client timing/autoplay-recovery/refresh/reconnect and server authority tests: play/pause/seek, another participant unaffected, no stale peer snapshot. Actual separate room media continuity corroborates; historical human multi-client evidence retains its limits |
| Historical report / later regression / dead routes | original504 PASS/2 xfail and1400 repetition counts are historical, not this audit's counts. Later server-owned hydration supersedes old join/sync_request wording; transient4008 reconnect supersedes original report's terminal4008 sentence. V1 remains intentionally retained, not production ownership; no duplicate writer launched or removed |

Historical D7 human playback/audio-stopped claim is preserved. Its observation does not identify
an implementation stop path in the old template, and A6's reproducible defect is not erased.
Current M1 closure rests on code and differential evidence above, not that historical PASS.
No unsupported inference about the cause of the human observation or production failure is made.

## Counts, commands and evidence provenance

[Evidence receipt](a6v1-terminal-evidence.json) records template/harness/probe hashes,
prior/resumed browser values, baseline identity and counts. [Entry inventory](a6v1-entry-inventory.json)
records all70 inherited paths/statuses/hashes and the empty index.

| Completed disjoint selection | PASS | FAIL | SKIP / XFAIL |
| --- | ---: | ---: | ---: |
| Exact original A6 appendix | 2 | 0 | 0 / 0 |
| Existing terminal/playback/client VM tests | 44 | 0 | 0 / 0 |
| Remaining Watch integration + Watch characterization, excluding those three files | 102 | 0 | 0 / 0 |
| Independent contract probe | 24 | 0 | 0 / 0 |
| Architecture import rules | 12 | 0 | 0 / 0 |
| **Unique pytest total** | **184** | **0** | **0 / 0** |
| **Unique actual Chrome synthetic scenarios** | **6** | **0** | **0 / 0** |

The pytest selections completed before the interruption (1.06s,2.11s,8.38s,2.06s,1.52s
respectively), with RuntimeWarning/PytestUnraisableExceptionWarning as errors. Known audioop
deprecation remains. No suite rerun is invented; all inherited hashes and scoped implementation/
existing tests remained unchanged at resume. Direct Node/candidate/baseline browser repeats and
reconnect-driver rerun are excluded from unique counts. Do not add historical A6R1's148.

From repository root, reproducible focused commands are:

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/watch/ tests/characterization/test_watch_contracts.py tests/architecture/test_import_rules.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest docs/rebuild/final-audit/a6v1-contract-probe.py -c pyproject.toml -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe tests/browser/watch_terminal_chrome.py
.venv/Scripts/python.exe docs/rebuild/final-audit/a6v1-browser-probe.py before-api
```

Repeat the last command with before-ready, session-event, destroy-throws and reconnect.
The consolidated pytest command is a reproduction convenience; actual execution used the disjoint
selections above. Original appendix uses the unchanged A6 report's explicit TEMP launcher.
The24-case probe originally ran through its saved TEMP launcher after installing root conftest's
credential boundary and explicit src/tests paths. Its archived code is unchanged.

Incomplete/diagnostic attempts disclosed, not counted as clean candidate failures: initial
restricted Chrome crashed and its crash-report TEMP cleanup was locked; normal isolated execution
then passed. After resume, sandbox CIM access was denied; elevated narrow read returned no owned
processes. The elevated browser could not read the sandbox-owned TEMP probe, so identical source
was archived in the workspace. The first boundary driver reached terminal assertions but failed
because CDP Page accounting was not enabled; adding Page.enable changed only audit instrumentation.
Initial reconnect assertions passed but the inherited synthetic server logged its intentional4008
as unexpected; the audit driver now accepts4008 only for that case, and a final clean run passed.
No product/test assertion was weakened. An earlier nested-string generator syntax error wrote no file.

## Ownership, safety and next boundary

Inherited entry **11 modified /59 untracked, empty index**, all70 hashes confirmed unchanged
at resume. Owned only this report, inventory, receipt, two audit probes, active-state AR append,
Phase6 ledger row and index navigation append. Only new audit files and AR/Phase6 deltas against
HEAD are staged; pre-existing mixed authority/index work remains uncommitted. The disposable
baseline export is removed only after checking its exact Git blob, not retained as a product asset.
Scoped local Conventional Commit follows staged-diff and whitespace review; no remote push.
Rollback is a documentation/evidence-only revert of this scoped commit; no data/runtime rollback.
The final commit SHA and preservation/process recheck are supplied in the handoff.

Known inventory/Deno/audioop and A3-N1 MINOR/A3-I1 INFO remain. No clean full-suite claim.
No fresh live Discord permissions/Gateway, actual YouTube/CDN/autoplay policy, genuine deployed
dual-process/TCP/proxy/Cloudflare boundary, Linux/Pi capacity/soak/clock-jump or crash SLO claim.
C8/C9 and original report explicitly defer those staging/operational gates; this local Phase6
PASS does not close the later audits. No WSL/install was needed. All database and backup tests
used isolated temporary synthetic paths. No real credentials/data, production/Pi, message send,
permission changes, deployment/restart/systemd, old restore, V1 writer, concurrent production
writer, retained-release cleanup or MyFood/local3000 operation occurred.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` unchanged; this candidate is not deployed.
A0-A5 PASS unchanged. Integrated Audit deployment condition remains unmet; friend activation HELD.
MyFood remains paused and untouched. Owned test/browser/server runs returned and closed their
private resources; final elevated narrow process lookup returned no owned processes at
approximately01:56 UTC (10:56 KST). No owned test/server/browser automation or pending test
write remains; it is safe from this audit to restart/update the app or shut down the PC. No scheduled
continuation or updater is started. Stop after A6V1 and pause for the user's desktop-app update;
A7, Integrated Audit, Phase11, remediation or deployment require separate authorization.
