# Current Rebuild Plan

Updated: 2026-09-06

## Current state

- PHASE 0–3 완료 상태를 기준으로 PHASE 4 Engagement를 구현했다. text/voice XP, profile/ranking,
  birthday와 필요한 Discord composition을 synthetic DB와 fake clock/Discord로 검증했다.
- PHASE 3 data boundary 위에 version 3 metadata를 expand-only로 추가했다. startup에서 자동
  migration하지 않으며 명시적으로 준비한 copy만 feature에 연결한다.
- V1 route, production process, 원본 DB와 Pi에는 연결·변경하지 않았다.
- 현재 단계는 **PHASE 4 완료 / PHASE 5 미진입**이다.

## Next gate

PHASE 5 Summary는 사용자 지시 전 자동 진입하지 않는다. 진입하면 PHASE 4 전체 baseline을
재실행하고 승인된 Summary policy와 source ACL을 application/adapter에 연결한다.
신규 data 의미 변경이나 기존 사용자 값의 자동 정리는 금지한다.
music JSON/0.5/default/ACK는 PHASE 7에, Watch write owner는 PHASE 6에 남아 있다.

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
