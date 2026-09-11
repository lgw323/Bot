# Current Rebuild Plan

Updated: 2026-09-11

## Current state

- PHASE 6 기준선 `504 passed, 2 xfailed`를 재확인하고 PHASE 7 Music을 구현했다.
- per-guild MusicActor, bounded media/TTS/FFmpeg/cache, Discord commands/dashboard,
  stable pagination과 legacy-compatible snapshot/restore를 추가했다.
- additive migration 5로 logical session start/count를 idempotent하게 기록한다.
  기존 six-table schema와 migration 1–4 정의, V1 production runtime은 유지했다.
- Music strict xfail 두 개를 실제 V2 actor/UI 경로로 해결했다. 현재 xfail은 0이다.
- 최종 전체 strict test는 **592 passed, 0 xfailed**다. 검증 수치와 focused commits는 [PHASE 7 report](../phases/phase-07/phase-7-report.md)에 기록한다.
- 현재 단계는 **PHASE 7 완료 / PHASE 8 미진입**이다.

## Next gate

PHASE 8 Operations는 사용자 지시 전 자동 진입하지 않는다. 실제 provider/Discord Voice,
권한 배치와 Pi 부하/장시간 soak 검증은 staging/PHASE 9에 남긴다. 수치는 실측 SLO가 아닌
보수적인 hard ceiling이며 Music direct fallback은 명시적 최대 7일 rollback 설정용이다.

Production DB migration/cutover는 PHASE 10의 별도 승인 gate 전까지 금지한다. Raspberry Pi
설치·배포, systemd, auto-update/auto-backup, Watch tunnel, production login과 실제 데이터
사용은 이번 Phase에서 수행하지 않았다. push/PR/deploy도 하지 않았다.

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
