# Current Rebuild Plan

Updated: 2026-09-19

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
- PHASE 9 로컬·synthetic staging을 완료했고 사용자 지시로 **PHASE 10A production readiness**를 시작했다.
  최신 진행 상태는 [PHASE 10 report](../phases/phase-10/phase-10-report.md), 과거 staging 증거는
  [PHASE 9 report](../phases/phase-09/phase-9-report.md)를 따른다.

## Next gate

PHASE 9는 사용자 지시로 시작했다. 기존 SSH와 사용자 직접 interactive sudo를 사용하며 synthetic
DB만 허용한다. ARM64 wheel과 Linux 파일시스템 테스트는 통과했고, 실제 systemd 서비스 검증에서
발견한 권한 문제를 수정해 실제 배포, 로컬 readiness, lifecycle, encrypted backup/isolated restore와
controlled smoke 실패 후 rollback을 검증했다. 전체 strict는 688 passed, 0 xfailed다.
synthetic DB 승격, host reboot 복구, actual split-version 거부, manual inbox, namespace/polkit과
bounded load/soak도 검증했다. 4시간 backup timer와 로컬 staging 두 서비스만 부팅 활성화했다.
staging Discord/Gemini credential과 guild/channel/origin이
없으므로 실제 외부 login/smoke는 보류한다. 기존 PC `.env`는 사용하지 않는다.

PHASE 10A에서 사용자 확인을 받은 최신 preservation DB의 별도 copy에만 migration 1–5를 적용했다.
실제 schema 0/5 encrypted backup 및 isolated restore와 old-reader/semantic 검증이 통과했다.
원본은 보존했고 Pi canonical은 synthetic이다. `.env`는 사용하지 않는다.
한국어 single-command setup으로 사용자 직접 입력을 완료했고, 세 서비스의 no-network credential mount/
owner/mode/basic config 검증이 통과했다. commit `672694d`의 ARM64 immutable 후보 release도 별도
build/operations strict/manifest 검증을 통과했다. current는 이전 synthetic release를 유지한다.
Watch origin은 `https://watch.lgw323.com`; DNS/route 생성은 아직 승인·실행하지 않았다.
Pi candidate decrypt/재backup/재restore/runtime UID open-close도 통과했다. 첫 observer의 실제 24h/1,438개
samples를 회수했고 restart/RPO 초과는 0이었다. DB probe 실패 +12/+17, health 누락 1회와 약 0.96GB
disk free 감소에 주기 작업의 과도한 정상 lifecycle journal이 기여함을 확인했다. throttling 1,438개 표본은
모두 0, health 누락은 HTTPError 1회였으며 DB 실패 상세 원인은 미확정이다.
off-host는 private Bot-Data/db-backup과 별도 write deploy key로 실제 upload/download/restore를 통과했다.
`d54ff36`의 ARM64 build/격리 runtime backup 검증도 PASS다. 사용자 승인 후 전체 Git ancestry의 비밀값/파일
검사를 거쳐 2026-09-19 exact commit을 origin/codex/rebuild-v2로 일반 push했다. main은 동일하다.
초기 production pin은 d54ff36, 자동 update는 비활성화하며 이후 commit은 수동 승인한다.
후속 로컬 수정은 주기 작업의 정상 journal을 줄이고 DB 실패의 safe error code를 추가한다.
수정본 Pi 검증·재관찰 및 pin 변경 승인은 별도다. V1 music_state는 없어 active queue/voice 위치는 미이전이다.
관찰 이상 검토와 최종 release/config/rollback sheet를 마친 뒤
[cutover runbook](../phases/phase-10/cutover-runbook.md)의
준비 항목을 끝내고 명시적 최종 승인을 받은 뒤에만 10B DB promotion/login/production timer를 실행한다.
PHASE 11 V1 제거는 별도 지시 전 시작하지 않는다.

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
- [PHASE 9 report](../phases/phase-09/phase-9-report.md)

## Active phase

- [PHASE 10A report](../phases/phase-10/phase-10-report.md)
- [Production migration contract](../phases/phase-10/production-migration-contract.md)
- [한 번 실행하는 config setup](../phases/phase-10/config-migration-guide.md)
- [Cutover gate/runbook](../phases/phase-10/cutover-runbook.md)
