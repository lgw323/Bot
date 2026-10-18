# A6R1 - Terminal browser playback remediation

2026-10-02. **Local remediation PASS; Phase 6 remains FAIL pending independent A6V1.**
A6-M1 is remediated in candidate `ecd8ef2d69d27199c41eb8941615fa177d1e8834`,
not independently CLOSED. Stop after this microphase; no A6V1/A7 started.

## Authority and scope

Entry branch `codex/rebuild-v2`, HEAD `8d04ed571578076837928a41131ae99b8519f69f`
matched the assignment. Read active-state, ledger and document index first, then the
[A6 report and exact appendix](a6-phase-6-report.md), C8/C9, F037-F043,
ADR-004/005/012/021, original Phase 6 report, current server/client/fixtures and
later Gates23/26/27/29. Repository AGENTS and the explicit narrow remediation
authorization apply. No applicable skill was needed for this repository code/test
change; no sub-agent, package installation or upgrade was used.

Gate29 requires terminal target playback/audio stop and unrelated-room isolation.
Gates23/26's accepted ordinary play action after refresh is unchanged; this is not
a refresh/autoplay acceptance change. F042/FR-043, terminal code4001, authorization,
invite boundaries, HTTP/WS formats, 30+5-second grace, server/database behavior and
visible control labels remain unchanged. No broader product/architecture decision
was required. Historical A6 FAIL and D7 human evidence are preserved.

## Cause and repair

The browser owned both a WebSocket and an independently running iframe. Setting
`terminal=true` prevented future sync/reconnect but did not release the iframe.
Server master-close/known-message cleanup and other-guild isolation already passed.

`player.html` now centralizes terminal cleanup before calling provider code:

- Revoke playback ownership; clear pending playback/cue and release the player reference.
- Destroy the owned player and remove its iframe in `finally`, including partially
  initialized players and provider cleanup failure. No new iframe may be constructed
  after terminal closure. Repeated and reentrant callbacks cannot issue new playback.
- Clear playback polling, acknowledgement, return/reconnect and delayed-add timers;
  unregister page lifecycle/reconnect listeners. Retain only the existing finite
  three-second terminal toast timer. Repeated close callbacks do not restart it.
- Route current-socket terminal4001/4002/4003, best-effort `session_closed`, and
  existing playlist HTTP403/404 terminal paths through the same cleanup. The event
  path acts immediately, without waiting for a close handshake to finish.
- Reject late API readiness, queued media commands, add responses and publications.
  In-flight bounded playlist reads retain their existing terminal-result guards.

Transient4008/1006 reconnect, active/paused hydration, recovery gestures, refresh,
retired socket isolation, another room and normal controls remain covered. Server,
schema, credentials, dependency definitions and V1 code were not changed.

## Reproduction and final evidence

Before edits, the **exact A6 Python appendix** ran from TEMP with the original harness:
**1 PASS / 1 FAIL / 0 SKIP**, 0.88s. The failure was exactly terminal target PLAYING,
42 -> 44s, one socket; control PLAYING44s. The server test passed.

The appendix and its assertions remained byte-identical. The existing harness was
extended to model newly exercised standard APIs: `destroy`, `clearInterval`, and
`removeEventListener`; it also exposes pre-ready and queued callback handles. Registered
listeners are tracked separately from saved callback handles so the unchanged probe can
deliberately deliver already queued online/pageshow events after removal. Destruction
cancels synthetic pending media; no terminal flag itself changes fake media state.
No old assertion or scenario was removed/weakened. The extended harness with the
unchanged A6 probe still FAILS against the entry template, proving the added APIs did
not hide the defect. [Exact observations and template hashes](a6r1-terminal-evidence.json):

| Same probe | Target state/time | Target commands | Control state/time | Exit |
| --- | --- | --- | --- | ---: |
| Entry template | PLAYING / 44 | playing | PLAYING / 44 | 1 |
| Candidate | destroyed (-1) / 42 | playing, destroy | PLAYING / 44 | 0 |

Final completed disjoint selections:

| Selection | PASS | FAIL | SKIP / XFAIL |
| --- | ---: | ---: | ---: |
| Watch integration + Watch characterization (132 existing + 14 new) | 146 | 0 | 0 / 0 |
| Unchanged A6 appendix, server + active-media test | 2 | 0 | 0 / 0 |
| **Pytest total** | **148** | **0** | **0 / 0** |
| Opt-in real Chrome / local HTTP+WS+iframe media scenario | 1 | 0 | 0 / 0 |

The 146-test run took10.75s; the appendix took0.83s. Earlier focused 43 PASS and
final 14 PASS selections overlap and are not added again. Node reruns of the same
appendix also are not extra tests. The known audioop deprecation remains visible;
RuntimeWarning and PytestUnraisableExceptionWarning are errors in final pytest runs.

New scenarios cover active4001/4002/4003, before API load, constructed before ready,
pending media load, delayed session-event close handshake, HTTP403/404, throwing and
reentrant destroy, pending add timer, late add response, repeated callbacks and
retired terminal socket versus healthy reconnected playback. Each terminal scenario
also checks timer/listener release and another room's advancing media.

Commands from repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/watch/ tests/characterization/test_watch_contracts.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe tests/browser/watch_terminal_chrome.py
```

For the unchanged A6 appendix use the exact explicit-config invocation in the A6 report.
The opt-in Chrome script accepts an optional template path, enabling the same assertions
against `git show 8d04ed571578076837928a41131ae99b8519f69f:src/discordbot/watch/adapters/templates/player.html`
exported to a workspace scratch file. That entry template FAILS with
`terminal iframe remains attached`; the candidate passes unchanged assertions.

Chrome154.0.8037.92 runs in a fresh headless temporary profile with local dynamic ports,
proxy/DNS restrictions blocking external hosts, a local synthetic provider and genuine
iframe HTMLAudioElement backed by generated silence. Shipped inline client JS is
unchanged in the served template; only the remote provider script URL is substituted.
Both rooms first play beyond42s. Candidate observation: target42.234401/control42.019348;
after terminal removal target media unloads to0 and remains0, while control advances
to42.990457. Destroy count1; one join each; target cannot recreate via online/pageshow/API
callback. This proves actual browser iframe/media lifetime, not YouTube provider behavior
or audible production output. Existing server/ASGI tests separately prove real Watch
authorization, revocation and cleanup; the Chrome server itself is synthetic.

Development attempts are disclosed, not counted as successful final evidence: the first
new VM run was42 PASS/1 FAIL because the destroy-failure test accessed an uncreated fake
DOM node; corrected lazy node access retained its assertions. Initial sandbox Chrome
crashed and hit temporary crash-report cleanup locking. Two subsequent local Chrome
attempts reached the42s precondition deadline because the synthetic WAV server lacked
byte-range support; range handling was added without changing the precondition. One
baseline launch could not read a sandbox-owned TEMP export, so the identical Git blob
was exported to workspace scratch. Final isolated elevated browser runs completed and
closed their owned browser/server. No shared Chrome or MyFood session was attached.

## Ownership and rollback

[Entry inventory](a6r1-entry-inventory.json): **11 modified /59 untracked, empty index,
70 inherited content hashes**. All70 matched before owned documentation changes.
The original appendix, all prior reports/receipts and mixed work remain preserved.

Implementation commit `ecd8ef2d69d27199c41eb8941615fa177d1e8834` contains the template,
two harness API extensions, new terminal harness/test, opt-in Chrome probe and only
the owned changelog append. Git staged diff and `git diff --cached --check` were reviewed.
The separate evidence commit contains this report, inventory/receipt and only the AQ
active-state append/Phase6 ledger row. Its SHA is provided in the handoff. The mixed
untracked document index gains an A6R1 navigation append but stays uncommitted; prior
mixed authority/changelog content is not swept into either commit.

Preservation verification removes only the owned append/row changes **in memory** and
compares all70 hashes. Expected final residual:11 modified/59 untracked, empty index.
No reset, bulk stage, overwrite of inherited content, remote push or history rewrite.
Rollback: revert only these two scoped local commits in reverse order, preserving
mixed work and historical evidence; no DB, restore or runtime rollback is required.

## Limits and next boundary

No clean full-suite claim. Broad unrelated tests were not run under this focused
assignment. Known inventory/Deno/audioop, A3-N1 MINOR and A3-I1 INFO limits remain.
No live Discord/YouTube/Pi, proxy/Cloudflare, capacity/soak or production permission
verification. No WSL was needed. All DB tests used temporary synthetic databases;
no actual data, credentials, systemd, deployment/restart, old restore, V1, concurrent
writer or release cleanup action occurred. Local3000/MyFood is preserved.

Recorded production source `8e9018d4b8061cde6006eee47fa4103522f77718` and pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain unchanged and undeployed. A0-A5 remain PASS;
Phase6 remains FAIL pending independent A6V1. Integrated-audit deployment condition
is unmet, friend activation HELD, MyFood paused.

**STOP A6R1. Recommend separate independent A6V1 on this candidate:** rerun the original
case, independently assess initialization/terminal races and whole Phase6 contract
coverage, then decide closure. Do not infer closure from this remediation report.
