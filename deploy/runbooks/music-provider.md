# Music provider repair and live smoke

PHASE 10B reproduced the acquisition failure under the stopped production release's
Python 3.12.3, service user, cwd, sandbox and cache path (private bind-mounted cache).
The public control reached PCM and Opus. The failing class passed metadata lookup
but yt-dlp 2026.7.4 returned HTTP 403 / exit 1 while downloading audio. Changing
M4A to WebM did not fix it; an audio HLS selection was unavailable. Adding Deno/EJS
to that old pin also did not fix it. No URL, title or provider stderr is retained here.

With yt-dlp 2026.8.19, the same failing class downloaded 2,525,278 bytes and reached
3840-byte PCM, fake VoiceClient acceptance and 96-byte Opus encoding. Both the
without-JS and with-JS comparisons passed. This identifies the old provider path
as the reproduced compatibility failure; it does not prove a particular YouTube
server-side rejection mechanism or actual Discord audibility.

Keep all unrelated dependencies fixed. The new sealed set supplies yt-dlp's
matching EJS 0.8.0 and Deno 2.9.7, which were missing from the previous deployment
inventory. The adapter selects the runtime beside the release's Python and disables
remote component downloads. Deno/EJS completeness is separate from the demonstrated
old-pin 403 failure. Do not use account cookies or enable automatic updates to mask
a failing smoke. Retain the old wheelhouse and immutable release unchanged.

Sources: [upstream provider release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19),
[EJS setup contract](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
[official Deno Python distribution](https://github.com/denoland/deno_pypi).

Tests use synthetic child processes, temporary cache and fake Discord transport.
The isolated ARM64 media check must also run against the exact new release before
asking for production pin approval. Actual Music audio and TTS remain live gates.

The live operator arms a root-owned `/run/discordbot-live-smoke` regular file before
starting the approved release. In that mode the first lookup/acquire/start/TTS or
audio callback failure latches Music admission closed, stops audio and retains the
current track/queue for the normal shutdown checkpoint. It never admits the 3-second
retry. Readiness becomes false. `deploy/production/observe-smoke.py` checks safe
journal evidence every 0.25 seconds (health every 5 seconds), stops the pair and
copies the newest data/state/audit into a fresh private preservation directory.
The observer requires the marker and never overwrites an old output directory.

Keep the marker through live smoke and bounded observation; remove it only after
all required gates pass. A successful process then uses the normal 3/8-second retry
policy without a restart. A failed process stays latched until a reviewed restart.
The marker lives in `/run`, is absent after boot, and is never user data or config.
No candidate replay, DB restore, down-migration or V1 restart belongs to this flow.
