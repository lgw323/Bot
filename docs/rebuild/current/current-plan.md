# Current Rebuild Plan

Updated: 2026-09-10

## Current state

- PHASE 5 기준선 `434 passed, 4 xfailed`를 재확인하고 PHASE 6 Watch를 구현했다.
- Discord와 watch-web의 독립 composition, authenticated loopback, durable-before-invite,
  bounded session mailbox/peer, capability/security, 30초+5초 lifecycle과 stale readiness를 검증했다.
- Phase 3 저장 경계에 additive migration 4를 추가했다. 기존 1–3 checksum과 V1 reader를
  보존했으며 Engagement/Summary 동작, V1 운영 route, 실제 DB와 Pi는 변경하지 않았다.
- 최종 전체 strict test는 **504 passed, 2 xfailed**이며 14개 경합의 100회 반복은 **1400 passed**다. 상세 결과는
  [PHASE 6 report](../phases/phase-06/phase-6-report.md)에 기록한다.
- 현재 단계는 **PHASE 6 완료 / PHASE 7 미진입**이다.

## Next gate

PHASE 7 Music은 사용자 지시 전 자동 진입하지 않는다. 진입하면 PHASE 6 전체 baseline과
남은 strict xfail 2개(Music)를 재확인한다. 실제 외부 API/Discord 권한 배치, dual-process
crash, browser/YouTube와 Pi 부하 검증은 staging에 남긴다. Music JSON/0.5/default/ACK는 PHASE 7 소유다.

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
- [PHASE 3 report](../phases/phase-03/phase-3-report.md)
- [PHASE 4 report](../phases/phase-04/phase-4-report.md)
- [PHASE 5 report](../phases/phase-05/phase-5-report.md)
- [PHASE 6 report](../phases/phase-06/phase-6-report.md)
