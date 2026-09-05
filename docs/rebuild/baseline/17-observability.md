# 17. Observability

## Structured logging schema

모든 sink 이전에 같은 JSON event를 만든다.

| field | 설명 |
| --- | --- |
| `timestamp`, `level`, `service`, `environment`, `release` | 시점/배포 식별 |
| `event`, `component`, `phase` | 안정된 event name과 단계 |
| `correlation_id`, `interaction_id`, `job_id`, `session_hash` | 한 실행 연결; capability 원문 금지 |
| `guild_id_hash`, `channel_id_hash`, `user_id_hash` | 승인 시 pseudonymized 식별; 원문 최소화 |
| `command`, `feature_id`, `actor_id_hash` | 기능 문맥 |
| `duration_ms`, `queue_wait_ms`, `attempt` | 지연 원인 분리 |
| `result`, `error_type`, `error_code`, `exception` | 결과; stack은 server log에만 |
| `dependency`, `http_status`, `rate_limited` | external 상태 |

message content, music URL/title, Gemini prompt, Watch UUID/link, token/key, remote credential,
raw WebSocket payload는 기본적으로 기록하지 않는다. redaction은 file/console/Discord sink
이전에 적용한다. Discord alert는 새 message 폭주 대신 stable incident/thread/panel update와
dedupe/rate limit을 쓴다.

## Metrics

| 영역 | metric 예 |
| --- | --- |
| Discord | `command_total{command,result}`, `command_latency_seconds`, `interaction_ack_seconds`, `gateway_reconnect_total`, `rest_rate_limit_total` |
| event loop/executor | `event_loop_lag_seconds`, `executor_active/queued`, `task_active/oldest`, `task_failure_total` |
| actors/queues | `actor_mailbox_depth{type}`, `admission_rejected_total`, `state_conflict_total` |
| DB | `db_query_seconds{operation}`, `db_queue_wait_seconds`, `db_busy_total`, `migration_version`, `integrity_check` |
| external | `external_request_seconds{service,operation,result}`, `retry_total`, `circuit_state`, `timeout_total` |
| music | queue length, active download, cache bytes/evictions, playback retry/skip, restore success |
| summary | captured/pruned messages, queue depth, Gemini latency/error, no-data/ACL denial |
| Watch | sessions/connections, frame bytes/rate, relay latency, slow-client close, expiry, reconnect |
| operations | release/readiness, backup age/size/success, restore drill, deploy/rollback duration/result |
| resource | RSS, CPU, file descriptors, disk/cache bytes, process restart count |

label에 raw user/session/URL을 넣어 cardinality와 privacy를 폭발시키지 않는다.

## Health model

- `/live`: event loop와 process가 응답 가능한지. 외부 dependency failure 때문에 false로 하지 않는다.
- `/ready`: typed config, DB integrity/schema, mandatory Cog/use case, Discord ready, worker supervisor,
  process별 listener가 traffic을 받을 준비가 됐는지.
- `/dependencies`: Discord/Gemini/YouTube/DB/backup age 등 `ok/degraded/open/unknown` 상태와
  마지막 성공 시각. secret-free, 외부 공개 금지 또는 제한.
- capability registry: `music`, `summary`, `engagement`, `birthday`, `watch`, `operations`별
  ready/degraded reason을 관리 panel과 deploy smoke가 함께 사용한다.

## Alert and runbook policy

page 후보는 readiness 지속 실패, restart loop, DB integrity/data error, backup RPO 위반,
command error/ACK breach 급증, event-loop lag, disk 부족이다. optional provider 단일 실패는
ticket/warning에서 시작해 circuit 지속·사용자 영향률이 threshold를 넘을 때 승격한다. 모든
alert에는 owner, dashboard link, 첫 진단 query와 rollback/runbook을 연결한다.

초기 배포 전 1주 baseline에서 p50/p95/p99와 정상 재연결/업데이트 패턴을 수집하고 alert
threshold를 튜닝한다. telemetry 자체가 Gateway를 막지 않도록 queue는 bounded이고 drop/sample
count를 별도 metric으로 남긴다.
