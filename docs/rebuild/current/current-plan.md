# Current Rebuild Plan

Updated: 2026-09-13

## Current state

- PHASE 7 완료 commit `e0449c2`와 `592 passed, 0 xfailed` 기준선을 재확인했다.
- PHASE 8은 immutable code/venv release, atomic activation/rollback, 두 executable service,
  typed credentials, encrypted backup/isolated restore, timer/manual boundary와 runbooks를 구현했다.
- Engagement / Summary / Watch / Music, migration ledger 5와 V1 production runtime을 보존했다.
  실제 DB, 운영 secret, Pi와 production route는 사용하거나 변경하지 않았다.
- 최종 전체 strict test는 **673 passed, 0 xfailed**다. 검증과 focused commits는
  [PHASE 8 report](../phases/phase-08/phase-8-report.md)에 기록한다.
  strict xfail은 0이며 architecture/import/task/executor 경계를 유지한다.
- rebuild index의 오래된 PHASE 6 상태 표시를 실제 완료 상태와 맞췄다. 과거 Phase와 baseline은 동결했다.
- 현재 단계는 **PHASE 8 완료 / PHASE 9 미진입**이다.

## Next gate

PHASE 9 clean Pi staging은 사용자 지시 전 자동 진입하지 않는다. ARM64 wheel 준비, OS credential/
group/WAL 권한, systemd/polkit, 실제 symlink/fsync, Gateway/Voice/Watch/Tunnel smoke와 Pi 부하/soak,
RPO/RTO 측정을 검증한다. 수치는 실측 SLO가 아닌 초기 hard ceiling이다.

Production DB migration/cutover는 PHASE 10의 별도 승인 gate 전까지 금지한다. Raspberry Pi
설치·배포, systemd/timer 활성화, Watch tunnel, production login과 실제 데이터 사용은 이번
Phase에서 수행하지 않았다. push/PR/deploy도 하지 않았다.

전체 단계·rollback 설계는 frozen [migration plan](../baseline/20-migration-plan.md),
최신 결정과 증거는 [Architecture Decision Log](architecture-decision-log.md),
[Requirement-to-Test Trace](requirement-test-trace.md), [Open Questions](open-questions.md)를 따른다.

## Completed phases

- [PHASE 0 report](../phases/phase-00/phase-0-report.md)
- [PHASE 1 report](../phases/phase-01/phase-1-report.md)
- [PHASE 2 report](../phases/phase-02/phase-2-report.md)
- [PHASE 3 report](../phases/phase-03/phase-3-report.md)
- [PHASE 4 report](../phases/phase-04/phase-4-report.md)
- [PHASE 5 report](../phases/phase-05/phase-5-report.md)
- [PHASE 6 report](../phases/phase-06/phase-6-report.md)
- [PHASE 7 report](../phases/phase-07/phase-7-report.md)
- [PHASE 8 report](../phases/phase-08/phase-8-report.md)
