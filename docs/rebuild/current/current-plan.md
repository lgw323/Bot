# Current Rebuild Plan

Updated: 2026-09-08

## Current state

- PHASE 4 기준선 `358 passed, 9 xfailed`를 재확인하고 PHASE 5 Summary를 구현했다.
- capture/preload/retention, 기본·고급·refresh/topic, source ACL/privacy, Gemini boundary,
  60초 end-to-end deadline과 active 1/waiting 4를 synthetic/fake 환경에서 검증했다.
- PHASE 3 data layer와 PHASE 4 Engagement, V1 route, 실제 DB와 Pi는 변경하지 않았다.
- 최종 전체 test는 **434 passed, 4 xfailed**이며 반복 경합 검증은 **900 passed**다.
- 현재 단계는 **PHASE 5 완료 / PHASE 6 미진입**이다.

## Next gate

PHASE 6 Watch는 사용자 지시 전 자동 진입하지 않는다. 진입하면 PHASE 5 전체 baseline과
남은 strict xfail 4개(Watch 2, Music 2)를 재확인한다. 실제 외부 API/Discord 권한 배치와
Pi 부하 검증은 staging에 남긴다. Music JSON/0.5/default/ACK는 PHASE 7 소유다.

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
