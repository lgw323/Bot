# 09. Performance and Reliability Audit

## 우선순위 감사표

| ID / 심각도 | 문제·근거 | 조건 → 영향/장애 형태 | 재현성 | 새 설계 제거 방법 |
| --- | --- | --- | --- | --- |
| AUD-001 CRITICAL | DB는 global lock을 먼저 잡고 default executor의 `to_thread`를 기다림. yt-dlp/gTTS도 같은 executor (`database_manager.py`, `music_agent.py`) | 느린 media threads 포화 → 첫 DB caller가 lock 점유 → XP/생일/Watch/music DB 전체 정체, interaction timeout | 단위 stress로 재현 가능; Pi 빈도 미측정 | DB 전용 worker/pool, workload별 capacity, lock/queue metric, deadline |
| AUD-002 CRITICAL | `init_db`가 파일 존재만 검사 | 0-byte/잘못된 기존 DB → backup 복구 우회 → 조용한 빈 schema 또는 startup failure/data loss 인식 | temp file로 재현 가능, test 없음 | header+integrity+schema+identity gate, read-only fail, 명시적 bootstrap 승인 |
| AUD-003 HIGH | autoplay가 import되지 않은 `extract_ytdlp_info` 호출 (`music_core.py`) | empty queue+autoplay → `NameError`가 catch/log → 추천이 항상 실패 | 코드상 확정, success test 없음 | typed recommendation port와 contract test |
| AUD-004 HIGH | Watch broadcast가 same loop에서 socket별 timeout 없이 순차 await | 느린/악성 peer 또는 frame 폭주 → session HOL blocking, Discord heartbeat/interaction 지연 | slow fake socket으로 재현 가능 | 별도 process, per-session actor, send timeout, bounded fanout/rate/frame |
| AUD-005 HIGH | extension/sync/web task failure 후에도 startup 계속 | 설정 오류/bind/API failure → online이나 기능 일부 없음; updater는 active를 성공 판정 | 설정 fault injection 가능 | mandatory capability manifest, readiness, supervised task, degraded status |
| AUD-006 HIGH | MusicState를 UI/voice-after/TTS/autoplay/task가 무소유 변경 | 동시 요청/skip/retry → queue 순서 역전, double next, stale index로 잘못 삭제 | deterministic actor test 필요 | guild당 단일 actor/mailbox, stable item ID, invariant assertions |
| AUD-007 HIGH | Gemini timeout/concurrency와 source ACL 없음 | 느린 Gemini/동시 요청/권한 낮은 requester → task 누적, timeout, 비공개 원문 요약 노출 | mock+ACL test 가능 | authz precheck, 60s deadline, concurrency1/queue4, circuit breaker |
| AUD-008 CRITICAL | updater가 live venv 먼저 변경, code만 rollback, `flock`/timeout 없음 | cron/manual overlap 또는 bad dependency → mixed release, 장기 hang, 복구 후에도 incompatible env | shell integration/staging 필요 | immutable release+venv, one deployment lock, smoke/readiness, atomic pointer rollback |
| AUD-009 HIGH | correlation/latency/event-loop/executor/queue/task health 없음 | 실제 지연/crash → 원인과 영향 범위 미식별, MTTR 증가 | 현재 telemetry inspection 확정 | structured logs, metrics, traces/correlation, health/alert |
| AUD-010 HIGH | music snapshot은 task 중지 전 mutable state를 thread에서 읽고 parse 후 즉시 삭제 | update/restore failure → inconsistent JSON, 일부 guild 복원 실패 후 재시도 자료 소실 | concurrency/fault test 가능 | loop 내 immutable capture, atomic publish, schema version, restore ack 후 archive |
| AUD-011 HIGH | Watch invite-before-commit, add/close/connect race | 빠른 click 또는 DB/oEmbed 지연 → 404/이중 응답/orphan playlist/session | injected delay로 재현 가능 | commit-first saga, session actor, conditional writes, compensating delete |
| AUD-012 HIGH | DB live dump는 cron process라 app lock 비공유; 명시 snapshot 없음 | concurrent writes → cross-table 시점이 다른 latest backup | concurrent backup test 필요 | SQLite backup API/read transaction, cross-process lock, semantic validation |
| AUD-013 HIGH | root log ERROR를 Discord로 보내고 future 결과 미관찰; panel delete/resend | 오류 storm/Discord 장애 → unbounded sends/API churn, failure invisible | fake burst test 가능 | bounded log queue, batching/rate limit, stable panel edit, drop metric |
| AUD-014 HIGH | summary raw content/display names가 외부 prompt에 포함, preload 경계 dedup 없음 | sensitive conversation/prompt injection/restart → privacy leak, 누락/중복 | code 확정; policy 미확인 | consent/ACL/redaction, message-ID cursor, prompt data boundary, retention policy |
| AUD-015 HIGH | fixed summary/music/log channels와 birthday guild iteration | multi-guild 사용 → 다른 guild 알림/데이터가 fixed channel로 노출 | second-guild integration test | explicit deployment scope or per-guild config/repository |
| AUD-016 MEDIUM | 모든 DB query 직렬, query index/limits 부족, connection 매번 생성 | user/guild/favorite growth → lock hold/scan 증가, 전체 feature latency | synthetic data benchmark | suitable indices, pagination, read/write paths, query budget |
| AUD-017 MEDIUM | TTS lock이 `play()` 호출만 보호; error 후 interrupt flag 고착 가능 | 동시 join/play exception → overlapping TTS 또는 music callbacks 영구 무시 | fake voice test | actor-owned interrupt state, try/finally, bounded cache/atomic files |
| AUD-018 MEDIUM | queue/favorites/Watch resources와 일부 cache가 무제한 | 장시간/악성 입력 → memory/disk/socket/task growth | load test | explicit caps, TTL, admission control, backpressure/eviction |
| AUD-019 MEDIUM | browser가 terminal close 후 3초마다 무기한 reconnect | expired/closed room → client/network/server retry load; startup stale session 부활 race | browser/WS test | terminal close code, capped jitter backoff, stale cleanup readiness barrier |
| AUD-020 MEDIUM | defer/followup/error response ownership이 command마다 다름 | DB contention/Watch insert failure → 3초 timeout 또는 `InteractionResponded` | delayed mock으로 재현 가능 | one interaction responder, 800ms defer policy, idempotent completion |
| AUD-021 HIGH | file log는 URL/ID 중앙 redaction 없이 30일 보존 | 음악 취향, Watch capability, IDs/credential-bearing command error → local leakage | log assertion 가능 | sink 이전 classification/redaction, hash IDs, retention/access controls |
| AUD-022 MEDIUM | XP rounding 두 경로, voice session user-only, invalid birthday 허용 | seconds/channel move/multi-guild/date input → profile/rank 불일치 또는 잘못된 알림 | unit test 가능 | single domain formula/key/date policy after approval |
| AUD-023 MEDIUM | backup key rotation, restore drill, backup age alert 없음 | key loss/corrupt latest/silent cron failure → 복구 시점에 발견 | 운영 상태 미확인 | key IDs, immutable retention, scheduled restore verification, RPO alert |
| AUD-024 MEDIUM | dependency 하한 위주, actual deploy lockfile/CI 없음 | reinstall/provider update → 비재현 build/런타임 회귀 | clean build 비교 가능 | pinned lock/release manifest, canary and rollback |

## Discord-specific assessment

- interaction의 3초 초기 응답 제한을 일관되게 보장하지 않는다. target은 handler 시작 후
  800ms 안에 완료 확신이 없으면 defer하고 ACK p99 <2s를 목표로 한다.
- REST rate limiting은 discord.py 내부 처리에만 의존하고 dashboard/log update coalescing이
  없다.
- reconnect `on_ready`는 재진입 가능하지만 모든 task/panel/load가 동일한 idempotency key를
  쓰지 않는다.
- 현재 2 guild 전제에서는 sharding 근거가 없다. guild/traffic 측정값이 threshold를 넘을
  때만 결정한다.

## 판정의 한계

코드로 성립하는 경로와 자동 test 결과는 확정했지만 실제 Pi의 빈도·p95/p99, 최근 crash
stack, RSS/CPU, Gateway heartbeat, Discord rate-limit 응답은 관측하지 못했다. 그러므로
성능 목표는 초기 제안이며 baseline 측정 후 승인한다.
