# 20. Migration Plan

## 원칙

빅뱅 교체가 아니라 기능 route와 data compatibility를 단계별로 바꾼다. 단, 같은 Discord
token으로 old/new bot을 동시에 연결해 event를 이중 처리하지 않는다. 각 단계는 entry
criteria, automated evidence, deploy flag, rollback point를 가진다. source/schema deletion은
마지막이며 별도 승인을 받는다.

## Phases

| 단계 | 작업 | exit criteria | rollback |
| --- | --- | --- | --- |
| 0 Decision closure/baseline | F001–F045 owner/status, 결정 반영, V1 test/trace, 운영 baseline 계획 | BLOCKER 0, 모든 기능 disposition과 Phase 1 trace | 문서만 되돌림 |
| 1 Characterization | current adapters와 결함 경계 test 보강 | command/UI/data/retry/timing coverage trace | test-only revert |
| 2 Skeleton/platform | composition, typed config, errors, supervisor, telemetry, ports | no side-effect import; health/task tests | old process untouched |
| 3 Data compatibility | current SQLite/backup/JSON read adapter, migration ledger 설계 | copy/backup restore/reconciliation/rollback rehearsal | old schema reader 유지 |
| 4 Low-risk engagement | profile/rank/text/voice XP, birthday behind route flags | formula/policy 결정, guild isolation tests | feature route→old |
| 5 Summary | capture cursor, ACL/privacy, bounded Gemini worker | golden output shell + fault/concurrency tests | route→old, no durable change |
| 6 Watch | separate process, session actor, compatibility protocol/internal control | HTTP/WS contract, races, security/load, admin close | old same-process route; DB compatibility |
| 7 Music | guild actor, backend ports, UI adapter, snapshot | all controls/autoplay/retry/TTS/cache/restart/soak | route→old; snapshot dual-read |
| 8 Operations | immutable releases, tracked units/timers, backup snapshot, readiness smoke | deploy+dependency rollback and restore drill | atomic prior release pointer |
| 9 Staging | dedicated guild/token, sanitized data, clean Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet load·fault·soak, 새 Watch tunnel 검증 | SLO/security/runbook/reconciliation approval | no production impact |
| 10 Production cutover | maintenance gate, final backup, one bot connection, flags in waves | health/SLO/data/user smoke, observation window | stop new, restore prior release/compatible data |
| 11 Legacy removal | old routes/code/format reader 제거 | rollback window 종료, no Sev1, reconciliation and owner sign-off | archived release/data retained |

## Suggested feature priority

1. platform/data safety/observability는 기능 migration보다 먼저다.
2. read-heavy profile/ranking과 birthday를 통해 port/Discord adapter를 검증한다.
3. Summary는 durable write가 적지만 privacy/timeout gate가 필요하다.
4. Watch는 process boundary와 public protocol 때문에 독립 release로 검증한다.
5. Music은 상태·voice·subprocess·UI·복원 위험이 가장 높아 마지막 핵심 migration으로 둔다.
6. deployment/backup 전환은 application cutover 전에 반복 연습한다.

## Data migration

- 현재 PHASE 1에서는 production DB migration/cutover를 실행하지 않는다. production data를
  건드리는 단계는 PHASE 10 사용자 승인 gate 뒤에만 수행한다.
- production DB를 개발/test에 복사하지 않는다. 운영 rehearsal은 제한된 operator 절차와
  암호화 snapshot을 사용한다.
- expand-only schema → dual-compatible adapter → backfill/reconcile → new write → 관찰 → old
  reader 제거 → contract 단계로 간다.
- migration 전 verified backup과 checksum/row count/semantic report를 만든다.
- migration step은 version/checksum/idempotency와 실패 위치를 기록하며 재개 가능해야 한다.
- `music_state.json`은 dual-reader, version, atomic rename, restore ack를 사용한다.
- favorite global scope, historical play count/XP/birthday와 Watch cleanup semantics를 검증한다.

## Cutover runbook outline

1. 승인자, release, target host, old/new config fingerprint, rollback release를 확인한다.
2. deployment lock을 획득하고 backup age/integrity/restore sample을 확인한다.
3. new immutable release를 offline build/test하고 optional migration dry-run/reconcile한다.
4. old bot admission을 멈추고 graceful snapshot/checkpoint 후 한 process만 Discord에 연결한다.
5. readiness와 slash/profile/music/summary/Watch synthetic smoke를 통과시킨다.
6. 낮은 위험 route부터 enable하고 ACK/error/DB/event-loop/queue/data diff를 관찰한다.
7. threshold 위반 시 admission stop, new process stop, compatible schema에서 old release pointer로
   되돌리고 session/data reconciliation을 수행한다.

## Legacy deletion gate

승인된 관찰 기간 동안 severity-1/데이터 불일치가 없고, 모든 기능 golden/부하/fault test,
production metric SLO, backup restore와 rollback rehearsal, 운영 runbook/owner 교육이 완료된
후 별도 승인으로 삭제한다. 삭제 commit은 feature migration과 분리하고 이전 release와
decrypt 가능한 backup을 retention 정책 동안 보존한다.
