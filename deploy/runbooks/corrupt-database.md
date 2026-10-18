# Missing, zero-byte or corrupt DB

Precondition: fail-closed startup or semantic/schema validation error. Preserve the canonical file
and any WAL/SHM together; stop consumers and prevent scheduled updates. Never initialize over them.

```sh
sudo systemctl stop discord-bot watch-web
sudo systemctl stop discordbot-update.timer discordbot-backup.timer discordbot-manual.timer
ops rehearse --destination /var/lib/discordbot/state/recovery-unique.db
```

Rehearsal does not open the canonical DB as a writable runtime and can recover even when canonical
data is missing/corrupt. Invalid latest falls back to validated older candidates. If none is usable,
obtain an explicitly approved encrypted alternative through the remote adapter/operator procedure.
There is no public-code-remote fallback and no automatic empty DB.

Postcondition: isolated candidate approved for the real-restore runbook, or stopped failure with
preserved source evidence. A new empty staging database is only an explicit synthetic bootstrap
operation; losing production data is not implicit authorization to bootstrap.
