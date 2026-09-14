# PHASE 9 Staging Report

## Phase 9 Status

LOCAL / SYNTHETIC STAGING VERIFIED; LIVE / NETWORK GATES OPEN. Started 2026-09-13,
local verification completed 2026-09-14. Baseline `7d596ade8c721931437560ad9e6828762018972c`
was clean; Windows full strict recheck: **673 passed, 0 xfailed, 34.40s**. Existing
discord.py audioop deprecation is the only warning. Production cutover is not authorized.

After the Pi permission/credential fixes, Windows full strict recheck: **688 passed, 0 xfailed,
30.76s**. Live integration remains explicitly blocked; this is not production readiness or cutover approval.
Final whole-suite rerun after staging tooling/documentation: **688 passed, 0 xfailed, 32.80s**.

The user explicitly confirmed no staging Discord/Gemini credentials or approved guild/channel/origin
exist. Existing PC `.env` must not be read/copied/used. Live external integrations are blocked;
credential-free Linux/synthetic tests continue. Existing interactive sudo is used through visible SSH
windows with operator password input. No passwordless policy, new SSH key or authentication storage.

## Host Inventory

Existing SSH alias reused; private key contents not read. Host `bot`: Raspberry Pi 5, Ubuntu 24.04.4
LTS, ARM64/aarch64, kernel 6.8.0-1064-raspi, four Cortex-A76 cores up to 2.4GHz. RAM 8,322,748,416 bytes,
no swap. Root/data share ext4, 125,555,904,512 bytes total, initially 117,536,235,520 bytes available.
Ethernet eth0 up; wlan0 and loopback also present. Python 3.12.3, Git 2.43.0, systemd 255.4-1ubuntu8.17;
Asia/Seoul with NTP synchronized. Initial temperature 58.2 C, throttle flags 0x0.

No `/opt/discordbot`, `/var/lib/discordbot`, `/etc/discordbot`, legacy `/home/os/bot` or `bot_env`,
project units or listeners on 9000/9001/9010/9011 existed. cloudflared was already active/enabled;
its update timer was disabled. Existing connector configuration remains untouched.

## Installation

Initial system lacked pip, ensurepip/venv package and FFmpeg. Hash-verified official pip 24.0 wheel
was used only in an isolated operator workspace for dependency download; no global pip install.
`provision_host.py` then prepared Python venv/FFmpeg packages and dedicated runtime/deploy users/paths
through operator interactive sudo. Top-level layout permissions were observed: release root 2750,
persistent root 2770, config root 0750, expected dedicated ownership.

`install_local.py` installed the reviewed source/wheelhouse, offline bootstrap environment and fresh
synthetic DB/HMAC/capability keys, with an explicit synthetic marker. It created no Discord/Gemini
credentials. The initial `/opt` release was built in place and the synthetic canonical database was
explicitly bootstrapped to ledger 5. No existing production database was used.

## ARM64 Dependencies

All **59 exact Phase 8 pins** downloaded as compatible ARM64/universal wheels from PyPI. Existing pins
were unchanged. Wheel METADATA and SHA256 were sealed using the Phase 8 tool. Offline `--no-index
--no-deps --require-hashes --only-binary=:all:` installation into an isolated validation venv completed
in **15.138s**; `pip check` returned no broken requirements. Actual Pi Operations+architecture strict
suite: **95 passed in 9.54s**, using actual Linux symlinks. Native ABI coverage is limited to exercised
imports/tests; real Voice/provider execution is not implied.

## Release Build / Identity

Selected code/test/deploy/Markdown source was exported from exact `7d596ad`; no DB, SQL backup, secret
or logs were included. Archive SHA256: `8ab5ade68750d93a60af6652b2ed9ead7a274751aa7ee036f851cfcff6add3fb`.
No push, history rewrite or remote authentication setup was performed.

Actual isolated Pi build/publish/activate validated **17,277 files**, Python 3.12.3, read-only release,
materialized venv lib64, real current symlink and offline deployment test subset. Total **126.93s**;
candidate build milestone **35.583s**. Identity `r-7d596ade8c721931-d026a47ed4f4b38a`;
wheel-lock SHA256 `d026a47ed4f4b38ad8b7d3ba4fb70d18a42f9abadce0ace763ca01329b80f394`.
This first proof used `/home/os/discordbot-phase9/release-validation`; installation at the contract
`/opt` location is tracked separately and requires a fresh build, never moving installed venv shebangs.

## Linux Filesystem / Permissions

Actual ext4 scratch probe passed atomic symlink replacement + directory fsync, setgid inheritance,
0660 DB/WAL/SHM under umask 0077, SQLite snapshot/integrity/reopen, cross-process flock exclusion and
release. Duration **2.762s**. Only newly created temporary synthetic files were used and removed.
This probe alone does not prove power-loss durability; cross-identity service access was subsequently
checked in the actual Watch mount namespace, as recorded under Security / Secrets.

## systemd Services / Timers

Installed units passed `systemd-analyze verify`; daemon reload and the first two-process start were
executed. Both processes failed before admission because the original release manifest was owner-only
readable; restart limit stopped the retries after three restarts. Production Discord stayed inactive.
The local peer is explicitly named
`discordbot-staging-discord.service`, contains no external credentials and exposes
`staging_synthetic_gateway=1` plus `/health/staging`. Production Discord remains a credential blocker.
Actual Watch uses the production executable from the corrected release. After successful installed
backup execution, the reviewed four-hour backup timer and the two staging services were enabled for
boot. Backup timer reports Persistent=yes and next trigger 2026-09-14 13:00 KST. Production Discord,
automatic update and manual polling timers were not enabled. No four-hour elapsed-run claim is made.

## Runtime / Health

Release `r-bb0fca6cf8b97586-d026a47ed4f4b38a` passed actual pair readiness and liveness smoke.
Watch and the synthetic peer ran as separate PIDs. Individually stopping each left the peer PID and
liveness unchanged. Clean stops took 0.343s (synthetic peer) and 0.592s (Watch); start-to-ready took
19.818s and 20.178s respectively. Both reported systemd Result=success and NRestarts=0 after recovery.
Synthetic peer success does not count as Discord Gateway, Music restore, command sync or Gemini success.

## Deployment / Rollback

The first actual installed deployment transaction completed in **134.1s** for `bb0fca6`, including
offline candidate tests, synthetic backups, publication, service stop, atomic switch, start, readiness
and smoke. systemd recorded success, 449.5MB peak memory and no swap. A second exact source identity
`0376f14` then ran to healthy smoke before an explicit test-adapter smoke failure was injected once.
The actual transaction returned `failed/smoke`, **rollback=ok**, in **196.616s**, restoring `bb0fca6` code
and venv with coherent readiness. Retrying the same candidate without fault completed normally in
**125.058s**. Current is `r-0376f14868461d16-d026a47ed4f4b38a`. The fault is a disclosed synthetic gate,
not an external outage; separate real one-process stops proved peer isolation.

An additional actual split pair ran the synthetic peer on `bb0fca6` and Watch on `0376f14`, both locally
ready. The unmodified operations coherence gate rejected the differing identities. Stopping Watch
also produced the expected unavailable-peer rejection. The temporary alternate process was stopped,
and the normal `0376f14` pair recovered in **20.071s**. This proves actual gate behavior; only the
smoke-gate fault was wrapped in a complete failed-deployment rollback transaction.

## Backup

The installed `discordbot-backup.service` completed successfully in **19.192s** (including launcher
validation). Direct online encrypted snapshot measured **0.148s**, archive **4,961 bytes**, mode **0600**.
Repeated actual backup creation retained exactly eight archives. The verified timer was subsequently
enabled and remained active after reboot; its scheduled cadence was not accelerated or falsely elapsed.
No remote backup destination/adapter is configured.

## Restore Rehearsal

Installed synthetic backup copies restored to isolated paths: newest selected in **0.064s**, corrupt
newest skipped for previous in **0.065s**. Wrong key, authenticated payload tamper (with recomputed outer
checksum) and incompatible schema metadata were rejected without exposing destination DBs. Faults
modified only separate drill archives, preserving canonical recovery evidence. Canonical synthetic
promotion then succeeded after both staging processes stopped and candidate ledger/digest were
validated under the shared operation lock. Stop plus promotion measured **0.885s**; both services
restarted and passed readiness before reboot. Actual preserved production DB remains entirely excluded.

## Reboot Recovery

Actual host reboot completed on 2026-09-14. Boot ID changed, current stayed on `0376f14`, both staging
services automatically started under distinct new PIDs with NRestarts=0, and both live/ready endpoints
matched the same release. The synthetic promoted DB remained valid and no empty bootstrap occurred.
Backup timer remained active with the same next trigger. Existing cloudflared recovered active (one
restart recorded after boot); its configuration was not changed. Live Music checkpoint/voice recovery
remains unavailable without approved Discord staging credentials.

## Cloudflare / Network

Existing cloudflared active; no reinstall, DNS/hostname/route changes. Public Watch hostname and route
are not approved and remain blocked. Internal control/health must stay loopback-only.

## Discord / Gemini / Voice / Provider Smoke

BLOCKED: no staging-safe Discord/Gemini credentials, guild/channels or public origin. PC `.env` has not
been used. No login, command sync, friend-server messages, Gemini request, voice, YouTube or TTS smoke.

## Resource Measurements

Initial host memory used approximately 393MB, available 7.93GB. During isolated release inventory,
builder RSS approximately 33MB, CPU about 78% of one core, temperature 66.4 C and no throttling.
After lifecycle recovery, synthetic peer RSS was 52,648 KiB and Watch 68,472 KiB (combined 121,120 KiB).
FD counts stayed 7 and 9; threads were 3 and 3–4. Startup includes full immutable inventory validation.
These values do not represent a live Discord/Voice/Gemini workload.
After the final pair-fault drill, filesystem available space was 114,630,316,032 bytes and temperature
66.1 C. Startup/release hashing is included in measured CPU/temperature costs; limits were not raised.

## Load / Soak

An actual **60.159-second** observation sampled both ready services six times. No restart or FD growth
occurred. RSS grew 44 KiB (synthetic peer) and 192 KiB (Watch) from first to final measurement; temperature
fell from 64.45 C to 57.3 C after startup. This short observation does not establish long-term leak
freedom. Longer observation remains a production prerequisite.

Actual ARM64 source tests for Summary requests, Watch lifecycle/caps, DB concurrency and Music
lifecycle/multiple-guild actors passed **69 tests in 8.46s** with fake external adapters and temporary
DBs. Initial collection required an explicit `tests` helper import path after excluding the legacy
root conftest; rerun passed. These are bounded synthetic workload tests, not live provider throughput.

Actual loopback health/metrics load: concurrency **8**, **640 requests over 30.109s**, **0 errors**,
p50 **159.525ms**, p95 **182.501ms**, maximum **271.679ms**. Both services remained active with
NRestarts=0 afterward. This workload includes client/opener overhead and is not an external SLO.

## RPO / RTO Evidence

Accepted targets remain RPO <=6h and approximate RTO 1h. Actual installed backup/restore timing and
service recovery measurements are synthetic only. The measured small synthetic restore/fallback times
above are evidence for isolated recovery only. Local-only backups do not prove off-host disaster recovery.
Final metric samples reported backup age **901.726s / 902.469s**, `backup_rpo_exceeded=0` and both
processes ready. Last sampled DB execution was **0.769ms / 9.135ms**; these are individual samples,
not latency percentiles. The timer still reported active/success with the next scheduled trigger.

## Security / Secrets

No preserved production DB open/read/hash/copy/modify. No PC `.env`, SSH private-key content, production
secret, credential value logging or password storage. Operator types sudo password in SSH terminal.
Synthetic local crypto keys stay in private OS-managed files. No security policy relaxation.

Inside the actual Watch mount namespace, the runtime UID could read only its mounted capability and
control credentials, could not read the operations DB key or source secrets, could write the data
directory, and could not write the release manifest or config. Credential directory contained exactly
`capability_key` and `control_key`. Synthetic DB and shared operation lock both had mode 0660 and
dedicated group ownership. All four listeners (9000/9001/9010/9011) bound only 127.0.0.1.

Trusted-caller polkit queries for explicit unprivileged PID/start-time/UID subjects returned authorized
(0) only for deploy-user Watch stop; runtime-user Watch stop and both users' SSH stop required
authorization (2). No unrelated service action was executed. An initial unprivileged caller query
returned 127 because modern polkit restricts action-detail queries to trusted callers; this was a
probe correction, not a policy change.

## Observability / Audit

Actual health/metrics were exercised under load. Successful deployment/rollback/backup/recovery
transactions completed their durable audit gates. A bounded scan of 500 current-boot staging journal
messages found no configured obvious credential markers; this marker scan is not proof against every
possible disclosure. Raw journal contents were not copied into reports. Staging progress files contain
safe result/timing/release metadata, never secret values or actual user data.

The actual manual CLI with only the Discord unit mapped to the local peer accepted one restart,
rejected overlap/duplicate requests, restarted in **40.067s**, returned completed replay as a no-op,
and preserved an injected `in_progress` request without replay. The explicitly injected state was
reconciled while preserving receipt/history. The installed unmodified manual service then consumed
the reconciled state as a successful no-op. Network update/deploy requests remain gated by the missing
approved remote ref/update policy; no production Discord administration button was connected.

## Deviations Found on Pi

- Missing venv/FFmpeg prerequisites required explicit package preparation; no general dependency upgrade.
- Initial sudo noninteractive failure is expected; user confirmed interactive operator authentication.
- Windows symlink-model limitation is now covered by actual Linux tests/probe.
- Python isolated mode ignores `PYTHONDONTWRITEBYTECODE`; source imports generated 21 bytecode files
  and correctly failed the builder's source inventory gate. The helper now disables bytecode before
  importing source, and isolated execution uses `-B`. A scoped repair removed only those generated
  files before the initial database/current existed. A subprocess regression verifies the fix.
- The original immutable manifest mode 0400 prevented the dedicated runtime user from reading a
  deploy-owned release. Publication now uses 0550 for directories/executables and 0440 for ordinary
  files, retaining read-only releases and excluding other users. Four mode regressions were added;
  the old immutable release was not patched in place.
- Actual systemd 255 credentials use root-owned 0440 files with a POSIX ACL granting only the target
  service UID read access. The group mode bits represent the ACL mask; the group entry grants no
  access. The loader now accepts only this exact five-entry service-exclusive ACL shape, obtained
  from the opened file descriptor. Ten regression cases cover accepted and rejected ACLs; no
  credential value was output or mode weakened.
- The first corrected-source transaction failed before deployment because of that credential ACL
  assumption. A subsequent wrapper retry failed during unconditional `reset-failed` on units already
  inactive/success. The wrapper now resets only failed named units and can resume an existing source
  only after exact archive inventory/content reconciliation. The corrected transaction succeeded.
- One automatic approval attempt failed from a usage-limit error. Another rejected service/polkit scope;
  rereading the explicit PHASE 9 authorization and resubmitting the same action obtained approval.
  Neither rejection was bypassed; no denied action ran before approval.
- The first installed split-pair probe failed its initial single readiness read before stopping any
  service. Three subsequent paired reads were all HTTP 200/ready. The precise transient cause was not
  established; the probe now uses the existing bounded 70-second readiness gate and records failure
  stages. This does not change the production readiness implementation or turn failures into passes.

## Changes Made

Added narrowly scoped staging preparation/install/filesystem/build/local-runtime scripts under
`deploy/staging/`. These are explicit test/operator tools, not production credential substitutes.
Focused commits preserve independent file responsibilities. The first two production corrections
include their direct regression tests; the remaining tools are explicit, finite staging drills.

## Remaining Risks

Live Discord assembly/Gateway/commands, Gemini, Voice, providers and Music checkpoint recovery remain
unverified because staging credentials/config are unavailable. Public origin/proxy route is unapproved;
off-host backup is absent. Network auto-update lacks a published approved ref/policy. Long soak,
power-loss durability and production-size capacity/RPO/RTO remain prerequisites. Synthetic success
does not close those gates. Initial transient single-read readiness failure is documented above;
subsequent bounded gate, actual split/unavailable-peer checks and restored-pair readiness passed.

## PHASE 10 Prerequisites

Review the local staging evidence; explicitly approve safe live staging credentials/config and
public route where required; approve off-host backup/restore plan and longer soak; separately approve
production data rehearsal/migration/cutover. Synthetic success never authorizes production promotion.

## Decision Required

External integration needs staging Discord token/Gemini credential locations, approved guild/channel
IDs and origin; secret values must not be sent in chat. Public hostname/DNS and remote backup
destination require separate approval. Network auto-update needs an approved published source ref and
update policy; the public repository was readable but `codex/rebuild-v2` was absent on the remote.

## Commits / rollback

PHASE 8 history unchanged. Completed focused commits: `24e4240` host preparation, `4332919` immutable
group permissions and tests, `3e9297a` confined filesystem probe, `bb0fca6` credential ACL validation
and tests, `92a4b10` isolated installation, `0376f14` bytecode-free staging imports and regression.
Additional verified tool commits: `18e1454`, `d75292b`, `9eef070`, `c6adea2`, `807fd51`, `b3c75a2`,
`9af25c6`, `7e0258b`, `425af55`, `7e6fdc3`, `1fb3daa`, `cc7db26`. Their messages identify each file's
responsibility; `453c896` and `183553f` add verified namespace/polkit and manual inbox drills.
`fd83f2d` records the actual split-pair/missing-peer rejection and recovery drill.
No remote push or history rewrite occurred. Rollback must stop only staging-created units, preserve synthetic recovery
evidence and review owned paths before removal; never remove existing cloudflared or V1 assets, modify
sudo/SSH policy, down-migrate live data or rewrite Git history. PHASE 10 will not start automatically.
