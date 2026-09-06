# Current Rebuild Plan

Updated: 2026-09-06

## Current state

- PHASE 0 decision/baseline, PHASE 1 characterization, PHASE 2 skeleton/platform과 PHASE 3
  data compatibility를 완료했다. PHASE 3 최종 검증 결과는 전용 보고서에서 확인한다.
- V2 SQLite repository, bounded DB execution, expand-only ledger와 explicit bootstrap,
  encrypted/legacy restore primitives를 synthetic test와 실제 DB working copy에서 검증했다.
- V1 route, production process, 원본 DB와 Pi에는 연결·변경하지 않았다.
- 현재 단계는 **PHASE 3 완료 / PHASE 4 미진입**이다.

## Next gate

PHASE 4 engagement는 사용자 지시 전 자동 진입하지 않는다. 진입하면 Phase 3 전체 baseline을
재실행하고 profile/ranking, text/voice XP, birthday의 승인된 policy와 guild scope를 application과
Discord adapter에 연결한다. 신규 data 의미 변경이나 기존 사용자 값의 자동 정리는 금지한다.
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
