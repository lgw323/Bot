# Watch real Chrome verification

This is an **opt-in, networked browser investigation**, separate from the offline
`pytest tests/` suite. It uses an already installed Chrome and Playwright; it does
not install packages or change application dependencies. No production config,
DB, credentials, invite or browser profile is used. The fixture binds only to
127.0.0.1:8765, uses a temporary synthetic SQLite DB, and serves the real Watch app.
The media is the public example from the official YouTube IFrame API reference.

1. Set `PYTHON_DOTENV_DISABLED=1` and `PYTHONDONTWRITEBYTECODE=1`. Run
   `python tests/browser/watch_fixture.py` with the existing development Python.
2. Make the existing Playwright package available through `NODE_PATH` if needed.
   Set `WATCH_CHROME` to the installed Chrome executable, `WATCH_TCP_FAULT=1`,
   `WATCH_STRICT_AUTOPLAY=1`, and `WATCH_BROWSER_RESULT` to an ignored scratch JSON.
   Run `node tests/browser/watch_real_chrome.cjs`.
3. POST to the fixture-only `http://127.0.0.1:8765/fixture/shutdown` to stop cleanly
   and remove the temporary synthetic DB. Never expose this fixture server.

For a pre/post warm-cache regression, serve the exact old HTML with
`--template <offline-exported-player.html>`, and set `WATCH_REFRESH_ONLY=1` for the
browser runner. This creates an already-playing room using the real iframe API
and real WebSocket, then reloads the same room. It isolates reload startup from
initial-selection bugs. Repeat with the current template. The old template must
FAIL with snapshot present / iframe absent before claiming that the startup race
is reproduced. The all-feature run uses the ordinary playlist selection UI.

The real-browser runner preserves HTTP caching (no Playwright response routing),
records only hashes, safe event categories/revisions/booleans/positions, and keeps
all capabilities, video identifiers/URLs, names and raw payloads out of evidence.
Read-only CDP probes use `userGesture=false`: ordinary automation evaluation can
otherwise enable autoplay and accidentally hide the blocked-client case.
`X-Watch-Client-Revision` is the SHA256 of the served UTF-8 template before the
per-response CSP nonce substitution; normalized HTML and inline JS hashes are
also recorded. Compare this header with the exact candidate asset, not just the
server pin. Headers must remain `no-store` without an ETag. The page registers no
service worker. A production browser/cache/Cloudflare identity check still needs
the actual public response; localhost evidence does not substitute for it.

Two independent browser contexts are valid independent participants: the server
creates a unique peer per WebSocket. This runner verifies two distinct server
peers, play/pause/seek propagation, an actually blocked client's inability to
overwrite authority, explicit recovery, and no duplicate after reconnect.
For the final user check, normal Chrome plus Incognito/another isolated profile
can therefore replace waiting for a friend. Count actual server clients too.

Chrome 153's DevTools Offline did **not** interrupt an established WebSocket in
the observed environment. Do not call that a reconnect PASS. The optional local
TCP proxy cuts the second context's real socket while the first keeps the room
alive; it observes clients 2→1→2, playing/paused hydration and terminal closure.
It is restricted to the local fixture and necessary public YouTube TLS tunnels,
does not decrypt TLS, and is not a production proxy. A future approved public-path
check needs an equivalent single-context TCP interruption through an audited
public-host TLS relay, or a real network interruption of one device while another
stays connected. Do not disconnect every client beyond the existing 5-second
empty-room grace and call the resulting expiry a reconnect defect.

Never run auxiliary Python polling processes on Pi while production live
validation is active. Read the existing observer's safe output with cat/SCP;
do not broaden the writer guard. This fixture is local-only and must be stopped
before final cross-platform candidate verification.
