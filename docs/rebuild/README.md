# DiscordBot 재구축 설계 문서

이 디렉터리는 2026-09-04 시점의 `main` 브랜치(`8432fde`)를 기준으로 현행 시스템을
역공학하고, 기존 구현과 독립적인 차기 시스템을 설계한 문서 묶음이다. 이 단계에서는
소스 코드, 데이터베이스, 의존성, 배포 설정을 변경하지 않았다.

## 읽는 순서

1. [Executive summary](00-executive-summary.md)
2. [현행 시스템](01-current-system-overview.md)과 [저장소 지도](02-repository-map.md)
3. [기능](03-feature-inventory.md), [인터페이스](04-command-event-inventory.md),
   [실행 흐름](05-runtime-flow.md), [데이터](06-data-model.md)
4. [신뢰성 감사](09-performance-reliability-audit.md),
   [구조 문제](10-architecture-problems.md), [보안](18-security-review.md)
5. [PRD](11-prd.md), [요구사항](12-functional-requirements.md),
   [비기능 요구사항](13-non-functional-requirements.md)
6. [목표 아키텍처](14-target-architecture.md)부터
   [마이그레이션 계획](20-migration-plan.md)까지
7. 구현 전에는 반드시 [결정 closure](22-open-questions.md)와
   [결정 기록](23-decision-log.md)을 확인한다.

## 전체 문서 목록

| 문서 | 역할 |
| --- | --- |
| [00 Executive summary](00-executive-summary.md) | 분석 결론, 핵심 위험, 구현 gate |
| [01 Current system](01-current-system-overview.md) | 운영 배치, 시작/종료, 상태 소유권 |
| [02 Repository map](02-repository-map.md) | 코드·dependency·config·test 지도 |
| [03 Feature inventory](03-feature-inventory.md) | F001–F045와 유지 등급 |
| [04 Command/event inventory](04-command-event-inventory.md) | Discord UI/event 및 HTTP/WS 계약 |
| [05 Runtime flow](05-runtime-flow.md) | 주요 sequence, task와 contention 경로 |
| [06 Data model](06-data-model.md) | SQLite/file/cache/memory와 ERD |
| [07 External dependencies](07-external-dependencies.md) | 외부 시스템과 회복 정책 |
| [08 Business rules](08-business-rules.md) | 확정 규칙, PHASE 0 해소 결정, bug 분리 |
| [09 Reliability audit](09-performance-reliability-audit.md) | severity별 24개 장애·성능 발견 |
| [10 Architecture problems](10-architecture-problems.md) | smell과 목표 dependency boundary |
| [11 PRD](11-prd.md) | 16개 필수 절의 제품 요구사항 |
| [12 Functional requirements](12-functional-requirements.md) | FR-001–FR-050과 acceptance source |
| [13 Non-functional requirements](13-non-functional-requirements.md) | NFR-001–NFR-037과 제안 SLO |
| [14 Target architecture](14-target-architecture.md) | process/layer/context/failure isolation |
| [15 Async design](15-async-concurrency-design.md) | ACK, actor, task, timeout, backpressure |
| [16 Error policy](16-error-handling-policy.md) | 오류 분류, UX, retry/alert/process 정책 |
| [17 Observability](17-observability.md) | log, metric, health, alert 설계 |
| [18 Security review](18-security-review.md) | threat boundary, permission, privacy |
| [19 Testing strategy](19-testing-strategy.md) | characterization부터 Pi E2E까지 |
| [20 Migration plan](20-migration-plan.md) | 단계별 cutover/rollback/legacy gate |
| [21 Target repository](21-target-repository-structure.md) | 목표 tree와 dependency rule |
| [22 Decision closure](22-open-questions.md) | BLOCKER closure와 phase별 실측 gate |
| [23 Decision log](23-decision-log.md) | 승인된 architecture와 product decision ADR |
| [24 Requirement/test trace](24-requirement-test-trace.md) | F001–F045 ↔ FR ↔ 현재/계획 test |
| [25 Phase 0 baseline](25-phase-0-baseline.md) | 결정 closure, V1 test 결과, Pi 측정 계획과 Phase 1 gate |

## 증거 표기

- **확정**: 현재 코드, 테스트 또는 기존 제품 계약에서 직접 확인했다.
- **추론**: 코드상 가능한 장애 경로이나 운영 계측으로 발생 빈도를 확인하지 못했다.
- **미확인**: `.env`, 실제 운영 로그, Discord Developer Portal, 채널 ACL,
  Cloudflare 설정처럼 저장소만으로 확인할 수 없다.

코드 링크는 이 분석 시점의 줄 번호다. 구현이 변경되면 링크와 판단을 함께 갱신해야 한다.
