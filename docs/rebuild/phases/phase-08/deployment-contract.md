# PHASE 8 Deployment Contract

Status: implemented in repository; synthetic verification only. PHASE 9 host installation requires
new user direction. The accepted immutable deployment model supersedes V1 live-venv/hard-reset scripts.

## Layout and identity

```text
/opt/discordbot/releases/<id>/app/{src,tests,deploy,...}
/opt/discordbot/releases/<id>/.venv/
/opt/discordbot/releases/<id>/dependencies.lock
/opt/discordbot/releases/<id>/manifest.json
/opt/discordbot/current -> releases/<id>
/var/lib/discordbot/{data,state,cache,backups,audit,source,wheels}/
/var/lib/discordbot/operations.lock
/etc/discordbot/{config.json,update.json,secrets/}
```

Release ID is `r-<commit first 16 hex>-<wheel-lock SHA256 first 16 hex>`. Reuse verifies the full
commit and dependency digest to reject truncated-ID collisions. Manifest records full commit, Python
3.12 patch, lock digest, schema min/max 5, UTC build time, application version, entrypoints, config
version and checksums of all code/venv files. It rejects missing, changed or additional files,
symlink/junction escape and `.building` candidates. The launcher validates its interpreter and source
belong to one resolved release; health never reads a later `current` pointer as its own identity.

Build creates a venv at its final absolute location, with `.building` admission protection. It never
renames an installed venv and invalidates its shebangs. POSIX publication removes write bits from
release contents. Runtime sandbox also makes releases read-only. The deploy owner retains controlled
cleanup capability; hashes detect accidental mutation, not compromise of that trusted owner.

## Dependencies and source

`deploy/dependencies.pins` records the existing environment's exact package versions plus the existing
bgutil requirement. No package was installed or upgraded in PHASE 8. `deploy/wheels.py` seals an
operator-reviewed local wheelhouse using METADATA name/version and artifact SHA256. Build requires an
exact pin/version set and offline `pip --no-index --no-deps --require-hashes --only-binary=:all:`, then
`pip check`. Wheel provenance and ARM64 availability remain staging checks. The Linux venv's known
internal `lib64 -> lib` alias is materialized; unexpected links are rejected.

Source export accepts an explicit 40-hex revision or an operator-configured `refs/heads/...` policy.
Automatic updates fetch only that ref into a dedicated source mirror. Bounded archive extraction
admits selected code/test/deploy metadata; live data, `.env` and docs DB are not source inputs.
Tests use fake commands: no fetch, venv install or package network operation was executed here.

## Transaction and failures

| Stage | Required result / failure behavior |
| --- | --- |
| Lock | Shared kernel lock for deploy, timer/manual, backup, restore and cleanup; conflict is bounded |
| Build | Complete candidate code/venv/checksums; failure discards unpublished candidate |
| Preflight/test | Paths/config, offline deployment test subset and inventory checks pass |
| Data/backup | Known schema 5 and PHASE 3 validated encrypted snapshot; current remains unchanged on failure |
| Publish | Complete manifest and immutable candidate; no partial release exposed |
| Stop | Stop both independent services, require clean systemd result, drain Music checkpoint |
| Activate | Second quiescent encrypted backup, durable activation intent, atomic symlink replacement and parent fsync |
| Start/ready/smoke | Both named services ready/live on exactly the expected release |
| Audit | Durable success evidence before retention; failed success audit initiates bounded recovery |
| Retain | Protect active/previous targets; cleanup failure remains visible without undoing a healthy pair |

Deployment tests run the approved `tests/integration/operations` subset with its own conftest boundary,
bytecode disabled and pytest cache disabled. The full repository suite is the development/commit gate.
Operations use argument vectors, no shell interpolation, bounded subprocess timeouts, discarded raw
child output, no inherited secret environment and a 30-minute systemd outer update budget.

An unchanged identity validates its manifest and audits unchanged without restart; this result is
not a fresh readiness check. Use the separate health gate when diagnosing a running release.

## Rollback and startup recovery

After stop/switch/start/readiness/smoke failure, make at most one rollback attempt. Stop the pair,
validate previous manifest and current data compatibility, restore the previous code+venv pointer,
start and recheck both readiness and smoke. If rollback fails, stop again and report failure; an
unconfirmed stop is explicitly distinct. Initial deployment has no invented previous release.
Cancellation after switch follows the same recovery path before propagation where the process can
still execute. SIGKILL/power loss cannot run compensation.

No automatic DB down-migration exists. Unknown schema fails closed. A validator from before ledger 5
requires an independently verified compatible pre-migration data candidate and explicit operator
procedure; retaining code for seven days alone does not make older validators compatible.

On reboot, only a validated complete `current` may start. Incomplete candidates remain non-current;
kernel ownership disappears on process exit even if stale PID metadata remains. Lock inode is never
deleted to steal ownership. Interrupted activation/manual evidence requires reconciliation of current,
both service identities and audit; no blind automatic replay. Missing/corrupt DB does not bootstrap.
Watch startup performs its Phase 6 stale cleanup; Music uses Phase 7 checkpoint restore after Gateway
readiness. Backup evidence remains outside releases.

## Retention and evidence

Cleanup protects current, rollback/activation intent targets, four newest published releases and all
published releases younger than seven days. Incomplete candidates have a one-day grace. Sixteen
release directories refuse further builds until safe cleanup, preserving the rollback window. File
counts/checksum size and source archive size are bounded. Reclaimed size includes the venv. Paths and
every nested link are validated before removal.

Windows tests model symlinks because this process lacks creation privilege, retaining real atomic
`os.replace`. Real Linux symlink/fsync/power-loss and ownership behavior is unverified until PHASE 9.
See [report](phase-8-report.md), [runbooks](../../../../deploy/runbooks/README.md), and
[backup contract](backup-restore-contract.md).
