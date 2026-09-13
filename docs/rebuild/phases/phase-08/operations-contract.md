# PHASE 8 Operations Contract

## Process ownership and configuration

Explicit `composition.main` selects the Discord or Watch composition root after validating immutable
typed settings, private credentials and executable manifest identity. Import performs no server/login/
DB work. Missing/wrong credentials fail before login. Runtime assembly uses feature/storage adapters;
operations application depends on ports, and OS interfaces stay in adapters.

`discord-bot.service` and `watch-web.service` are separate processes using one release launcher and
runtime user `discordbot`. They have no `Requires`/`PartOf` coupling. Watch listeners use loopback
ports 9000 (public application for the tunnel) and 9001 (signed control); health uses 9010/9011.
Runtime units use explicit persistent working directories, UMask 0077, read-only release/system paths,
bounded shutdown (90 seconds), on-failure restart delay 10 seconds and three starts per 300 seconds.
Deployment/manual/backup units run as `discordbot-deploy` in the dedicated shared group. A narrow
polkit rule permits that identity only to start/stop the two named runtime units.

Config version 1 validates distinct absolute persistent paths outside releases, positive bounded
guild/channel/master IDs, one to four channel scopes, HTTPS origin, distinct loopback ports and
platform capacity limits. Config/credential paths cannot be release-contained or symlinked. Config is
read once per invocation; `.env` and implicit legacy aliases are not production configuration.

| Process | systemd credentials |
| --- | --- |
| Discord | Discord token, Gemini key, Watch control HMAC key |
| Watch | Watch capability key and control HMAC key |
| Operations | DB encryption key only |

Files are bounded, regular, owner-checked and private on POSIX; secret fields/paths are excluded from
repr. Runtime/deploy DB sharing requires reviewed directory setgid and canonical DB mode 0660, while
Music state/cache remain runtime-owned. The operation lock inode is precreated once, mode 0660.
POSIX permission policy is unit-tested as pure validation; actual Linux credential mounts/group/WAL
permissions and polkit are PHASE 9 checks. No operating-system paths were installed here.

## Readiness, signals and observability

Local `/health/live`, `/health/ready` and `/metrics` adapters expose release/service identity and
bounded safe observations. Discord readiness requires platform startup, usable known-schema DB,
Gateway readiness and completed Music restore/command synchronization. Watch requires DB/stale
cleanup and both listeners. A supervised DB probe samples every five seconds and fails stale readiness
after 15 seconds. Deployment allows a bounded 60-second pair readiness wait and verifies both identities;
one ready process or split versions never counts as success.

Main owns the long-lived Gateway await. SIGTERM/SIGINT stops admission, drains Music checkpoint before
Gateway close, stops listeners/probe/telemetry and shuts down platform resources. Supervised tasks
have explicit deadlines/capacity; there are no raw application-created tasks or ad-hoc executors.
JSON telemetry flushes to journald using central redaction. Metrics preserve the platform cardinality
cap and report task/capacity/drop signals, DB latency/admission/failure, backup age/RPO, Watch capacity,
Summary waiting and Music actor/cache/process gauges. No user IDs, content or capability URLs are labels.

Runtime and operations errors expose safe fixed messages; raw command output is suppressed. Failed
shutdown propagates a failure result to systemd. A stopped process cannot emit its own liveness:
systemd status and local probe failures complement endpoint evidence. No hosted monitoring was added.

## Automatic and manual control

Daily update uses an explicit branch policy, the same deployment transaction and offline reviewed
wheels. Default 18:00 UTC (03:00 KST) plus up to 30 minutes jitter is a conservative staging proposal.
There is no five-minute network polling, live venv mutation or weekly reboot timer. Existing V1 scripts
remain untouched. An emergency provider-only path audits and permits only a yt-dlp pin change among
dependencies, retaining old code+venv; it does not auto-upgrade the full dependency set.

The manual application boundary authorizes only the configured master and returns exactly one
ephemeral response for denied/accepted/already-running/failed outcomes. It builds no shell strings.
The local inbox stores a hashed interaction receipt and up to 1,000 recent receipts under the same
kernel operation lock. A 60-second timer consumes pending requests once, marks `in_progress` before
execution, and delegates to deploy or checkpoint/backup/restart/readiness. Acceptance is not completion.
An interrupted `in_progress` request is uncertain and never automatically replayed. Operator review
must reconcile services/audit before clearing it. No live Discord administration button was wired.

## Audit, bounds and recovery

Durable per-event atomic JSON audit includes operation, release, UTC time, result, safe reason and
correlation. Deployment/rollback/backup/rehearsal/promotion/manual/restart/retention are covered. Future
cutover/migration must retain this boundary; no cutover command was implemented in this Phase.
The hard cap is 10,000 records and requires explicit safe archival rather than silently dropping
history. Admission/audit failure prevents claiming success. Post-mutation write/fsync failure remains
uncertain and requires reconciliation; cleanup cannot erase uncertainty.

The deployment kernel lock has a bounded 0–60 second acquisition timeout, is released on exceptions
or process exit, and never trusts PID metadata or deletes an inode to steal ownership. Initialization
writes occur only after acquiring kernel ownership, including Windows empty-file contention.
All durable jobs coordinate through this lock; timer overlap and manual races cannot switch twice.

See [deployment](deployment-contract.md), [backup/restore](backup-restore-contract.md),
[13 runbooks](../../../../deploy/runbooks/README.md) and [completion evidence](phase-8-report.md).
