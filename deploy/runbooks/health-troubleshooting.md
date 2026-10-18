# Health troubleshooting

Precondition: local approved host shell; no public exposure of the internal/health ports. Only public
Watch port 9000 is a tunnel candidate; 9001/9010/9011 must remain loopback-only.

```sh
curl --fail --max-time 3 http://127.0.0.1:9010/health/ready
curl --fail --max-time 3 http://127.0.0.1:9011/health/ready
curl --fail --max-time 3 http://127.0.0.1:9010/metrics
curl --fail --max-time 3 http://127.0.0.1:9011/metrics
sudo systemctl show discord-bot watch-web -p ActiveState -p Result -p NRestarts
sudo journalctl -u discord-bot -u watch-web --since '-15 minutes' --no-pager
```

Inspect logs locally; do not share raw legacy/vendor logs. V2 emitted operational events use fixed
names, centralized redaction and bounded fields; the durable audit stores operation/release/time/
result/safe reason/correlation only. Ten thousand audit files is a hard admission cap, requiring
explicit archive planning instead of silent evidence deletion.

Readiness is distinct from liveness: database/migration, Gateway/core initialization, Watch stale
cleanup/lease and all required listeners must be ready. Metrics include bounded task/cardinality,
DB probe latency/admission/recent failures, backup age/RPO, Watch sessions/clients, Summary waiting,
Music actors/cache bytes/process count. Missing probe progress fails readiness after 15 seconds.
Compare release identities before assuming a restart fixed anything.

Postcondition: cause classified as config/secret, DB, feature, listener, release or capacity; safe
evidence retained. Start-limit limits restart storms; reset/restart only after correcting the cause.
No hosted alert destination or measured Pi SLO is claimed by Phase 8.
