# 11. Product Requirements Document

## 1. Background

현재 봇은 친구 Discord 서버의 음악 bot에서 출발해 summary, XP, birthday, Watch
Together, 운영 자동화가 한 process에 누적됐다. 주요 기능은 유용하고 test도 130개가
통과하지만 Discord Gateway, public web traffic, media subprocess/thread, Gemini, SQLite와
logging이 lifecycle·capacity 경계 없이 결합돼 있다. 간헐적 지연과 crash의 현장 원인은
계측할 수 없고 부분 기동도 정상처럼 보인다. 기존 구현을 확대하지 않고 사용자 동작을
역공학해 안정성과 진단 가능성을 우선하는 새 시스템을 구축한다.

## 2. Objective

- 45개 capability의 승인된 동작을 누락 없이 재구현한다.
- 한 guild/기능/외부 서비스 장애를 Discord gateway와 다른 기능에서 격리한다.
- interaction, DB, 외부 API, queue/task의 latency와 failure를 운영자가 설명할 수 있게 한다.
- 배포·backup·restore·rollback을 재현 가능하고 검증 가능한 절차로 만든다.
- 기능 추가 시 Discord SDK, business rule, storage를 독립적으로 test할 수 있게 한다.

## 3. Non-goals

- 이 설계 단계에서 source code, schema, dependency, command를 변경하지 않는다.
- 확인되지 않은 UX를 개선한다는 이유로 message, permission, timing을 바꾸지 않는다.
- 현재 규모의 근거 없이 Kubernetes, Kafka, Redis, 다수 microservice를 도입하지 않는다.
- Discord 외 플랫폼, web 관리 console, 새로운 음악 provider를 추가하지 않는다.
- 승인 없이 기존 backup/SQLite/music JSON 호환성을 종료하지 않는다.

## 4. Users

| actor | 필요 |
| --- | --- |
| 일반 Discord 사용자 | 빠른 command, XP/profile/birthday list, summary, Watch creation |
| 음악 청취자 | 안정적인 queue/playback/UI/favorites/restore |
| Watch 참여자 | 링크만으로 공동 재생·chat·playlist, 명확한 만료 |
| master 관리자 | birthday mutation, restart/update, Watch 강제 종료 |
| 운영자 | health, 장애 원인, backup/restore, atomic deploy/rollback |
| 개발자 | 격리된 module, deterministic test, 명시 contract |

## 5. Current Feature Set

45개 capability는 [기능 인벤토리](03-feature-inventory.md)에 있다. 큰 범주는 lifecycle/
backup 5개, summary 5개, music 18개, leveling/birthday 8개, Watch 7개, 암묵/legacy 2개다.
명시 slash command 8개, default help 1개, UI callback 약 31개, HTTP 4개, WebSocket 1개다.

## 6. Required Feature Set

- F001–F043의 승인된 사용자 결과와 데이터 의미를 보존한다.
- F044 help와 F045 persisted volume은 rollback window 동안 compatibility contract로 보존한다.
- autoplay는 현재 결함을 복제하지 않고 의도된 추천 기능으로 구현한다.
- Watch의 no-login/no-host UX, URL/API/message compatibility, 30초/5초 유예를 보존한다.
- 운영자는 capability별 degraded/ready 상태, 안전한 update와 encrypted recovery를 가져야 한다.

## 7. Functional Requirements

정식 번호와 검증은 [12-functional-requirements.md](12-functional-requirements.md)에 있다.
FR-001–010은 lifecycle/interface, FR-011–025는 music, FR-026–030은 summary,
FR-031–037은 XP/birthday, FR-038–044는 Watch, FR-045–050은 운영/data다.

## 8. Non-Functional Requirements

[13-non-functional-requirements.md](13-non-functional-requirements.md)의 NFR-001–037을
적용한다. 핵심은 failure isolation, bounded concurrency, latency SLO, typed configuration,
structured telemetry, least privilege, compatible migration이다.

## 9. Reliability Target

- 필수 capability가 준비되지 않으면 전체 readiness를 내리거나 명시적 degraded state로
  표시한다. online presence만으로 정상이라 판정하지 않는다.
- Watch web crash/폭주는 Discord gateway process를 종료시키지 않는다.
- optional Gemini/gTTS/YouTube 장애는 해당 요청만 실패하며 다른 command를 계속 처리한다.
- 모든 task/subprocess는 owner, deadline, cancellation/reap 경로를 가진다.
- 정상 종료 시 10초 안에 신규 work admission을 막고 in-flight 작업을 제한 시간 내 정리한다.
- 제안 초기 목표: 월간 bot command plane 99.5% 가용성. 승인된 초기 RPO는 최대 6시간,
  RTO는 약 1시간이며 backup age가 RPO보다 나빠지면 alert한다. 가용성/SLO threshold는
  실제 Pi baseline 뒤 조정한다.

## 10. Performance Target

실제 Pi baseline 전의 제안값이다.

| 지표 | 목표 |
| --- | --- |
| interaction initial ACK | p95 <1s, p99 <2s, 절대 3초 전에 response/defer |
| local non-AI command completion | p95 <2s, p99 <5s(외부 download 제외) |
| SQLite repository read/write execution | p95 <25ms / <50ms, queue wait 별도 측정 |
| event-loop lag | p99 <100ms, 1s 초과 alert 후보 |
| summary | queue 포함 제외 명확히, admitted request total deadline 60s |
| metadata/search | 20s total deadline |
| media download attempt | 최대 180s, 전체 retry budget 별도 제한 |
| Watch relay | 정상 peer p95 <250ms; 느린 peer는 timeout 후 격리 |

## 11. Data Requirements

- 기존 SQLite six-table 의미, encrypted V2/legacy restore, music snapshot을 전환기 동안 읽는다.
- 실제 DB/backup/log를 test에서 사용하지 않는다.
- migration은 version/checksum, pre-backup, idempotent resume, semantic validation, rollback
  compatibility를 가진다.
- favorites는 user-global, XP/birthday/play counts는 승인된 guild scope를 유지한다.
- snapshot은 atomic publish하고 실제 restore 성공 ack 전 삭제하지 않는다.
- retention/RPO/RTO/key rotation은
  [미결 질문](../current/open-questions.md) 결정에 따른다.

## 12. Security

- token/API/backup key는 source/log에 없고 최소 권한 OS secret로 주입한다.
- Discord operation마다 actor/guild/channel/master 정책을 application boundary에서 확인한다.
- summary source ACL을 확인하고 외부 전송 consent/redaction 정책을 적용한다.
- Watch no-login 계약은 유지하되 capability token validation, TLS, Origin/CSRF, CSP,
  input schema/size/rate/cap, admin loopback authentication을 둔다.
- SQL은 parameterized repository만 사용하고 shell argument/remote credential을 log하지 않는다.

## 13. Observability

모든 interaction/job/session은 correlation ID를 가진다. JSON log에는 service, environment,
guild/channel/user의 허용된 pseudonymous 값, interaction/command/phase, duration, result,
error type을 둔다. command/DB/external/task/queue/WS/deploy/backup metric, liveness/readiness와
dependency state를 제공하며 alert는 사용자 action이 필요한 상태에만 보낸다.

## 14. Deployment

Raspberry Pi/Linux와 systemd를 유지하는 단순한 구조를 우선한다. `discord-bot`과
`watch-web` 두 process, release별 immutable directory/venv, tracked unit/timer template,
one deployment lock, preflight/test/migration/smoke, atomic symlink switch, release+dependency
rollback을 사용한다. 실제 `/home/os/bot`, account, cron을 승인 없이 바꾸지 않는다.

## 15. Migration

behavior freeze → characterization → platform skeleton → 낮은 위험 기능 → summary → Watch
split → music actor → data expand/contract → staging shadow/contract verification → feature-route
cutover → rollback window → legacy 제거 순이다. 동일 token으로 두 bot이 동시에 event를
처리하지 않는다. 단계별 상세는 [20-migration-plan.md](20-migration-plan.md)다.

## 16. Acceptance Criteria

1. F001–F043과 승인된 F044/F045의 requirement-to-test trace가 100%다.
2. 8 slash command, UI, HTTP/WS의 golden contract와 permission/ephemeral text가 승인됐다.
3. autoplay, executor saturation, music races, WebSocket slow peer, DB recovery/snapshot/backup,
   restart/rollback test가 통과한다.
4. 목표 Pi에서 ACK/latency/event-loop/RSS/CPU/load SLO를 만족한다.
5. 필수 dependency fault injection 시 failure isolation과 degraded/readiness가 확인된다.
6. production data copy가 아닌 승인된 sanitized snapshot으로 migration rehearsal과 rollback을
   두 번 성공한다.
7. backup restore drill이 승인된 RPO/RTO 안에서 성공한다.
8. security/privacy review와 BLOCKER ADR이 승인된다.
9. cutover 후 관찰 기간 동안 no-severity-1, data reconciliation 통과, rollback point 보존을
   확인한 뒤에만 legacy code를 삭제한다.
