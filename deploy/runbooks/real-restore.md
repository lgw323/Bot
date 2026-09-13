# Real restore

Precondition: explicit operator approval for this data replacement, retained encrypted recovery points,
known matching key, approved target release and maintenance window. Production replacement additionally
requires PHASE 10 approval. Disable scheduled/manual consumers for the maintenance window; record
their prior enabled state. First complete isolated rehearsal using the approved candidate.

```sh
sudo systemctl stop discordbot-update.timer discordbot-backup.timer discordbot-manual.timer
sudo systemctl stop discord-bot watch-web
sudo systemctl show discord-bot watch-web -p ActiveState -p Result
```

Both services must be stopped, no operator may restart them during promotion, and canonical WAL/SHM
must be absent. Preserve any remaining sidecar together with its DB; do not delete a WAL to bypass
the guard. Investigate shutdown/checkpoint failure. Record the isolated candidate SHA256 privately
using `sha256sum` (do not publish the DB or values). Review that exact candidate and live target.

```sh
ops promote --destination /var/lib/discordbot/state/rehearsal-unique.db --expected-sha256 "$APPROVED_CANDIDATE_SHA256" --approve-promotion
sudo systemctl start discord-bot watch-web
ops health
```

Promotion validates application/schema and exact candidate digest again, requires inactive/failed
systemd states, refuses live sidecars, fsyncs a private copy and atomically replaces the canonical
path. The shared service group gets mode 0660. A post-replace fsync/audit failure is **uncertain**:
inspect/revalidate current data while stopped; never assume no change occurred or blindly retry.

Postcondition: both services ready on the same compatible release, data reconciliation approved,
fresh verified backup and restore-promotion audit. Re-enable only previously approved timers. This
tool never automatically restores an older schema for code rollback or generates an empty DB.
