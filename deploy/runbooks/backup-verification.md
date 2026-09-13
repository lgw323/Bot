# Backup verification

Precondition: canonical DB validates, encryption key ID matches, private backup/audit directories have
space. Backup and deployment share the kernel lock; a conflicting timer run is visible as nonzero.

```sh
ops backup
ops rehearse --destination /var/lib/discordbot/state/rehearsal-unique.db
sudo systemctl list-timers discordbot-backup.timer
curl --fail --max-time 3 http://127.0.0.1:9010/metrics
```

Use a new rehearsal path each time. The timer proposes every four hours UTC, persistent catch-up,
one-second accuracy, leaving headroom under initial RPO six hours. Failures/outages can still exceed
RPO: `backup_rpo_exceeded` becomes 1 when latest is missing or older than six hours. Investigate local
audit and bounded journal diagnostics; no hosted monitoring was added.

Backups are Phase 3 consistent snapshots, validated by decrypt/restore/reconciliation before publish.
Archive `.enc` plus checksum/key-ID metadata is immutable; `latest.json` advances after success audit
and optional remote publication. Eight validated alternatives are retained. At 65 directory artifacts,
backup fails closed for inspection rather than growing without bound after repeated partial failures.
Never remove latest or its valid predecessor to clear this condition.

Remote publication is an injected encrypted-object/digest port. `backup_remote:null` explicitly means
local-only; off-host RPO/host-loss durability is not claimed. No code-remote fallback or force push
exists. A production remote destination/adapter needs its own approved decision before cutover.

Postcondition: latest checksum validates, independent isolated restore passes, age is within RPO and
safe backup/rehearsal audits exist. A checksum alone is not a recovery proof.
