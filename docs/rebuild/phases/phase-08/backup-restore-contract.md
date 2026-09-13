# PHASE 8 Backup / Restore Contract

## Backup

Operations reuse PHASE 3 `DataRecovery` consistent SQLite snapshot, integrity/schema/semantic checks
and complete-file encryption/round-trip validation. No live SQLite `cp` replaces these primitives.
Only synthetic temporary databases and generated test keys were used in this Phase. The actual
`docs/rebuild/bot_database.db` was not opened, read, hashed, copied or modified.

Each successful operation publishes a unique encrypted archive and metadata with checksum, key ID,
schema 5 and creation time. Durable audit precedes replacement of `latest.json`. Partial/encryption/
remote/audit failure preserves the previous latest pointer. An operation may have produced a valid
or partial orphan even when it reports failure: inspect evidence instead of assuming no artifact.
Keep eight verified alternatives; a hard 65-directory-entry admission cap prevents unbounded failed
artifact growth and requires operator inspection/archival when reached.

`RemoteBackup` accepts only the encrypted artifact, checksum and identity. There is no active remote
implementation/destination and no private-branch force push. Non-null remote config fails closed
rather than silently ignoring publication. Off-host disaster recovery remains unavailable until an
approved destination/auth adapter and restore drill exist; local success does not prove remote durability.

All operations share the deployment lock. Scheduled backup is every four hours UTC, persistent on
missed boot, with a 180-second unit budget. This leaves normal margin inside the accepted six-hour
initial RPO, but an outage/lock conflict can violate it. Missing or older-than-six-hour evidence is
exposed in local metrics. The timer is defined, not installed or enabled.

## Isolated rehearsal

1. Select explicit archive IDs or inspect up to eight newest metadata records independently of latest.
2. Check metadata/key identity/schema and ciphertext checksum.
3. Decrypt and restore using PHASE 3 validation into a new private temporary path.
4. Independently open/validate application compatibility at ledger 5 and close it.
5. Publish to a previously absent operator candidate path, with no live overwrite.
6. Audit success and remove private intermediate plaintext files/sidecars on completion or failure.

Corrupt newest, bad metadata, tampered ciphertext, wrong key and semantic/schema-invalid candidates
cannot replace canonical data. Invalid candidates may fall back to a known-good alternative; disk,
permission and cancellation faults propagate rather than being mistaken for candidate corruption.
Restoration uses a separate offline DB instance, never maintenance on a running canonical instance.

## Explicit promotion

`promote --destination <isolated-candidate> --expected-sha256 <reviewed-digest> --approve-promotion`
requires reviewed recovery evidence, maintenance window and stopped consumers. CLI confirms both
runtime services are inactive/failed, validates candidate schema/application compatibility and acquires
the operation lock. Promotion rejects same-path source/target, changed candidate and canonical WAL/SHM,
copies to a private file, flushes/fsyncs, checks the digest, assigns the dedicated group mode 0660 and
atomically replaces canonical followed by parent fsync. It never removes a live WAL to bypass checks.

The operator must prevent unrelated service starts throughout the maintenance window. CLI does not
automatically create a fresh backup of a corrupt canonical DB; retain existing verified encrypted
recovery points and preserve original DB/sidecars before approved replacement. Post-replace fsync or
audit failure is an uncertain outcome: remain stopped and revalidate the exact target before action.
No automatic reverse migration, empty production initialization or old-schema code rollback exists.

Keys remain outside releases, private and service-scoped. Key ID is metadata, not key material.
Retain separately protected old keys for backups that use them; lost encryption keys cannot be
reconstructed by these tools. Actual key rotation/destination changes require operator decisions.

## Evidence and limits

`tests/integration/operations/test_recovery.py` covers newest/corrupt fallback, wrong key/tamper/schema,
semantic corruption, failed remote publication, retention, audit failure, cancelled restore, explicit
promotion guards, atomic replacement failure, disk-full and permission errors. Pipeline tests combine
real synthetic SQLite/encrypted backups with fake commands/services. PHASE 3 tests continue to verify
snapshot semantics, corruption and legacy reader/codec compatibility.

No production data, remote upload or host restore was performed. Actual filesystem durability, RTO,
six-hour RPO under load and real old-key restore rehearsal remain staging/production approval gates.
See [backup verification](../../../../deploy/runbooks/backup-verification.md),
[rehearsal](../../../../deploy/runbooks/restore-rehearsal.md), and
[real restore](../../../../deploy/runbooks/real-restore.md).
