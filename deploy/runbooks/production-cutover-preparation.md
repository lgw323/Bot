# Production cutover preparation

Precondition: PHASE 9 staging complete and explicit PHASE 10 authorization still pending. This is a
checklist and command review, not authorization to run production operations.

- Record clean Pi hardware/storage/filesystem/network inventory and staging SLO/soak results.
- Verify ARM64 native dependencies, ffmpeg, Gateway/voice, Gemini, Watch browser/tunnel/TLS and actual
  systemd/polkit/secret permissions. Compare both process release identities.
- Approve exact release/config versions, production secret handling, private backup destination,
  remote restore proof, six-hour RPO, approximate one-hour RTO, minimum seven-day rollback and disk budget.
- Rehearse interruption at every activation boundary, including host reboot and filesystem durability.
- Preserve verified pre-migration encrypted data, old release+venv, V1 reader and Music checkpoint.
- Plan one Gateway token owner: stop V1 before starting V2 with the production token. Never dual-connect.
- Approve maintenance communication, final backup/reconciliation, rollback owner and observation window.

Review commands that will be needed, without executing them in Phase 8:

```sh
ops backup
ops rehearse --destination /var/lib/discordbot/state/cutover-rehearsal-unique.db
ops deploy --revision "$CUTOVER_COMMIT" --policy /etc/discordbot/update.json --wheels "$APPROVED_WHEELHOUSE"
ops health
```

Postcondition: written sign-off and a separately authorized production plan. Actual production DB
migration/cutover, rollback-window abandonment, secret rotation, backup-destination change and V1
removal are not implied. PHASE 8 does not start PHASE 9 automatically.
