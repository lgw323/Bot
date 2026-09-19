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
exists. PHASE 10 selected private Bot-Data with a separate write deploy key. The opt-in object is
`{"kind":"git-ssh","repository":"git@github.com:lgw323/Bot-Data.git","ref":"refs/heads/db-backup"}`;
no other destination/ref is accepted. Operations additionally needs scoped `backup_ssh_key` and
`known_hosts` mounts. Runtime Discord/Watch scopes do not receive them. Actual production activation
still requires the final gate; see [PHASE 10 cutover](../../docs/rebuild/phases/phase-10/cutover-runbook.md).

The Git adapter uploads only the whole-file encrypted envelope and allowlisted metadata, using a
normal fast-forward commit. Independent remote fetch/read-back must succeed before `latest.json`
advances. Failed or uncertain publication retains the previous latest and local artifacts, returns
failure and requires operator reconciliation; there is no retry loop. A single transport has a 90s
deadline and its executor drains before the operation lock is released.

Remote active tree retention selects the latest eight plus the newest per each of seven UTC dates
(at most fourteen distinct points). Legacy files and Git ancestors remain intact. This does not
erase historical ciphertext or cap repository storage; inspect growth separately. Remote deletion
logic is verified on disposable synthetic repositories, not by pruning existing V1 history.

Postcondition: latest checksum validates, independent isolated restore passes, age is within RPO and
safe backup/rehearsal audits exist. A checksum alone is not a recovery proof.
