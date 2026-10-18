# Normal deploy

Precondition: common ops wrapper, reviewed explicit 40-hex commit, matching sealed ARM64 wheelhouse,
healthy same-version pair and sufficient disk. Source mirror/auth and update policy are operator-owned.

```sh
ops deploy --revision "$APPROVED_COMMIT" --policy /etc/discordbot/update.json --wheels /var/lib/discordbot/wheels
ops health
readlink -f /opt/discordbot/current
ops cleanup
```

The pipeline acquires the shared kernel lock before source preparation, creates a release-local venv,
verifies hashes/tests/data, captures an online encrypted backup, publishes an immutable manifest, stops
both services (including Music checkpoint), verifies stop results, captures the quiescent backup,
atomically switches current, starts both, and checks readiness/smoke before success audit.

Automatic update runs this same path with `--revision policy`, fetching only the explicit configured
branch. An unchanged release validates the manifest and records an unchanged result without restarting.
Daily 03:00 KST with up to 30 minutes jitter is an initial conservative proposal; it is not enabled in
Phase 8. Manual requests use the same operation lock and pipeline; their local inbox timer has no
network polling. The Discord application boundary is implemented but no production button is wired.

If the inbox remains `in_progress` after a crash, the timer deliberately does not replay it. Stop the
manual timer, acquire the operation lock through an operator recovery procedure, reconcile both
service identities and deployment/restart audit, then archive the uncertain request and record the
operator resolution before accepting another request. Never relabel uncertainty as success. The last
1,000 hashed receipts prevent recent duplicate delivery; this is a bounded replay window.

Postcondition: audit `deployment/ok`, matching readiness identity, retained previous release and
verified backup. Cleanup keeps current/rollback/activation targets, four recent releases and every
published release younger than seven days. Sixteen release directories block new builds rather than
discard protected history. Candidate failure never mutates current or its venv. A long deployment
must finish within its 30-minute systemd budget, including bounded recovery; inspect failures before retry.
