# 23. Architecture Decision Log

2026-09-04 V2 구현 마스터 프롬프트와 승인된 PRD/architecture를 기준으로 ADR-001–ADR-015를
`ACCEPTED`로 전환했다. 승인자는 이 저장소의 사용자이며, capacity/SLO처럼 실측이 필요한
숫자는 결정 자체가 아니라 운영 parameter로 남겨 Phase 9에서 조정한다.

## ADR-001 Discord library

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** 현재 UI/voice/app-command contract가 discord.py 2.7 계열에 깊이 맞춰져 있다.
- **Options:** discord.py 유지; Pycord/Nextcord 전환; 직접 Gateway/REST 구현.
- **Decision:** 첫 재구축은 supported discord.py를 compatibility adapter 안에서 유지한다.
- **Reason:** 사용자 기능보다 library migration risk가 크며 SDK 격리는 adapter로 달성된다.
- **Trade-off:** 기존 library의 voice/reconnect/limit 동작을 계속 이해해야 한다.
- **Consequence:** domain/application에는 discord type을 금지하고 library 교체는 adapter contract로 가능하게 한다.

## ADR-002 Database

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** 소규모 Pi 운영, six-table SQLite와 backup 호환이 있으나 global lock/복구 문제가 있다.
- **Options:** SQLite 개선; PostgreSQL; 다른 embedded DB.
- **Decision:** 초기 migration은 SQLite compatibility repository와 dedicated DB execution을 쓴다.
- **Reason:** 현재 workload가 Postgres를 요구한다는 측정 근거가 없고 data migration risk를 줄인다.
- **Trade-off:** single-writer/host HA 한계와 careful backup이 남는다.
- **Consequence:** lock/latency SLO를 측정하고 초과할 때 Postgres ADR을 재개한다.

## ADR-003 Architecture style

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** 기능 결합을 끊어야 하지만 운영 인력·host는 작다.
- **Options:** layered monolith; hexagonal modular monolith; full microservices.
- **Decision:** bounded context와 ports를 가진 hexagonal modular monolith를 사용한다.
- **Reason:** test/의존성 격리를 얻으면서 network/배포 복잡도를 제한한다.
- **Trade-off:** import/ownership discipline을 CI로 강제해야 한다.
- **Consequence:** domain inward dependency, explicit contracts, composition-only wiring을 적용한다.

## ADR-004 Watch process isolation

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** public HTTP/WS가 Discord와 같은 loop에서 무제한 workload를 공유한다.
- **Options:** 같은 process 개선; 별도 process; 별도 host/service.
- **Decision:** 같은 Pi의 별도 `watch-web` process로 분리한다.
- **Reason:** 가장 직접적인 failure/resource isolation이며 별도 host는 현재 과도하다.
- **Trade-off:** internal control와 data single-owner protocol이 필요하다.
- **Consequence:** `watch-web`을 session data single writer로 하고 Discord↔Watch authenticated loopback contract와 두 health/unit을 설계한다.

## ADR-005 Background job and actor strategy

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** raw tasks/global state로 lifecycle·race·capacity가 불명확하다.
- **Options:** asyncio tasks 유지; in-process supervisor+actors; Redis/Celery broker.
- **Decision:** bounded in-process TaskSupervisor, guild MusicActor, WatchSessionActor를 사용한다.
- **Reason:** 현재 규모에서 broker 없이 단일 owner/backpressure를 제공한다.
- **Trade-off:** process crash 시 memory mailbox는 유실되므로 durable checkpoint가 별도 필요하다.
- **Consequence:** 모든 task에 owner/deadline/cancel/error metric, 모든 mailbox에 hard cap을 둔다.

## ADR-006 Cache

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** media/TTS cache가 local이며 일부 한도가 guild별 또는 없음이다.
- **Options:** bounded local disk; Redis; remote object storage.
- **Decision:** process-global budget의 bounded local disk cache와 atomic files를 사용한다.
- **Reason:** 재사용 범위가 한 host이고 Redis 운영 근거가 없다.
- **Trade-off:** host 교체/cleanup 시 cache miss를 수용한다.
- **Consequence:** size/TTL/eviction/permission/partial-file metric과 cleanup owner를 둔다.

## ADR-007 Deployment

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** live venv+hard reset과 code-only rollback이 비원자적이다.
- **Options:** in-place 개선; immutable directories+systemd; containers/orchestrator.
- **Decision:** release별 immutable directory/venv, atomic symlink, two systemd units/timers를 쓴다.
- **Reason:** Pi에서 단순하며 code+dependency rollback을 함께 보장한다.
- **Trade-off:** disk와 release cleanup/runbook이 필요하다.
- **Consequence:** one deployment lock, preflight/test/readiness/smoke, retained previous release를 요구한다.

## ADR-008 Observability

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** free-text logs만으로 latency/queue/root cause를 설명할 수 없다.
- **Options:** 향상된 text log; structured logs+local metrics; hosted full tracing.
- **Decision:** 공통 JSON logs, Prometheus-compatible metrics, health/correlation을 먼저 도입한다.
- **Reason:** 핵심 원인을 낮은 운영 비용으로 측정한다.
- **Trade-off:** metric endpoint/storage/alert destination을 결정해야 한다.
- **Consequence:** label cardinality/privacy 규칙과 bounded telemetry path를 적용한다.

## ADR-009 Configuration and secrets

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** import-time env parse와 scattered default가 partial startup을 만든다.
- **Options:** 현 env 직접 접근; typed startup config; remote config service.
- **Decision:** composition에서 한 번 typed immutable config로 검증하고 OS-managed secret file을 사용한다.
- **Reason:** 오타를 fail-fast하고 test/문서/default를 일치시킨다.
- **Trade-off:** migration 시 legacy env alias와 명확한 startup failure가 필요하다.
- **Consequence:** feature module의 `os.getenv`와 import side effect를 금지한다.

## ADR-010 Data compatibility and migration

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** schema ledger가 없고 기존 SQLite/backup/JSON rollback 호환이 중요하다.
- **Options:** big-bang conversion; expand/contract dual compatibility; permanent old schema.
- **Decision:** versioned/checksummed expand-contract migration과 rollback-window dual reader를 사용한다.
- **Reason:** data loss와 release rollback 위험을 최소화한다.
- **Trade-off:** 한시적으로 adapter와 schema 복잡도가 증가한다.
- **Consequence:** pre-backup, semantic reconciliation, idempotent resume, explicit contract removal gate가 필요하다.

## ADR-011 External resilience defaults

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** timeout/retry/circuit/concurrency가 dependency별로 누락·불일치한다.
- **Options:** SDK default; 공통 고정값; operation별 policy table.
- **Decision:** end-to-end deadline 안에서 operation별 timeout, retry eligibility/budget, circuit, semaphore를 선언한다.
- **Reason:** media/AI 특성이 달라 한 값은 부적절하지만 무정책은 전체 정체를 만든다.
- **Trade-off:** policy tuning과 더 많은 metric이 필요하다.
- **Consequence:** port call은 remaining deadline/correlation/idempotency를 전달하고 initial values는 load test 후 승인한다.

## ADR-012 Watch trust model

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** 제품은 login/host 없는 친구 링크 모델을 명시하지만 public surface 방어가 부족하다.
- **Options:** 현 capability-only; capability+transport/resource controls; account/host model.
- **Decision:** UX는 capability-only로 유지하고 TLS, expiry/revocation, Origin/CSRF/CSP, schema/rate/caps를 추가한다.
- **Reason:** 명시 제품 동작을 보존하면서 외부 workload와 link leakage 위험을 줄인다.
- **Trade-off:** capability를 잃으면 재인증 대신 새 invite가 필요하고 rate/cap 튜닝이 필요하다.
- **Consequence:** login/host 추가는 새 제품 ADR 없이는 금지하며 session URL을 secret처럼 취급한다.

## ADR-013 Guild isolation and configuration

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** 현재 운영은 소수 guild와 전역 channel ID를 사용하지만 향후 guild가 늘어날 수 있다.
- **Options:** single-guild hardcode; guild-keyed modular model; SaaS tenant platform.
- **Decision:** state, XP/birthday, music, feature flag와 channel config를 `guild_id`로 격리하는 multi-guild capable model을 사용하되 tenant 관리 platform은 만들지 않는다.
- **Reason:** cross-guild data/notification 노출을 막고 현재 규모에 불필요한 복잡성을 피한다.
- **Trade-off:** legacy global env 값을 guild config로 옮기는 compatibility adapter가 필요하다.
- **Consequence:** second-guild architecture/repository/application tests를 모든 guild-scoped capability에 둔다.

## ADR-014 Bootstrap, recovery objectives and rollback window

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** V1은 존재하는 0-byte/corrupt DB가 recovery를 우회할 수 있고 restore 훈련이 없다.
- **Options:** 자동 empty DB; fail-closed explicit bootstrap; remote service database.
- **Decision:** production empty DB 생성은 explicit admin operation만 허용한다. 초기 RPO는 최대 6시간, RTO는 약 1시간, V1-compatible rollback window는 최소 7일이다.
- **Reason:** 편의보다 실제 사용자 데이터 안전과 되돌릴 수 있는 전환을 우선한다.
- **Trade-off:** 최초 설치와 장애 복구에 operator 절차와 여러 recovery point가 필요하다.
- **Consequence:** startup integrity/schema/migration validation, verified encrypted backup, restore rehearsal와 old reader removal gate를 구현한다.

## ADR-015 Compatibility corrections

- **Status:** ACCEPTED (2026-09-04, user master prompt)
- **Context:** V1에는 autoplay 실패, play-count 중복, XP rounding drift, invalid birthday, stale UI처럼 보존하면 안 되는 결함이 있다.
- **Options:** byte-for-byte bug compatibility; 전면 UX 변경; 승인된 의미를 보존하며 결함만 교정.
- **Decision:** command/permission/publicness/data 의미와 주요 timing은 보존하되 autoplay를 정상 구현하고 play count는 playback session start당 한 번, voice XP는 완료된 분, 생일은 실제 날짜와 Feb-29→Feb-28 정책, queue/favorite는 stable ID와 pagination을 사용한다.
- **Reason:** 확인된 제품 계약은 지키면서 장애와 불일치를 요구사항으로 승격하지 않는다.
- **Trade-off:** 일부 결함 의존 사용자가 있다면 characterization 결과와 수정 동작을 명시해야 한다.
- **Consequence:** 각 test/fixture에 `PRESERVE`, `CORRECT`, `DECIDE` metadata를 연결하며 큰 제품 변경만 다시 승인받는다.

## ADR-016 Clean Raspberry Pi 5 production baseline

- **Status:** ACCEPTED (2026-09-04, user PHASE 1 direction)
- **Context:** 기존 Pi OS를 재설치하며 과거 host에는 bot 외 WordPress, CloudPanel과 폐기된 Cloudflare Tunnel/DNS가 함께 있었다.
- **Options:** 과거 전체 host 재현; bot 전용 clean host; 기존 host 수치를 그대로 acceptance baseline으로 사용.
- **Decision:** Raspberry Pi 5에 Ubuntu Server 24.04 LTS ARM64를 설치하고 Ethernet/LAN을 주 연결로 사용한다. host 범위는 Discord Bot V2, Watch Web, SQLite, 필요한 media/runtime dependency와 운영 도구로 제한한다. WordPress/CloudPanel은 설치하지 않고 기존 Tunnel/DNS는 재사용하지 않으며 Watch tunnel을 새로 구성한다.
- **Reason:** 폐기된 workload와 network 구성이 V2의 자원·보안·운영 기준을 왜곡하지 않게 한다.
- **Trade-off:** 과거 수치와 직접 비교할 수 없고 새 tunnel 및 clean staging baseline 측정이 필요하다.
- **Consequence:** PHASE 8/9에서 새 host inventory, Ethernet network, Watch tunnel/TLS와 부하·soak baseline을 기록한다. production DB migration/cutover는 PHASE 10 명시 승인 전 금지한다.
