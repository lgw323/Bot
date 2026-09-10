# PHASE 6 Report

Date: 2026-09-10. Scope: Watch migration / process split only.

## Phase 6 Complete

PHASE 6 F037–F043 implementation and synthetic verification are complete. Phase 5 baseline
`5c68659` was clean at entry; recent commits `c81f4d1`, `643b75a`, `5c68659` matched the Phase 5
report/current documents. Baseline rerun: **434 passed, 4 xfailed**. No discrepancy was found.
The completed implementation has **504 passed, 2 xfailed**. Phase 7 has not started.

## Implemented

Watch session application/ports/adapters, additive storage metadata, authoritative session mailbox,
independent peer pumps, HTTP/WS/browser adapters, bounded oEmbed, signed loopback client/server,
Discord invite/admin/cleanup orchestration and opt-in independent composition resources.
Detailed policy and limits: [Watch contract](watch-contract.md), [loopback contract](loopback-contract.md).

## Tests

All commands used Python 3.12.14 in the existing `.venv`, with `PYTHON_DOTENV_DISABLED=1`.

| Executed verification | Result |
| --- | --- |
| Entry baseline `python -m pytest tests/ -q` | 434 passed, 4 xfailed |
| Final `python -m pytest tests/ -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning` | 504 passed, 2 xfailed, 28.04 seconds |
| Watch integration + architecture strict checks | 82 passed (68 Watch + 14 architecture) |
| Data/migration + existing Engagement compatibility + Watch data/runtime/lifecycle | 96 passed |
| 14 deterministic race/lifecycle scenarios × 100, final code | 1400 passed, 1700 deselected, 167.36 seconds |
| V2 browser inline JavaScript via `node --check` | exit 0 |
| Phase 5 vs final Watch PRESERVE function AST comparison | 7 unchanged functions; parameterized cases retained |

The only warning is the existing Discord `audioop` Python 3.13 deprecation warning. RuntimeWarning
and unraisable-warning checks passed. An intermediate collection collision between equal test module
names was fixed by packaging the Watch integration directory; the final full run collected normally.
No external API, production data, listener, Gateway, Pi or Cloudflare endpoint was exercised.

Repeat command used `pytest.main` with the three files `test_runtime.py`, `test_lifecycle.py`,
`test_discord.py` repeated 100 times, `--keep-duplicates`, strict warning flags and a `-k` expression
selecting the following 14 test names (all under `tests/integration/watch/`):

- `test_seven_messages_order_and_session_isolation`
- `test_creation_grace_and_reconnect_boundary`
- `test_playlist_duplicate_order_close_race`
- `test_slow_peer_queue_is_bounded_and_fast_peer_progresses`
- `test_connection_capacity_and_shutdown`
- `test_create_cancel_after_commit_compensates_and_cannot_retry`
- `test_stale_cleanup_readiness_barrier_and_failure`
- `test_new_owner_cleans_dead_owner_and_old_peer_cannot_mutate`
- `test_mailbox_saturation_cancelled_waiter_and_close_are_bounded`
- `test_add_metadata_late_result_cannot_revive_closed_session`
- `test_session_cap_and_maintenance_schedule_idempotence`
- `test_duplicate_discord_delivery_and_single_admin_control`
- `test_full_signed_loopback_command_signature_binding_and_master_cleanup`
- `test_close_during_durable_create_cannot_leave_an_orphan_actor`

CF-10/11/12/13/16/19/20 are covered by these tests plus cancellation/failure parameterizations,
real in-process ASGI WS tests and the separate process-composition tests. Fake clocks/barriers choose
the order; no long wall-clock lifecycle sleeps are used. The actual 1-second slow-send deadline has
one dedicated bounded test. These results establish invariants, not Pi p95/soak or crash SLOs.

## Architecture Check

Domain/application remain vendor/SQLite-free. All feature background work enters TaskSupervisor;
no feature-level raw `create_task` or executor dispatch was added. Composition reaches adapters only.
Fresh-process imports do not start DB, network, threads, subprocesses or servers. Additional child
interpreter tests prove each composition root's transitive import closure excludes the other runtime.
The earlier blanket ban on all Watch imports from Discord composition is now narrowed to permit
only the Discord-side Watch resource; transitive isolation is checked separately.

## Process Isolation

The Discord resource contains the Cog, UI/control client and its own supervisor. The web resource
contains the DB, session actors and separate public/internal apps. No session object or dictionary
is passed to Discord. The full integration harness crosses serialized, signed HTTP through an ASGI
transport. Web readiness/lease failure does not stop Discord liveness. Inactive Uvicorn objects are
configured, but two live OS services and crash/kill integration remain Phase 8/9 validation.

## Loopback Contract

Literal loopback/port validation, separate route tables, HMAC request authentication, timestamp and
nonce replay window, bounded JSON envelopes, exact response schemas, correlation echo, deadlines,
create idempotency and close/abort/bind/cleanup/ack are implemented. Synthetic keys only.
The same creation identity can abort a response-lost create; tombstones reject late creation.

## Browser / HTTP

Known page and playlist routes/body/query behavior are preserved. Invalid/expired page retains the
existing Korean HTML 404 guidance. The V2 template preserves the player UI and safe DOM rendering,
adds nonce CSP/CSRF, terminal reconnect handling, monotonic revision filtering and coalesced playlist
loads. Route/body/schema/Origin/error/closed-session behavior runs in ASGI tests; JavaScript parses.
Actual YouTube iframe playback, CDN availability and visual cross-browser behavior remain staging.

## WebSocket Protocol

All seven client types, actual `state` and characterized `playing` payloads, join/leave/relay behavior
and invalid-session 4003 are covered. In-process ASGI tests exercise accept/join, malformed JSON,
unknown type and oversized frame closure. Server close 4001 and protocol/capacity 4002/4008 stop
browser reconnection. No raw protocol payload is logged.

## Session Ownership / Ordering

One mailbox per session owns all mutable state/revisions and serializes playlist writes. Each
command has a five-second deadline, cancellation-aware reply and bounded admission. Close is
terminal before persistence; duplicate close, add/connect/close races and late metadata/queued
commands cannot resurrect state. Tests prove session/guild isolation and strictly increasing observed
revisions (gaps are valid because relays exclude the sender).

## Capability / Security

256-bit HMAC capability, digest-only persistence, issued timestamp, six-hour maximum lifetime,
revocation, exact Origin/CSRF, nonce CSP, escaping and hard size/rate/cap controls are implemented.
Capability text is removed from diagnostic fields and telemetry. Future reverse-proxy access logs
must redact paths/query strings too. Login and host permissions were not introduced.

## Lifecycle / Expiry

Phase 1 explicitly characterizes 30 seconds creation protection followed by 5 seconds empty grace;
no-participant expiry is t=35. Tests cover 29.999/30/34.999/35, last disconnect, reconnect at 4.99 and
the five-second boundary, absolute expiry, owner loss and repeated lifecycle scheduling. A lease
transaction gates stale cleanup before readiness and protects another unexpired active owner.

## Slow Peer / Backpressure

Outbound 16 per peer, send/close deadline one second, independent supervised pumps. Saturation
closes only the slow peer with 4008; normal peers and another session continue. Queue/task/session
caps and shutdown leave no owned task/peer backlog in the test harness.

## Playlist / oEmbed

URL-keyed replacement-to-tail, ordering, remove query, invalid URL, capacity and session isolation
are preserved/verified. Metadata has a fixed YouTube origin, validated video ID, no redirect/retry,
two active/four waiting calls, five-second deadline and 64 KiB response cap. Timeout/status/schema/
size failure preserves the fallback title; overload remains a typed capacity error.

## Failure / Cancellation

Durable-create failure sends no link. Response-lost create, admin failure, invite failure, bind
failure and cancellation revoke/abort; one initial ACK and one legal private failure followup are
verified. Compensation has at most three attempts within two seconds; known UI cleanup is bounded.
Unknown Discord message IDs after an uncertain send cannot be recovered automatically. Failed known
deletions remain in durable cleanup receipts. Neither uncertainty is reported as normal success.

## Data Compatibility

Migration 4 adds only owner/intent metadata. Tests compare unchanged migration 1–3 ledger rows,
unchanged synthetic source hash, V1 session/playlist readers, cross-guild readers and full encrypted
backup/restore metadata checksums. Corrupt metadata/checksum fails closed. No legacy schema or music
snapshot format is changed. The actual `docs/rebuild/bot_database.db` was not opened/read/hashed/
copied/modified; every DB/backup used in Phase 6 tests is temporary synthetic data.

## Pi / Cloudflare Impact

None. No package install/upgrade, systemd, DNS, Tunnel, TLS, production token, deployment, remote
backup activation, Git push or PR. Existing dependencies are sufficient. The copied V2 template is
included in setuptools package data. Production entrypoints remain unchanged.

## Compatibility

All PRESERVE regressions pass, including unchanged Watch characterization bodies. Engagement and
Summary behavior remain unchanged; only assertions for the latest additive migration version move
from 3 to 4. V1 runtime is retained. Corrected capability/ordering/security/lifecycle behavior applies
only to the opt-in V2 paths.

## Corrected Legacy Bugs

Watch strict xfail 2 → pass through the full V2 signed-client/server/database/Discord adapter path:
`test_f037_fr004_fr038_correct_watch_commits_before_invite` and
`test_f037_fr004_fr010_correct_watch_failure_uses_single_responder`.
Additional approved corrections cover process coupling, unbounded slow peers, ordering/close races,
unsafe startup deletion, replay and unbounded public input. Music's two strict xfails remain unchanged.

## Documentation Updated

This report, Watch/loopback contracts, current plan/trace/open questions/ADR-021, rebuild index,
README structure row and CHANGELOG. Frozen baseline and Phase 0–5 documents remain unchanged.

## Remaining Risks

- Capacity/deadline values are conservative hard ceilings, not measured Pi limits/SLOs.
- Real Gateway permissions, admin channel privacy, send uncertainty, browser/YouTube, actual dual
  process crash/kill, loopback/proxy forwarding and 24-hour Pi soak remain Phase 8/9 gates.
- Clock jumps can expire a writer lease; fail-closed replacement intentionally invalidates old links.
- A web restart cannot recover connected browser sockets; stale sessions require new invites.
- Discord and SQLite are not atomic; unknown message IDs can remain after uncertain sends. Closed
  capabilities and bounded durable cleanup prevent treating this as successful session publication.
- V1 and V2 Watch writers must not run simultaneously against one database during future cutover.

## Next Phase Gate

PHASE 7 Music requires a new user instruction. Its pagination/snapshot/default/ACK corrections and
two xfails are untouched. Production data migration/cutover still requires the Phase 10 approval gate.

## Decision Required

None for this Phase. Existing accepted capability/hostless model and process split were implemented.
Remaining items are planned staging/measurement gates, not requests for new product behavior.

## Commit / rollback

Staged diff and `git diff --cached --check` were reviewed for each focused commit:

| Commit | Responsibility |
| --- | --- |
| `4c31a83` | `feat: add bounded Watch session ownership and durable lifecycle` |
| `cf222bf` | `feat: isolate Watch web surfaces and authenticated control transport` |
| `93b6d0a` | `feat: connect Discord Watch interactions through isolated loopback` |

This report/current-document update is the separate `docs: complete V2 phase 6 Watch migration`
commit; its identity is available in the Git history for this file. Nothing was pushed or deployed.

No operational process was activated, so reverting these feature commits in reverse order returns
the code to `5c68659` without an operational data rollback. Future staging rollback must keep a verified
pre-migration candidate: Phase 5 V2 validation does not recognize migration-4 metadata, even though
V1 CRUD readers remain compatible. Restore the verified earlier version to a new path; do not drop
tables or rewrite a live database to downgrade. Never undo unrelated user changes or rewrite history.
