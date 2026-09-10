# PHASE 6 Watch contract

Date: 2026-09-10. Scope: F037–F043, Watch migration/process split only.

## Ownership and composition

`composition.discord_app.build_discord_runtime(watch=DiscordWatchResource(...))` registers the
lazy Discord Cog and its own request/cleanup supervisor. It holds bounded interaction dedupe
receipts and Discord View handles, not Watch session, playlist, playback or presence state.
`LoopbackClient` is its only Watch state access. Watch failure changes the controller's
`loopback` capability health; Gateway process liveness and other capabilities remain independent.

`composition.watch_app.build_watch_runtime(watch=WatchWebResource(...))` owns a separate
Phase 3 `SqliteDatabase`, `WatchService`, session actors and peer send pumps. Pass an existing,
explicitly migrated, unopened database resource. Startup never bootstraps a missing database.
Public and internal ASGI apps have separate route tables. `build_servers` constructs inactive
Uvicorn servers on distinct literal loopback ports, with access logging/proxy headers disabled,
4096-byte WS frames, WS queue 4, concurrency 96, backlog 64 and 5-second keepalive/shutdown.
No server, Gateway or production entrypoint is started by import or construction. Actual process
launch/service ownership, proxy routing and staging activation remain Phase 8/9 work.

## PRESERVE

- `/시청` has no parameters. Description, public invite, private unavailable/error response,
  invite title, description, link button and master-only close button retain their meanings.
- The configured private admin channel gets the control before the public invite is published.
  The existing `MASTER_USER_ID` exact-match policy remains; participants have no login or host role.
- `/watch?session=CAPABILITY`, GET `/api/playlist/{session_id}`, POST
  `/api/playlist/{session_id}/add` with `video_url`/`added_by`, and POST
  `/api/playlist/{session_id}/remove?video_url=...` retain their routes and payload meanings.
  GET returns `{"playlist": [...]}`; add returns `status`/`title`; remove returns `status`.
- Playlist identity is the original trimmed URL. A duplicate replaces the URL row and moves it
  to the tail. Different sessions/guilds remain isolated. Metadata failure keeps the Korean fallback title.
- Seven client types: `join`, `chat`, `state_change`, `seek`, `sync_request`, `sync_response`,
  `playlist_change`. Playback accepts the actual browser's `state: playing|paused` and Phase 1's
  `playing: bool` form. Join emits `user_joined`, `user_list`, `sync_request`; leave emits
  `user_left`, `user_list`. Relay excludes the sender. Server revisions may have gaps for that reason.
- Creation protects the first **30 seconds**, followed by **5 seconds** empty grace: an untouched
  session closes at t=35, matching Phase 1's two sequential sleeps. Last disconnect uses
  `max(now, created+30)+5`. Reconnect before that deadline clears it; at the deadline expiry wins.

## CORRECT

Durable intent precedes every usable link. Discord acknowledges once, requests durable create,
creates/binds admin control, edits the original public response with the invite, then binds that
message. Failure is not success: the same interaction gets at most one private failure followup,
known messages are retracted and the creation identity is aborted. Cancellation follows the same
compensation path without a new user response. An abort tombstone also blocks a late create.
Local duplicate deliveries are ignored; signed create retries with the same identity return the
same intent/token, or reject a terminal intent. The supported deployment has one Gateway owner.

Each session has one bounded mailbox. It decides revision increments, presence, playback and
playlist mutations, including close. Terminal state is set before awaiting durable close; late
commands cannot add a peer/item or revive the session. Close is idempotent. Failed close remains
terminal in memory and is retried by bounded maintenance or reconciled by the next owner.

Each peer has an independent send pump. Broadcast only performs bounded queue offers. Queue
saturation or a 1-second send timeout disconnects that peer with 4008; socket close itself has a
1-second timeout. Terminal close uses 4001 and drops pending output. A `session_closed` event is
best effort; the close code is authoritative. Invalid handshake/capability uses 4003; protocol
errors use 4002. The browser stops reconnecting for these terminal codes, ignores old revisions,
coalesces playlist fetches and retains at most 200 chat/system DOM entries. Existing player layout
and escaping are retained in a V2-owned template; V1 is unchanged.

## Capability and public surface

The capability is a 43-character base64url HMAC-SHA256 output (256 bits), keyed separately from
loopback authentication. Input includes guild, requester, operation and issued timestamp. Only
its SHA-256 digest is persisted as internal identity. Create is accepted within ±60 seconds of
issue, retries must retain the original timestamp, and lifetime is at most 6 hours. Including the
timestamp prevents cleaned, old operation identities from resurrecting old bearer tokens.
Close/startup revokes the capability. The raw capability appears only where needed for the invite
and browser URL; it is omitted from diagnostic embeds, structured telemetry and stored rows.

State-changing HTTP requires exact configured Origin and `X-Watch-CSRF: 1`; add requires JSON.
WS requires exact Origin. No CORS allowance or login/host model is introduced. CSP restricts scripts
to a per-response nonce and YouTube, frames to YouTube, connection to self, and the existing font/
thumbnail hosts. Inline styles remain necessary for the preserved page. `Referrer-Policy:
no-referrer`, no-store and nosniff protect the page. The browser uses text/escaping for untrusted
names/titles/chat. Public failures contain safe messages/codes only. Uvicorn access logs are off;
the future tunnel/proxy must also redact capability paths/query strings.

| Resource | Default / hard ceiling before Pi measurements |
| --- | --- |
| Sessions / clients per session / total clients | 8 / 8 / 64 |
| Mailbox / peer outbound queue / playlist | 100 / 16 / 100 |
| WS application frame / HTTP body | 4096 / 8192 bytes |
| Combined path+query / headers | 4096 / 16384 bytes |
| Public HTTP requests / internal HTTP requests / bot loopback calls | 32 / 8 / 8 |
| Peer rate / session rate / public HTTP rate | 10 / 80 / 80 per fixed second |
| Public operation / internal operation / mailbox deadline | 10 / 5 / 5 seconds; body read separately capped at 5 seconds |
| oEmbed | 2 active + 4 waiting; total 5 seconds; 64 KiB response; no retry |
| watch-web / Discord Watch supervised task slots | 96 / 12 |
| Durable intents / control replay receipts / bot interaction receipts | 10000 / 256 / 256 |
| Admin View handles / cleanup page / cleanup batch | 128 / 100 / 8 |

These are conservative proposals, not measured Pi SLOs. Invalid input, rate/capacity, revoked/
expired capability, DB failure, loopback authentication, Discord delivery, WS protocol, metadata
failure, deadline and shutdown have safe typed boundaries. Metadata requests use only the fixed
YouTube oEmbed origin with a validated 11-character video ID and reject redirects.

## Persistence and stale cleanup

Additive migration **4**, `watch-process-ownership`, adds `v2_watch_owner` and `v2_watch_intents`.
Migrations 1–3 and legacy table shapes are unchanged. Phase 3 validation, migration checksum and
encrypted backup allowlist cover both new tables. Old readers can still read session/playlist rows;
V2 rows use opaque digest identities, not bearer tokens. This is data compatibility, not permission
to run both V1 and V2 Watch writers against one live database.

A transaction claims a 10-second writer lease. An unexpired different owner prevents startup
cleanup. A replacement after release/expiry closes prior intents, removes prior runtime session/
playlist rows and retains Discord message cleanup receipts before readiness opens. Legacy stale
identities are hashed rather than copied as capability diagnostics. Every writer operation checks
the owner epoch/lease; public admission and queued mutations also check local lease validity.
Maintenance renews every second and checks session expiry concurrently with a bounded supervisor.
Cleanup failure degrades readiness and closes old peers. No task can renew an already lost lease.

Discord polls cleanup every 5 seconds, deletes known invite/admin messages idempotently, then
acknowledges the durable receipt. Failed deletion remains pending. Closed/cleaned receipts are
removed only after their capability expiry. Pending receipts are retained under the hard cap;
capacity exhaustion rejects new work instead of silently dropping cleanup evidence.

## Shutdown and limitations

Watch shutdown stops admission/maintenance, terminally closes actors, allows at most 5 seconds
for durable closure, cancels/drains supervised work with 1-second grace, releases the writer lease,
closes metadata and finally the Phase 3 DB resource. Cooperative adapter deadlines bound cleanup.
Discord has its own supervisor/client/View cleanup and does not stop the Watch process or Gateway.
Compensation has a 2-second budget and at most three attempts, followed by bounded UI cleanup.
Master close uses the Discord supervisor's shared capacity and an 8-second deadline.

SQLite and Discord cannot form one atomic transaction. If both transport response and subsequent
compensation are unavailable, no success is reported; the unattended session expires through normal
grace, or the next web owner closes it. An admin send whose response is lost can leave an unknown
message ID that cannot be deleted automatically; its capability/session is revoked and its View
times out. Known messages use durable cleanup receipts. Browser reload/reconnect after a web
process replacement requires a new invite. Distributed delivery certainty, real browser/YouTube
behavior, proxy security, lease sensitivity to host clock jumps and Pi timing remain staging gates.

The actual `docs/rebuild/bot_database.db` was not opened, read, hashed, copied or modified in Phase 6.
