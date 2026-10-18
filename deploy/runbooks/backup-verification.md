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
RPO: `backup_rpo_exceeded` becomes 1 when latest is missing, its observation is unavailable, or it is
older than six hours. `backup_age_seconds=-1` means unknown, including after the terminal DB probe
latch or sampler termination; it must not be read as proof of a known backup age. While sampling is
active, age advances from the last observed local `latest.json` mtime; replacement/removal appears
at the next sample. Publishing a backup does not clear the DB latch or unknown state. Investigate local
audit and bounded journal diagnostics; no hosted monitoring was added.

Backups are Phase 3 consistent snapshots, validated by decrypt/restore/reconciliation before publish.
Archive `.enc` plus checksum/key-ID metadata is immutable; `latest.json` advances after success audit
and optional remote publication. Eight validated alternatives are retained. At 65 directory artifacts,
backup fails closed for inspection rather than growing without bound after repeated partial failures.
Never remove latest or its valid predecessor to clear this condition.

Local retention uses the same isolated decrypt/restore and application-compatibility checks as
rehearsal before counting an archive toward eight. It plans deletion before success audit/latest
publication, protects the previous latest and new snapshot, and retains rejected artifacts for
operator inspection. Valid local orphans can count; failed publication alone is not proof of
corruption. Disk/permission/cancellation faults during validation abort before pruning. Revalidation
adds local I/O; the existing 180-second service budget is unchanged, and production-scale timing
is not established by synthetic tests. No cleanup of existing archives is authorized by this note.

Remote publication is an injected encrypted-object/digest port. `backup_remote:null` explicitly means
local-only; off-host RPO/host-loss durability is not claimed. No code-remote fallback or force push
exists. PHASE 10 selected private Bot-Data with a separate write deploy key. The opt-in object is
`{"kind":"git-ssh","repository":"git@github.com:lgw323/Bot-Data.git","ref":"refs/heads/db-backup"}`;
this unchanged object is accepted in `environment:production`. Staging must use the explicitly
isolated policy below; it cannot select Bot-Data. Operations additionally needs scoped `backup_ssh_key` and
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

## A9-BT1 isolated destination configuration (local implementation, review pending)

The source-controlled `ISOLATED_REPOSITORIES` allowlist in
`src/discordbot/operations/adapters/backup_destination.py` is deliberately empty. An operator must
name and approve an exact private repository before a separately reviewed source change adds it.
Configuration alone cannot approve a recipient. The supplied Bot-Data URL names production and
does not satisfy isolation. No repository, credential or remote operation is created by this change.

Configuration shape below is illustrative and intentionally rejected until its placeholder is
replaced with an owner-approved, source-allowlisted repository:

```json
{
  "environment": "staging",
  "backup_remote": {
    "kind": "git-ssh",
    "target": "isolated",
    "repository": "git@github.com:lgw323/<approved-private-repository>.git",
    "ref": "refs/heads/db-backup"
  }
}
```

This is a fragment, not a complete runnable config. Only canonical scp-style Git SSH on github.com,
user git, owner lgw323 and the fixed db-backup ref are supported. Production/code repositories,
other owners/hosts/protocols, unknown fields, duplicate JSON keys, absent fields and conflicting
environment/target selections fail before credential reads or transport admission. Errors do not
echo values. Existing production config needs no migration; explicit null remains local-only.
Previously accepted staging-to-production remote config is now intentionally rejected.

The immutable validated destination passes through BackupRemoteSettings, GitRemoteBackup and
GitBackupStore. Upload base fetch, fast-forward push, independent readback, remote tree retention
and explicit download all use it. Direct store construction without a destination retains its
production helper compatibility default; isolated callers must pass the validated destination.
There is no fallback after validation, fetch, push or readback errors. Production-specific scripts
under deploy/production remain production-only and must not be used for isolated recovery.

Recovery selection remains local to the configured backup root. Download with the same validated
destination into a fresh directory, then bind a separately reviewed recovery config to those
downloaded artifacts; no automatic repository search or production fallback exists. Private
visibility, dedicated repository-scoped deploy key, pinned host and actual remote behavior require
later evidence/approval. SSH ACL/ownership, no agent/global-config fallback, encryption, retention,
restore no-overwrite and 90s total/30s command transport bounds are unchanged.
