# Current Rebuild Plan

Updated: 2026-09-05

## Current state

- PHASE 0 decision/baseline, PHASE 1 characterization, PHASE 2 skeleton/platform까지 완료했다.
- PHASE 2 package는 V1 route나 production process에 연결하지 않았고 SQLite repository 구현,
  schema 변경, data migration은 시작하지 않았다.
- 현재 단계는 **PHASE 2 완료 / PHASE 3 미진입**이다.

## Next gate

PHASE 3 Data compatibility는 사용자 지시 전 자동 진입하지 않는다. 진입 시에도 임시 DB와
copy fixture만 사용해 repository boundary, DB worker/capacity, migration ledger, explicit
bootstrap, legacy schema/backup reader와 corrupt recovery를 검증한다.

Production DB migration/cutover는 PHASE 10의 별도 승인 gate 전까지 금지한다. Raspberry Pi
설치·배포, Git clone 운영 설치, systemd, auto-update/auto-backup과 Watch tunnel 활성화도 현재
범위가 아니다.

전체 단계·rollback 설계는 frozen
[migration plan](../baseline/20-migration-plan.md), 최신 결정과 증거는
[Architecture Decision Log](architecture-decision-log.md),
[Requirement-to-Test Trace](requirement-test-trace.md),
[Open Questions](open-questions.md)를 따른다.

## Completed phases

- [PHASE 0 report](../phases/phase-00/phase-0-report.md)
- [PHASE 1 report](../phases/phase-01/phase-1-report.md)
- [PHASE 2 report](../phases/phase-02/phase-2-report.md)
