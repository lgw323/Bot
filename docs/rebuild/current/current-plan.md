# Current Rebuild Plan

Updated: 2026-09-19

## PHASE 10B execution override

**10B FAILED LIVE SMOKE / SERVICES STOPPED.** 아래 PHASE8–10A 기록은 준비 단계의 이력이다.
2026-09-19 사용자 최종 승인과 writer 최신성 재확인 후 승인된63c7722/schema5 candidate를
production canonical로 승격했다. 양쪽 실제 서비스는24.827초 내 동일 release ready/live를 통과했다.
사용자가 기존 Cloudflare Watch origin을127.0.0.1:9000으로 변경했고 공개 HTTPS ready를 확인했다.
Engagement/Summary는 사용자 PASS, Music/즐겨찾기/Watch는 실패, TTS는 미검증이다.
05:09:43Z pair를 정상 중지했으며 production backup/restore/timer 활성화는 실행하지 않았다.
현재 상태·실패·실측 시간은 [PHASE10 실행 보고서](../phases/phase-10/phase-10-report.md)의 첫 절이 우선한다.
재시도 조사에서는 current52d DB와 보존본 일치/schema5/favorites40을 확인하고, 현재 writes의 새 암호화
local recovery roundtrip을 통과했다. Dashboard callback 등록, TTS child 경로와 Watch hydration/reconnect
결함을 수정·검증 중이다. 사용자 요청으로 V1 jukebox 표시를 복원한다. 새 source의 Pi build와
push/production pin 별도 승인, 실제 smoke/off-host backup/timer/관찰은 아직 남아 있다.
10B 완료가 아니며 auto-update/manual polling은 비활성화 유지한다. Audit0/PHASE11은 별도 지시 전 금지다.

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
build/operations strict/manifest 검증을 통과했다. 당시 current는 이전 synthetic release였으며 아래 후속 검증에서63으로 적용했다.
Watch origin은 `https://watch.lgw323.com`; DNS/route 생성은 아직 승인·실행하지 않았다.
Pi candidate decrypt/재backup/재restore/runtime UID open-close도 통과했다. 첫 observer의 실제 24h/1,438개
samples를 회수했고 restart/RPO 초과는 0이었다. DB probe 실패 +12/+17, health 누락 1회와 약 0.96GB
disk free 감소에 주기 작업의 과도한 정상 lifecycle journal이 기여함을 확인했다. throttling 1,438개 표본은
모두 0, health 누락은 HTTPError 1회였으며 DB 실패 상세 원인은 미확정이다.
off-host는 private Bot-Data/db-backup과 별도 write deploy key로 실제 upload/download/restore를 통과했다.
`d54ff36`의 ARM64 build/격리 runtime backup 검증도 PASS다. 사용자 승인 후 전체 Git ancestry의 비밀값/파일
검사를 거쳐 2026-09-19 exact commit을 origin/codex/rebuild-v2로 일반 push했다. main은 동일하다.
후속 사용자 승인으로 초기 production pin을 `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`으로 갱신했다.
직전 전체 이력/파일/내용/commit 메시지를 재검사하고 해당 commit까지만 일반 fast-forward push했다.
자동 update는 계속 비활성화하며 이후 commit은 수동 승인한다.
수정본63을 실제 synthetic pair에 적용해300.171초/31 samples 관찰을 완료했다. 양쪽 같은release,
ready/live, restart0과 정상 주기 journal0을 확인했고 별도 Pi fault worker에서 실패 로그/코드를 검증했다.
과거24h 장애의 상세 원인은 미확정으로 공개하고 stop/reconciliation 기준을 고정했다.
실제 connector 현재 route는 watch.lgw323.com → localhost:8000이며 변경하지 않았다.
별도 production install config 준비와 [exact 명령표](../phases/phase-10/final-command-sheet.md)를 완료했다.
최종 상태는 **10A COMPLETE / 10B NOT AUTHORIZED**다. 다음 gate는 사용자 최종 cutover 승인이다.
승인 전 production promotion/login/timer/route 변경은 실행하지 않는다. V1 music_state는 없어 queue/voice 위치는 미이전이다.
PHASE11 V1 제거는 별도 지시 전 시작하지 않는다.

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

- [PHASE 10 report — 10A COMPLETE / 10B live 실패·정지](../phases/phase-10/phase-10-report.md)
- [Production migration contract](../phases/phase-10/production-migration-contract.md)
- [한 번 실행하는 config setup](../phases/phase-10/config-migration-guide.md)
- [Cutover gate/runbook](../phases/phase-10/cutover-runbook.md)
