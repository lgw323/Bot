# PHASE 8 Report

## Phase 8 Complete

2026-09-13: Operations / Deployment implementation completed in the repository. This is synthetic
implementation evidence, not a Pi installation or production cutover. PHASE 9 has not started.

Baseline was clean `codex/rebuild-v2` at `e0449c2`, with PHASE 7 focused commits present, full strict
**592 passed, 0 xfailed**, ledger 5 and V1 runtime retained. The rebuild index still described PHASE 6
despite PHASE 7 deliverables/current plan; its living status was corrected without editing historical
Phase reports or frozen baseline. Current decisions, accepted ADRs and PHASE 3/6/7 contracts governed
implementation; V1 hard-reset/live-venv scripts were not treated as compatibility requirements.

## Implemented

- Immutable release builder/manifest, exact offline wheel pins/hashes, per-release venv and atomic current.
- Exclusive operations lock, deploy/preflight/test/data/backup/publish/activation/readiness/smoke/audit
  pipeline, one bounded compatibility-gated rollback, protected release cleanup and startup evidence.
- Two executable composition roots, scoped typed credentials, local health/metrics, signals and
  systemd runtime/backup/update/manual service/timer assets plus a narrow deploy-user polkit rule.
- Verified encrypted backup archives, isolated restore/fallback/rehearsal, explicit stopped-service
  promotion and remote publication port, reusing PHASE 3 primitives.
- Master-only manual operation boundary, single durable inbox consumption, daily update policy,
  provider-only pin guard, operational telemetry/audit and 13 reviewable runbooks.

## Tests

All operations tests used temporary paths, synthetic databases/test keys, fake commands/services or
in-process ASGI transports. No actual systemctl/sudo/Git fetch/package installation/API/production data
was exercised. `PYTHON_DOTENV_DISABLED=1` was set; legacy test configuration redirects DB work to temp.

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
.venv\Scripts\python.exe -m pytest tests/ -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

Final full strict result: **673 passed, 0 xfailed**, 30.99s. The only warning is the existing
discord.py `audioop` DeprecationWarning; there were no RuntimeWarning or unraisable-exception failures.

| Observed verification | Result |
| --- | --- |
| PHASE 7 baseline full strict | 592 passed, 0 xfailed, 21.83s |
| Final full strict | 673 passed, 0 xfailed, 30.99s |
| Final operations + architecture strict | 95 passed, 9.46s (81 operations + 14 architecture) |
| Earlier PHASE 8 full strict before final signal/lock/collision tests | 669 passed, 0 xfailed, 32.60s |
| Runtime/assets/pipeline/filesystem focused gate | 39 passed, 2.81s |
| Builder identity/pin gate | 9 passed, 0.86s |
| Final documentation checks | 2 architecture documentation tests passed; all 14 runbook/index relative links resolved; bootstrap Python example parsed without execution |
| Critical fault repetition after lock fix | 14 cases × 20 consecutive runs = 280 passes; each run 0.79–0.91s |

Repetition covers six rollback stages, switch cancellation, shared lock/error release, stale PID,
manual/timer race, cancelled restore, disk/permission promotion failures and first-open write ordering.
An initial repetition failed on its second run: simultaneous first-open lock initialization could write
against the winner's Windows mandatory byte lock. Initialization now writes only after kernel ownership;
the regression test verifies write ordering against the real platform lock. Windows supports locking
beyond EOF, so an unlocked initialization byte is unnecessary.
[Microsoft CRT documentation](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170).

Earlier implementation checks exposed Windows symlink privilege limitations, a restore maintenance call
on an already-running DB instance, and pytest import-name collisions. These were resolved with an
explicit test-only link model, a separate offline restore DB and an operations test package. No failing
scenario was hidden with xfail. Interrupted sessions whose results were lost are not counted as passes.

## Architecture Check

Existing architecture tests cover inward imports, vendor/OS adapter placement, fresh-process import
side effects, supervised task ownership, centralized executor dispatch and documentation links.
Production composition accesses feature/storage adapters; operations application uses ports. No feature
domain, prior migration/schema definition or V1 runtime file was changed. No raw task/ad-hoc executor
was introduced. Per-process config remains immutable and bounded; ledger stays 5.

## Release Layout / Manifest

`/opt/discordbot/releases/<id>/{app,.venv,dependencies.lock,manifest.json}` and atomic `current` are
separate from persistent `/var/lib/discordbot` and `/etc/discordbot` credentials. Manifest captures full
commit, Python version, dependency identity, compatibility, time/version/entrypoints/config and complete
file inventory. Full identities reject prefix collisions; changed pin versions reject lock drift.
See [deployment contract](deployment-contract.md) for publication, bounds and venv alias handling.

## systemd Services / Timers

Discord and Watch have independent restart/liveness and bounded shutdown, fixed users/working paths,
scoped credentials, read-only system/release sandbox, journald and restart-storm limits. Backup runs
every four hours; update defaults to daily 03:00 KST plus up to 30 minutes jitter; local manual inbox
polling is every 60 seconds. Units and polkit were tested as repository assets, never installed/enabled.
Actual `systemd-analyze verify`, credential mounts and Linux unit behavior remain PHASE 9 work.

## Configuration / Secrets

One startup validation checks config version, absolute distinct paths, channel/master IDs, HTTPS Watch
origin, loopback ports, runtime bounds and private service-scoped credentials. Missing token fails before
assembly/login. `.env` is not a V2 source of truth. No actual secret was requested/read/logged. Synthetic
example IDs/origin require staging replacement. POSIX mode/owner policy is tested; host ACL/group/WAL
behavior remains unverified. See [operations contract](operations-contract.md).

## Deployment / Activation

Lock → source/venv → checksums/preflight/offline approved test subset → compatibility → verified online
backup → immutable publish → clean stop/checkpoint → quiescent backup/activation intent → atomic switch
→ start → pair readiness/smoke → durable success → retention. Pre-activation failures preserve current.
The two synthetic end-to-end LocalDeployment tests exercise successful activation and readiness recovery
with real backup/release/audit adapters and fake command/service boundaries.

## Readiness / Smoke

Both services must identify themselves on one expected release. Discord requires DB/schema, Gateway and
Music restoration/core readiness; Watch requires DB/stale cleanup and public/control listeners. Local
health and metrics run through in-process/fake adapters in tests. The signal test verifies checkpoint
before Gateway close and cleanup/handler restoration. Actual Discord/Gateway/Voice/Watch/Tunnel and
pinned Uvicorn socket lifecycle smoke are PHASE 9 prerequisites, not claimed here.

## Rollback

At most one attempt validates previous manifest and current data, switches code+venv together and
rechecks readiness/smoke. Failure stops the pair or explicitly reports unconfirmed stop. Initial
activation cannot invent a prior release. No automatic down-migration occurs. An older V2 validator
that does not know ledger 5 requires verified pre-migration data and operator recovery tooling.

## Backup

PHASE 3 snapshot/semantic/encryption validation feeds atomic archives, SHA256 metadata, latest, eight
alternatives, bounded admission and durable audit. Failed remote/audit publication preserves previous
latest. The remote adapter is a port only; no off-host durability or upload is claimed. Four-hour timer
is inside the accepted initial six-hour RPO in normal operation; metrics expose missing/stale evidence.
See [backup/restore contract](backup-restore-contract.md).

## Restore / Rehearsal

Newest-valid and corrupt-latest fallback, wrong key, tamper, schema/semantic failure, cancellation,
disk-full/permission and atomic promotion guards are synthetic-tested. Rehearsal publishes only to a
new isolated path. Promotion requires explicit approval flag, exact reviewed digest, stopped services,
no live WAL/SHM, application compatibility and audit. Post-replace fsync/audit failure is uncertain;
operator reconciliation is required. Canonical data is never automatically replaced by a candidate.

## Automatic / Manual Update

Explicit branch/revision policy uses a source mirror and the same immutable transaction. Exact pinned
offline dependencies remain normal policy; emergency provider-only mode permits only yt-dlp pin drift
and records audit. Master authorization, one ephemeral response, overlap rejection and bounded receipt
history are tested. Accepted inbox work is not reported as completed deployment. Interrupted
`in_progress` work requires operator review, never replay. No production admin button was wired.

## Audit / Observability

Atomic bounded audit stores safe operation/release/time/result/reason/correlation fields. Admission and
success-audit failure cannot claim completion. Platform telemetry drains to JSON journald; local capped
metrics include release/readiness, DB latency/admission/failure, backup age/RPO, task/capacity/drops,
Watch sessions/clients, Summary waiting and Music actor/cache/process observations. No hosted monitoring
or user-content/capability labels were added. Audit archival is explicit at the 10,000-record hard cap.

## Runbooks

[Runbook index](../../../../deploy/runbooks/README.md) links first staging install, normal deploy,
failed deploy rollback, backup verification, restore rehearsal, real restore, health troubleshooting,
Watch isolation, Music/provider failure, corrupt/zero-byte DB, lost secrets, emergency provider update
and production cutover preparation. Each states preconditions, commands and postconditions. Commands
are future reviewed host actions; none was executed against a Pi in PHASE 8.

## Failure / Recovery Check

| Fault | Evidence / outcome |
| --- | --- |
| Build/preflight/test/backup fail | Fake stage injection preserves old pair/current |
| Switch/readiness/smoke/one service/split version | Rollback validates and checks one coherent pair |
| Rollback itself fails | One attempt, stop and visible failure |
| Cancel during switch/restore | Recovery or isolated cleanup; no silent successful mutation |
| Crash/reboot before activation | Incomplete release rejected; stale metadata cannot steal kernel lock |
| Corrupt latest or semantic data | Invalid candidate rejected; valid previous selected |
| Wrong key/ciphertext/schema | No canonical overwrite |
| Disk full/permission/atomic replacement error | Old target remains where replacement has not occurred |
| Missing/wrong secret or unknown/missing DB | Startup fails closed; no automatic bootstrap/login |
| Audit failure | No success claim; previous latest preserved; recovery/uncertainty visible |
| Retention/path escape | Current/rollback/window protected; traversal/link rejection |

## Pi Impact

None. No SSH, Git clone/auth, host packages, `/opt`/`etc`/`var` installation, service/timer activation,
Cloudflare change, external API/login, production backup upload/restore, migration, cutover or V1 removal.
Actual `docs/rebuild/bot_database.db` was not opened/read/hashed/copied/modified in PHASE 8.
No push, PR or deploy occurred.

## Compatibility

Engagement/Summary/Watch/Music and their executable contracts remain; strict xfails stay zero. Ledger 5,
legacy tables, SQL backup codec, Music snapshot and V1 production runtime are unchanged by this Phase.
V1 hard-reset update details are superseded only in the new, unactivated V2 tooling. Live Discord
admin-panel migration, actual Linux atomicity and production data compatibility drill are not inferred
from these synthetic results.

## Documentation Updated

Four PHASE 8 deliverables, `deploy/runbooks/`, living plan/ADR-023/trace/open questions, rebuild index,
root README and CHANGELOG. Architecture documentation inventory now includes PHASE 8. Historical
baseline and PHASE 0–7 artifacts remain unchanged.

## Remaining Risks

- ARM64 pinned wheel availability/provenance/transitive completeness and native ABI require staging.
- Windows symlink modeling does not prove Linux fsync/power-loss behavior; actual permissions,
  systemd/polkit and lib64 materialization need the clean target host.
- Gateway/Voice/provider/tunnel behavior, actual Uvicorn serving, cold-start/stop duration, disk/RSS/CPU/
  temperature, long soak and RPO/RTO remain unmeasured. Hard limits are initial values.
- Host kill during mutation, filesystem stalls and failed post-mutation audit can leave uncertainty;
  inspect durable intent/current/DB while stopped rather than blindly retrying.
- No configured remote backup adapter means local evidence alone cannot recover a lost host.
- Manual receipt history and audit/release/archive capacity are bounded; operators must reconcile
  interrupted requests and archive evidence before caps. Production key/cadence decisions remain gated.

## Phase 9 Staging Prerequisites

New user instruction; clean Raspberry Pi 5 / Ubuntu Server 24.04 LTS ARM64 / Ethernet inventory;
reviewed staging application/guild/secrets and source auth; authorized pinned wheel preparation;
synthetic bootstrap; reviewed account/group/path layout and units. Then execute runbooks with staged
credential/polkit/real-link/failure/restore tests, live staging smoke, resource/soak/RPO/RTO evidence.
Production data rehearsal requires its own approved gate; no WordPress/CloudPanel restoration.

## Next Phase Gate

PHASE 8 stops here. PHASE 9 is not started automatically. Production migration/cutover and V1 removal
retain PHASE 10/separate explicit authorization.

## Decision Required

None blocks repository implementation. Real host/auth access, production backup destination or new
external service, key-management product changes, cadence with production cost/product impact,
Cloudflare hostname changes, destructive migration/cutover and V1 removal require later decisions.

## Commit / rollback

| Focused commit | Responsibility |
| --- | --- |
| `4a0ddb2` | Immutable release transaction, filesystem/source/build/retention and tests |
| `5b32140` | Verified encrypted backup archives and isolated restore/promotion tests |
| `1f65322` | Executable runtime, credential/health/manual adapters, systemd assets and lock race regression |
| `88e32fe` | Exact dependency pin and full release identity collision validation |
| `docs: document Phase 8 operations contracts and staging runbooks` | This report, contracts, runbooks and living documentation inventory |

Staged diff/whitespace and file scope are reviewed before each commit. Repository rollback is focused
`git revert` in reverse dependency order; no production state exists to undo in this Phase. Future
operational rollback uses retained verified release/data evidence and the deployment/restore contracts,
never `reset --hard`, history rewriting or automatic live data down-migration.
