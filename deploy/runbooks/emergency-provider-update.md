# Emergency yt-dlp update

Precondition: provider breakage diagnosed, exact new version approved, previous immutable release
and matching wheelhouse retained. Work in an isolated source candidate. Do not run pip against current.

Change only the `yt-dlp==...` line in `deploy/dependencies.pins`; acquire/review its matching wheel in a
new wheelhouse while retaining every other pinned artifact unchanged. Commit the isolated pin change
and materialize the new hash lock. The emergency build rejects changes to any other dependency pin.

```sh
python3.12 "$CANDIDATE_SOURCE/deploy/wheels.py" "$NEW_WHEELHOUSE" "$CANDIDATE_SOURCE/deploy/dependencies.pins"
ops deploy --revision "$PROVIDER_COMMIT" --provider-only --policy /etc/discordbot/update.json --wheels "$NEW_WHEELHOUSE"
ops health
```

The provider_update audit and release manifest record the attempt and dependency identity. Full
deploy tests/backup/readiness/rollback gates still apply. No unbounded internet upgrade, live venv
mutation or dependency-wide resolver refresh occurs. If the new yt-dlp needs a different dependency,
stop and review a normal dependency change instead of bypassing the emergency guard.

Postcondition: staged real provider/voice smoke succeeds; otherwise rollback to the previous release
and its wheelhouse through the failed-deploy runbook. Phase 8 performs no actual provider call.
