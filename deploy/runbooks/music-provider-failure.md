# Music/provider failure

Precondition: identify whether failure is metadata/download, ffmpeg/voice, cache capacity, Gateway or
checkpoint. Inspect fixed errors and aggregate metrics; do not publish URLs, titles or raw stderr.

```sh
curl --fail --max-time 3 http://127.0.0.1:9010/metrics
sudo systemctl show discord-bot -p ActiveState -p Result
df -h /var/lib/discordbot/cache
ops restart
```

Use restart only after ruling out a provider outage and checking backup health. It checkpoints/stops,
backs up, restarts and gates readiness; it does not upgrade dependencies. Guild actor retry, bounded
provider queues, cache leases and idempotent session receipts remain PHASE 7 contracts. Do not manually
delete music_state.json or an in-use cache file to bypass recovery failure.

Postcondition: prior voice intent/queue/session recovered or failure is explicit. A provider version
change follows the separate emergency runbook. Direct playback fallback requires an explicit bounded
configuration/approval decision; this production entrypoint does not enable it by default.
