# Failed deploy rollback

Precondition: deployment exited nonzero or the two readiness identities disagree. Freeze further
updates. Preserve safe audit, activation/rollback metadata, manifests and encrypted backup evidence.

```sh
readlink -f /opt/discordbot/current
curl --fail --max-time 3 http://127.0.0.1:9010/health/ready
curl --fail --max-time 3 http://127.0.0.1:9011/health/ready
sudo systemctl show discord-bot watch-web -p ActiveState -p Result
```

The pipeline attempts rollback only once, verifies previous code/venv and live DB compatibility, then
rechecks both readiness/smoke responses. A failed rollback leaves services stopped where stop can be
confirmed; `failed_stop_unconfirmed` means even that guarantee was not established. Audit storage
failure never becomes success. Do not loop deploy/rollback automatically.

If the current data ledger is compatible with the reviewed previous release, deploy its exact commit
through `ops deploy --revision "$PREVIOUS_COMMIT" --policy /etc/discordbot/update.json --wheels "$PREVIOUS_WHEELHOUSE"` using the retained matching
wheelhouse. For an older V2 validator that rejects ledger 5, code-only rollback is invalid. Use the
separately approved pre-migration DB candidate and that release's recovery tooling/runbook; do not
down-migrate the live DB. V1 readers ignoring additive metadata does not imply old V2 validator safety.

Postcondition: one verified release runs in both processes, or a clearly reported stopped/unconfirmed
failure awaits operator action. Production data restoration still needs the PHASE 10 gate.
