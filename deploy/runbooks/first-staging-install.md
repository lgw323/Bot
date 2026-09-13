# First staging install

Precondition: PHASE 9 authorization, dedicated staging Discord application/guild, reviewed clean-host
inventory and operator-supplied secrets. Production data is forbidden here. The operator supplies the
approved source URL and exact commit without embedding credentials. Cloudflare connector/hostname
validation is a separate staging check; these commands never edit its configuration.

1. Confirm OS/architecture/Python/media binaries and free disk; record results without host secrets.

```sh
uname -m
python3.12 --version
ffmpeg -version
df -h /opt /var/lib
```

2. After reviewing account collisions and ownership, provision the dedicated paths. These are future
host changes; never run them on the development PC or an unapproved production host.

```sh
sudo useradd --system --user-group --home-dir /var/lib/discordbot --shell /usr/sbin/nologin discordbot
sudo useradd --system --gid discordbot --home-dir /var/lib/discordbot/source --shell /usr/sbin/nologin discordbot-deploy
sudo install -d -o discordbot-deploy -g discordbot -m 2750 /opt/discordbot /opt/discordbot/releases /opt/discordbot/candidates
sudo install -d -o discordbot-deploy -g discordbot -m 2770 /var/lib/discordbot
sudo install -d -o discordbot -g discordbot -m 2770 /var/lib/discordbot/data /var/lib/discordbot/state /var/lib/discordbot/cache
sudo install -d -o discordbot-deploy -g discordbot -m 2750 /var/lib/discordbot/backups
sudo install -d -o discordbot-deploy -g discordbot -m 2770 /var/lib/discordbot/audit
sudo install -d -o discordbot-deploy -g discordbot -m 2750 /var/lib/discordbot/wheels
sudo install -d -o root -g discordbot -m 0750 /etc/discordbot
sudo install -d -o root -g root -m 0700 /etc/discordbot/secrets
sudo install -o discordbot-deploy -g discordbot -m 0660 /dev/null /var/lib/discordbot/operations.lock
```

Do not rerun `install /dev/null` against an existing lock: never replace its inode. Use the existing
file after verifying ownership. Shared canonical DB/WAL access requires dedicated group `discordbot`
and mode 0660; imported synthetic DB must be explicitly installed with that ownership/mode. Persistent
directories use setgid. Music state/cache remain runtime-owned; deploy tools do not parse Music data.

3. Review/install `config.example.json`, `update.example.json`, root-owned private secret files and
the narrow polkit rule. Replace synthetic IDs and `.invalid` origin with staging values privately.
Secret files must be regular files owned by root, mode 0600. `db_key` is a Fernet key; the two Watch
keys are independent random strings ≥32 characters. Config is root:discordbot 0640. Do not put keys
in command arguments, environment files or Git. Auth for the source mirror is an explicit operator
step; no current PC credentials are copied. Clone only after the Phase 9 authorization:

```sh
sudo -u discordbot-deploy git clone --no-checkout "$APPROVED_SOURCE_URL" /var/lib/discordbot/source
```

4. Prepare a reviewed exported source tree under `$STAGING_SOURCE`. Fetch/download/build ARM64 wheels
only when Phase 9 package/network actions are authorized. The current pins record local Phase 7
versions and the existing bgutil pin; ARM64 availability is not claimed. Example preparation:

```sh
python3.12 -m pip download --only-binary=:all: --no-deps -r "$STAGING_SOURCE/deploy/dependencies.pins" -d "$WHEELHOUSE"
python3.12 "$STAGING_SOURCE/deploy/wheels.py" "$WHEELHOUSE" "$STAGING_SOURCE/deploy/dependencies.pins"
python3.12 -m venv --copies /var/lib/discordbot/bootstrap
/var/lib/discordbot/bootstrap/bin/python -m pip install --no-index --no-deps --only-binary=:all: --require-hashes --find-links "$WHEELHOUSE" -r "$WHEELHOUSE/requirements.lock"
/var/lib/discordbot/bootstrap/bin/python -m pip check
```

Review/archive the wheel lock and artifact hashes before install. If a pin/wheel/transitive dependency
is unavailable, stop and produce a reviewed lock revision; do not silently resolve or upgrade. Stage
the reviewed wheels/lock at `/var/lib/discordbot/wheels`. Neither lock generation nor tests prove wheel
provenance or native ABI compatibility. These remain host checks.

5. Create a new synthetic staging DB using PHASE 3's explicit `DataRecovery.bootstrap`, or restore an
approved synthetic backup to a new path. This example refuses an existing target; it is exclusively
for the clean staging host and uses the reviewed source/bootstrap environment:

```sh
sudo -u discordbot-deploy env PYTHONPATH="$STAGING_SOURCE/src" PYTHON_DOTENV_DISABLED=1 \
  /var/lib/discordbot/bootstrap/bin/python - <<'PY'
import asyncio
import os
from pathlib import Path
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseRequest

async def bootstrap():
    path = Path('/var/lib/discordbot/data/bot_database.db')
    database = SqliteDatabase(DatabaseConfig(path))
    try:
        report = await DataRecovery(database).bootstrap(DatabaseRequest.within(30))
        if report.migration_version != 5:
            raise RuntimeError('unexpected staging schema')
        os.chmod(path, 0o660)
    finally:
        await database.stop()

asyncio.run(bootstrap())
PY
```

No automatic empty production DB exists. Review the configured DB path against this example before
running it. Copy and validate
the unit assets and polkit rule with operator approval; do not enable timers yet:

```sh
sudo install -m 0644 "$STAGING_SOURCE"/deploy/systemd/* /etc/systemd/system/
sudo install -m 0644 "$STAGING_SOURCE/deploy/polkit/50-discordbot.rules" /etc/polkit-1/rules.d/
sudo systemd-analyze verify /etc/systemd/system/discord-bot.service /etc/systemd/system/watch-web.service
sudo systemctl daemon-reload
```

6. First activation uses the bootstrap interpreter with only the DB credential:

```sh
sudo systemd-run --wait --collect --unit=discordbot-bootstrap \
  --property=User=discordbot-deploy --property=Group=discordbot \
  --property=LoadCredential=db_key:/etc/discordbot/secrets/db_key \
  --property=RuntimeMaxSec=1800 --property=TimeoutStopSec=300 \
  --setenv="PYTHONPATH=$STAGING_SOURCE/src" --setenv=PYTHON_DOTENV_DISABLED=1 \
  /var/lib/discordbot/bootstrap/bin/python -m discordbot.operations.adapters.cli deploy \
  --revision "$APPROVED_COMMIT" --config /etc/discordbot/config.json \
  --credentials /run/credentials/discordbot-bootstrap.service \
  --policy /etc/discordbot/update.json --wheels /var/lib/discordbot/wheels
```

This source invocation is only for first installation; later operations use the pinned release
launcher. A missing DB, missing
wheel, failed test, permission problem or missing credential prevents successful activation.

Postcondition: both local readiness payloads match one release, synthetic backup restores, only the
staging Gateway connects. Measure cold start, shutdown, disk/RSS/CPU/temperature, lib64 materialization,
Uvicorn lifecycle, polkit and real atomic symlink/fsync behavior. Enable reviewed timers only after
their staging rehearsal. No production cutover is implied.
