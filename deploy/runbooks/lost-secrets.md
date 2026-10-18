# Lost or invalid secrets

Precondition: credential validation failed before login/listener admission. Operator checks file
existence, owner, permissions and key-ID inventory without printing values.

```sh
sudo stat -c '%a %U %n' /etc/discordbot/secrets/*
sudo systemctl show discord-bot watch-web -p Result
```

Restore the approved OS-managed secret files, owned by root with mode 0600. Runtime credential copies
must be private regular files owned by root/service UID. Keep tokens and keys out of shell history,
environment files, manifests, source, logs and reports. Do not generate a replacement encryption key
and expect it to decrypt existing backups. Loss of the only DB key means those encrypted backups
cannot be recovered; escalate that fact instead of manufacturing a successful restore.

Key rotation is a separate production decision: assign a new key ID, retain old keys in OS-managed
private storage for all retained backup generations, document operator ownership, rehearse each ID
with its matching key and explicitly list candidates for mixed generations. Backups require exact
key-ID selection; no automatic brute-force multi-key fallback. Retire an old key only after its last
required backup/rollback window and an approved recovery review.

Postcondition: correct services receive only their required credentials, startup passes, and a
synthetic encrypted backup/rehearsal passes. Watch key rotation invalidates old trust/capabilities and
must be planned; it is not a troubleshooting shortcut.
