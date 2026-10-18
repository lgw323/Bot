# Restore rehearsal

Precondition: approved synthetic artifacts in staging; available matching key ID; new isolated path
outside the canonical DB. Production artifacts are not permitted by Phase 8 authorization.

```sh
ops rehearse --destination /var/lib/discordbot/state/rehearsal-unique.db
ops rehearse --candidate "$NEWEST_BACKUP_ID" --candidate "$PREVIOUS_BACKUP_ID" --destination /var/lib/discordbot/state/fallback-unique.db
```

Default selection tries at most eight newest timestamped records and remains usable if `latest.json`
is corrupt. Each candidate checks identity, key ID, ciphertext digest, authentication/decrypt, SQLite
integrity, known schema/ledger and semantic data; the isolated result must start under the current
application. An invalid candidate never overwrites canonical data and an existing destination is
refused. Temporary plaintext/sidecars are removed; disk/permission/cancellation failures are audited.

Postcondition: `restore_rehearsal/ok`, new compatible isolated DB, original live DB untouched. Record
duration/bytes on staging for the approximate one-hour RTO target. Do not treat a file left after an
uncertain failure as approved: rerun validation with a new destination before promotion.
