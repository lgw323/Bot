# DiscordBot V2 Rebuild Documentation

현재 상태는 **PHASE 10A COMPLETE / PHASE 10B INCOMPLETE — 서비스 정지**다.
PHASE 10을 재개하는 세션은 [부모 보고서](phases/phase-10/phase-10-report.md)와
[full-sweep 상세 보고서](phase-10-full-sweep-report.md)를 모두 읽는다.
부모는 cutover/migration·초기10B 이력과 전체 상태, 전용 보고서는 현재 full-sweep 실행·실패·수정·재시도의 기준이다.
각 범위에서 최신 continuation이 우선하며 구체적인 다음 작업은 [current plan](current/current-plan.md)을 따른다.

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

- [PHASE 8 report](phases/phase-08/phase-8-report.md),
  [deployment contract](phases/phase-08/deployment-contract.md),
  [backup/restore contract](phases/phase-08/backup-restore-contract.md),
  [operations contract](phases/phase-08/operations-contract.md),
  [staging runbooks](../../deploy/runbooks/README.md)

- [PHASE 9 staging evidence and remaining gates](phases/phase-09/phase-9-report.md)

- [PHASE 10 parent report](phases/phase-10/phase-10-report.md),
  [PHASE 10B full-sweep report](phase-10-full-sweep-report.md),
  [production migration contract](phases/phase-10/production-migration-contract.md),
  [config migration guide](phases/phase-10/config-migration-guide.md),
  [cutover approval gate/runbook](phases/phase-10/cutover-runbook.md)

새 Phase 산출물은 `phases/phase-XX/`에 의미 있는 파일명으로 추가한다. 과거 분석과 달라진
사실은 baseline을 고치지 않고 current ADR/trace/plan 또는 해당 Phase 보고서에 기록한다.
