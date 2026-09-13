# V2 operations runbooks

These commands are **review artifacts for PHASE 9**, not instructions already executed.
Target: dedicated Raspberry Pi 5, Ubuntu Server 24.04 ARM64, Ethernet, Python 3.12.
Production data, production credentials, cutover and V1 removal retain separate approval gates.
No WordPress/CloudPanel or past host configuration is restored.

Common preconditions: verified current release; reviewed config; dedicated `discordbot` runtime user
and `discordbot-deploy` deployment user in group `discordbot`; operator authorization on the target
host. Never paste credentials, actual DB values or raw logs into chat. Unit files use systemd
`LoadCredential`; `.env` is not the V2 source of truth.

For operator commands below, define this shell function **only on the approved staging host**:

```sh
ops() {
  sudo systemd-run --wait --collect --unit=discordbot-operation \
    --property=User=discordbot-deploy --property=Group=discordbot \
    --property=LoadCredential=db_key:/etc/discordbot/secrets/db_key \
    --property=RuntimeMaxSec=1800 --property=TimeoutStopSec=300 \
    /opt/discordbot/current/.venv/bin/python -I \
    /opt/discordbot/current/app/deploy/launch.py operations "$@" \
    --config /etc/discordbot/config.json \
    --credentials /run/credentials/discordbot-operation.service
}
```

Exit 0 means verified completion; 1 means failure or uncertain outcome; 75 means lock/conflict.
systemd-run may wrap the application's exit status: inspect its unit result. A request acceptance is
not deployment success. Do not blindly retry an uncertain promotion or activation. Inspect current,
both readiness responses, `activation.json`, `rollback.json`, and safe audit records first.

| Runbook | Purpose |
| --- | --- |
| [First staging install](first-staging-install.md) | Host, users, offline wheels, initial candidate |
| [Normal deploy](normal-deploy.md) | Immutable update and cleanup |
| [Failed deploy rollback](failed-deploy-rollback.md) | Single compatibility-gated recovery |
| [Backup verification](backup-verification.md) | Snapshot evidence and six-hour RPO |
| [Restore rehearsal](restore-rehearsal.md) | Isolated validation and fallback |
| [Real restore](real-restore.md) | Explicit stopped-service promotion |
| [Health troubleshooting](health-troubleshooting.md) | Local readiness, metrics and safe audit |
| [Watch isolation](watch-failure-isolation.md) | Independent service/route diagnosis |
| [Music provider](music-provider-failure.md) | Actor/cache/provider recovery |
| [Corrupt DB](corrupt-database.md) | Missing/zero-byte/corrupt fail-closed behavior |
| [Lost secrets](lost-secrets.md) | Key IDs, old-key retention and recovery |
| [Emergency provider update](emergency-provider-update.md) | Isolated yt-dlp pin and rollback |
| [Cutover preparation](production-cutover-preparation.md) | PHASE 10 approval gate |

Units are concrete deterministic assets for the accepted layout. Path changes require editing config
and units together, rerunning asset tests and `systemd-analyze verify` on staging. No install script
silently creates users, rewrites system paths, enables units, or changes Cloudflare routes.

Reference checks: [systemd 255 execution configuration](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.exec.xml),
[systemd 255 timers](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.timer.xml),
[pip hash-checked installs](https://pip.pypa.io/en/stable/topics/secure-installs/).

Timers specify cadence, not a guaranteed RPO during outage. Alert locally on backup age >6h or missing
evidence; restore rehearsal and measured Pi durations establish the actual recovery capability.
