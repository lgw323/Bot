# DiscordBot V2 Rebuild Documentation

현재 상태는 **PHASE 6 완료 / PHASE 7 미진입**이다. Production DB migration/cutover와
Raspberry Pi 운영 배포는 시작하지 않았다.

| 위치 | 책임 | 변경 정책 |
| --- | --- | --- |
| [baseline/](baseline/README.md) | 최초 V1 분석, 요구사항과 목표 설계 snapshot | 동결; 이후 Phase에서 수정하지 않음 |
| [current/](current/current-plan.md) | 최신 결정, trace, 미결 사항과 다음 gate | Phase 진행에 따라 최소한으로 갱신 |
| [phases/](phases/) | Phase별 완료 보고서, contract와 plan | 해당 Phase의 역사적 산출물로 보존 |

## Current sources of truth

- [Current plan and next gate](current/current-plan.md)
- [Architecture Decision Log](current/architecture-decision-log.md)
- [Requirement-to-Test Trace](current/requirement-test-trace.md)
- [Open Questions and unresolved decisions](current/open-questions.md)

## Phase deliverables

- [PHASE 0 report](phases/phase-00/phase-0-report.md)
- [PHASE 1 report](phases/phase-01/phase-1-report.md),
  [characterization contracts](phases/phase-01/characterization-contracts.md),
  [concurrency/failure plan](phases/phase-01/concurrency-failure-plan.md)
- [PHASE 2 report](phases/phase-02/phase-2-report.md),
  [platform contract](phases/phase-02/platform-contract.md)
- [PHASE 3 report](phases/phase-03/phase-3-report.md),
  [data compatibility contract](phases/phase-03/data-compatibility-contract.md),
  [actual DB rehearsal](phases/phase-03/migration-rehearsal.md)
- [PHASE 4 report](phases/phase-04/phase-4-report.md),
  [engagement contract](phases/phase-04/engagement-contract.md)

- [PHASE 5 report](phases/phase-05/phase-5-report.md),
  [Summary contract](phases/phase-05/summary-contract.md)
- [PHASE 6 report](phases/phase-06/phase-6-report.md),
  [Watch contract](phases/phase-06/watch-contract.md),
  [loopback contract](phases/phase-06/loopback-contract.md)

- [PHASE 7 report](phases/phase-07/phase-7-report.md),
  [Music contract](phases/phase-07/music-contract.md),
  [MusicActor contract](phases/phase-07/music-actor-contract.md),
  [media/cache contract](phases/phase-07/media-cache-contract.md)

새 Phase 산출물은 `phases/phase-XX/`에 의미 있는 파일명으로 추가한다. 과거 분석과 달라진
사실은 baseline을 고치지 않고 current ADR/trace/plan 또는 해당 Phase 보고서에 기록한다.
