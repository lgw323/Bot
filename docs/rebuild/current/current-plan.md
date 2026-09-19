# Current Rebuild Plan

Updated: 2026-09-19

## PHASE 10B execution override

**10B 2c LIVE SUMMARY HTTP503 / STOPPED AND VERIFIED. PHASE 10B INCOMPLETE.**
사용자 첨부의 exact push/pin 승인에 따라4 commits/17 blobs 및 docs-only tail을 재검사하고
`686b946439ab5404cf194f8282f4559be245a1ea`까지 일반 FF push/read-back 완료. Main8432fdef… 불변.
새 pin `r-2c768ec98d1fc8b1-3dac82a792fad576`, source2c768ec…/dependency3dac82a…/manifeste201e829… 일치.
시작 전 DB1d871b…/schema5/integrity/config/다섯 preservation 및 전체 protected inventory 불변,
writers/boot/timers 정지·비활성, runtime listeners0, 세 credential scope 및 public9000 경로 재확인 PASS.
기존 Windows837/Pi828+9 intentional skips와 동일 Windows browser9 PASS evidence 유지.
10:55:50.699891Z 시작 → **24.840초/70초 readiness PASS**, Gateway/command sync/동일 release/NRestarts0.
사용자 `/내정보`·`/랭킹`·보관함·볼륨/상태 PASS. 실제 `/요약`1건이6.868612초 뒤HTTP503으로 실패했고,
새 guard가 자동 정지·여섯 번째 새 preservation을 생성했다.72.259초/74 poll records의 부분 관찰이다.
Canonical/copy 최신 DB SHA256 **6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099**,
schema5/integrity/모든 file byte 비교 PASS, 기존 다섯 preservation/config 불변. 이전1d DB로 되돌리지 않는다.
Current pin2c 유지, services inactive/MainPID0, boot/timers disabled/auto-update OFF.
재생 입력3종 무응답은 요약 실패 뒤 사용자 보고다. Music 처리 진입 telemetry0, 개별 요청 시각은 없으므로
정지 영향과 별도 Music 결함을 확정적으로 구분하지 않는다. 새 release의 audible Music/TTS/Watch는 미검증이다.
실제 오류는503이며 무료 일일 quota를 뜻하는429 evidence는 없다. 프로젝트 사용량/제공자 내부 원인·회복 미확인.
정지 후 추가 provider 요청/재시작0, 기존 synthetic HTTP/diagnostic/observer29 PASS. 새 runtime 변경 없음.
Summary 실패를 PASS 처리하지 않으며 actual production backup/restore/boot/timer/완료 후 observation은 미진행.
사용자 지시대로 최신 보고를 남기고 중단한다. Candidate/old DB replay·복원·remigration/V1 시작 금지.
Audit/PHASE11/legacy 삭제 없음. 다음 재개는 최신627082… DB와 모든 보존본을 유지한다.

### Summary 실패와 승인 전 검증 이력

**10B SUMMARY FAILED / STOPPED / VERIFIED RETRY AWAITING PUSH-PIN APPROVAL. PHASE10 INCOMPLETE.**
승인된 d14 source와 docs-only dd5d9aa까지 일반 FF push 후24.821초/70초 readiness를 통과했다.
사용자 `/내정보`·`/랭킹`·`💾 보관함`·볼륨100% PASS, `/요약` FAIL로 즉시 정지·새 보존했다.
Current pin `r-d14eba80bdec9126-3dac82a792fad576`, 최신 canonical/copy DB SHA256
`1d871bed4ba8b8fe4fd9426cfa15c8b373f700baca2f548f5cea571570252363`, schema5/integrity PASS.
새 `phase10-retry-d14eba80bdec9126-live-smoke-guard-preservation`과 기존 네 보존본 모두 유지,
services inactive/MainPID0, boot/backup/update/manual timers disabled, auto-update OFF.
실제 두 Summary 요청은 external_temporary이며 정확한 HTTP status는 당시 기록되지 않았다.
정지 후 합성 provider 요청1회에서503/UNAVAILABLE를 확인했지만 제공자 회복은 미확인이다.
과거 음악 테스트의 버튼 무응답은 SDK HTTP edit 대기 중 callback 등록 공백을 격리 재현·수정했다.
추가한 Summary telemetry/guard는 안전한 오류 분류와 즉시 정지용이며 upstream503의 해결은 아니다.
새 source `2c768ec98d1fc8b1325f88cdfa1558bc6972d551`, Windows exact Git archive full strict837 PASS,
Pi ARM64 full strict828 PASS/9 intentional skips, 같은 Windows Watch9개 PASS, 예상 밖 skip0.
새 비활성 release `r-2c768ec98d1fc8b1-3dac82a792fad576`, manifest17406 files/schema[5,5],
immutable/세 credential scope PASS, 최신 DB/config/다섯 preservation 및 protected state 불변.
새3commits/15blobs secret/artifact 검사 PASS. 원격 dd5d9aa/main8432fdef… 불변.
Workspace 전체 검사의 미추적 gpt_handoff 문서 링크 실패는 별도 기록했고 사용자 파일은 보존했다.
새 runtime push/pin은 아직 승인되지 않았으며 검증된 source2c768ec와 보고-only commit까지의
일반 FF push 및 위 새 release pin을 단일 승인 대상으로 제시한다. Push 직전 최종 range 재검사한다.
이 release에서 남은 Music/TTS 실제 청취와 Chrome public Watch/private admin close까지 모두 PASS해야
actual newest production backup/read-back/independent restore → boot/4h timer → bounded observation을 진행한다.
DB replay/restore/remigration/down-migration/V1 시작 없음. Audit/PHASE11/V1 삭제도 진행하지 않는다.

### TTS 수정 및 승인 전 검증 이력

**10B TTS REPAIRED / VERIFIED RELEASE / PUSH-PIN APPROVAL PENDING. PHASE10 INCOMPLETE.**
사용자가 commands3개, Favorites/volume, Music URL/search/선택/추가/실제 청취/stop·퇴장을 PASS로 확인했다.
이후 봇 입장 안내 없이 음악이 시작된다는 TTS 실패를 보고하여 정지·새 보존을 완료했다.
현재 pin4963982 유지, canonical/copy DB SHA256
`28291bf37128dd62815c818ac45865c8a504cc04a2b3dbb9a8a564d8226dab1d`, 이전 세 preservation 불변.
새 copy는 `phase10-retry-49639828a3c2f181-operator-failed-20260919T092351777156Z`다.
Watch/public browser와 production backup/restore/boot/timer는 미진행. Auto-update OFF.
분석을 계속해 lookup/추가가 idle TTS를 덮는 경쟁 및 TTS 완료 뒤 idle 복귀 결함을 격리 재현·수정했다.
수정 a77f43e + 최신 stopped guard8261076 + 연속 안내 pause 보존d14eba8,
직접 regression8/관련51/최종 Windows full strict821 PASS.
Live에서는 TTS acceptance 뒤0.173711초 만에 Music acceptance가 발생했다.
실제 DiskCache를 사용하는 합성 재현에서도 이전 source의 TTS lease 누수/종료 오류를 확인했고,
수정본은 잔존 lease0/cache close PASS다. Live 종료 오류는 DataIntegrityError category만 확인했다.
새 source `d14eba80bdec912615d9bcc8ba22005b2aec3929`의 Pi ARM64 전체 strict **812 pass/9 skip**,
동일 Windows Watch harness9개 PASS, 예상 밖 skip0. 새 비활성 immutable release
`r-d14eba80bdec9126-3dac82a792fad576`: manifest17403 files/schema[5,5]/세 credential scope PASS.
Current496 pin/최신 canonical DB/config/네 preservation 및 protected state 불변, services stopped,
boot/backup/update/manual timers disabled. 실제 DB schema5/integrity/favorites40 rows/3 owners 유지.
새 runtime은 아직 push/활성화하지 않았다. 원격 branch2e008c3와 main8432fdef… 불변을 재확인했다.
Runtime/guard3 commits와 별도 최종 보고 commit을 포함한 일반 FF push 및 위 pin으로 live 재시도를
한 번의 승인 gate에서 요청한다. 승인 후 최신 DB compatibility/readiness/commands/Favorites/volume/
Music/실제 입장 TTS/Chrome Watch/Cloudflare를 모두 확인하고, 모두 PASS한 뒤에만
actual encrypted backup/remote read-back/isolated restore/boot/4h timer/관찰을 진행한다.
실패하면 정지·새 보존 뒤 분석을 계속한다. 이전 DB replay/restore, V1 시작, down-migration 금지.
Audit/PHASE11/PHASE10 COMPLETE 승인을 요청하지 않는다.

### 승인된496 release live 실행 이력

**10B APPROVED RELEASE LIVE / REQUIRED SMOKE IN PROGRESS. PHASE10 INCOMPLETE.**
사용자 `진행` 승인 뒤 exact `2e008c37936a7077bb9b81e6f280cdc138297d58`까지 기존 branch에
일반 FF push/read-back 완료, main8432fdef… 불변. 최종6 commits/29 blobs secret/artifact scan PASS.
현재 pin은 **`r-49639828a3c2f181-3dac82a792fad576`**이며 최신 canonical DB를 그대로 사용한다.
시작 전 DBfdc1aca…/config/세 preservation inventory 불변 및 schema5/manifest compatibility PASS.
08:43:21.886Z 시작,25.648초/70초 readiness PASS. Discord/Watch active, 같은 release, NRestarts0.
Root fail-fast marker와30분 유한 guard를 켰다. 복원 Music은 실제 acquisition/PCM/Voice acceptance와
정상 playback 종료까지 통과했으며, 사용자가 **실제 청취/보관함 열림/볼륨100% 표시 PASS**를 확인했다.
Commands/새 Music URL·search·추가·stop/TTS/Chrome Watch 순차 smoke가 남아 있고,
그 뒤에만 actual encrypted backup/remote read-back/isolated restore/
boot/4h backup timer/관찰을 수행한다. Auto-update OFF. Audit/PHASE11/V1 삭제는 진행하지 않는다.

### 승인 직전 준비 이력

**10B MEDIA REPAIRED / VERIFIED IMMUTABLE RELEASE / PUSH-PIN APPROVAL PENDING.** PHASE10은 미완료다.
사용자 변경 지시로 정지·보존 뒤에도 분석→격리 재현→수정→strict 검증→immutable release 준비를 이어갔다.
Favorites는 실제 💾 보관함 열림과40 rows/3 owners 보존 evidence에 따라 **PASS**다.
기존 yt-dlp2026.7.4의 media 취득 HTTP403/child exit1을 같은 Pi 환경에서 재현했고,
format 변경과 Deno/EJS 추가만으로는 해결되지 않았다. 2026.8.19로 동일 실패 class의 acquire/PCM/Opus가
통과했다. Runtime-local Deno2.9.7/EJS0.8.0을 봉인하고 remote component download를 금지했다.
Responder Webhook API 계약, 단일 fallback/삭제 작업 ownership을 수정했다. Root marker로 활성화하는
live-smoke first-failure latch는 retry 전에 admission을 닫고 current/queue를 보존한다. 정상3초/8초는 유지한다.

Runtime source `49639828a3c2f181e87a3cfffd5d5f80f47b359a`, 새 비활성 release
`r-49639828a3c2f181-3dac82a792fad576`: Windows813 pass, Pi804 pass/9 intentional Node skips,
동일 Windows Node9 pass, manifest17402 files/schema[5,5]/세 credential scope PASS.
Exact release의 search/public control/기존 실패 class/synthetic TTS 모두 PCM/Opus까지 PASS했다.
이 결과는 실제 Discord 청취와 Chrome Watch를 대체하지 않는다.

Current production pin은368 유지, canonical DB SHA256
`fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f` 및 config/state/cache/audit,
세 실패 preservation은 모두 불변이다. Runtime/staging stopped/MainPID0, boot/timers disabled, listeners0.
일반 FF push와 새 pin/live 재시도에 대한 단일 승인 gate에서 기다린다. 승인 후 현재 newest DB로
readiness70초→commands→Favorites/volume→audible Music/search/stop→TTS→Chrome Watch/Cloudflare를
확인하고, 모두 성공해야 actual encrypted backup/Bot-Data read-back/isolated restore/boot/4h timer/관찰을 진행한다.
실패하면 즉시 stop/preserve하되 Codex는 분석·수정을 계속한다. 새 code activation은 다시 승인받는다.
Candidate replay/old DB restore/down-migration/V1 restart, auto-update는 금지/비활성 유지한다.
Audit0/Audit1–10/Integrated Audit/PHASE11/V1 삭제는 진행하지 않는다.
최신 [PHASE10 보고서](../phases/phase-10/phase-10-report.md)의 첫 절이 우선한다.

아래는 직전 정지 재시도와 PHASE8–10A 준비 단계의 이력이다.
2026-09-19 사용자 최종 승인과 writer 최신성 재확인 후 승인된63c7722/schema5 candidate를
production canonical로 승격했다. 양쪽 실제 서비스는24.827초 내 동일 release ready/live를 통과했다.
사용자가 기존 Cloudflare Watch origin을127.0.0.1:9000으로 변경했고 공개 HTTPS ready를 확인했다.
Engagement/Summary는 사용자 PASS, Music/즐겨찾기/Watch는 실패, TTS는 미검증이다.
05:09:43Z pair를 정상 중지했으며 production backup/restore/timer 활성화는 실행하지 않았다.
현재 상태·실패·실측 시간은 [PHASE10 실행 보고서](../phases/phase-10/phase-10-report.md)의 첫 절이 우선한다.
재시도 조사에서는 current52d DB와 보존본 일치/schema5/favorites40을 확인하고, 현재 writes의 새 암호화
local recovery roundtrip을 통과했다. Dashboard callback 등록, TTS child 경로와 Watch hydration/reconnect
결함을 수정·검증했다. 사용자 요청으로 V1 jukebox 표시를 복원했다.
Windows771 pass와 Pi762 pass/9 intentional Node skips, 세 credential scope/manifest 검증을 통과했다.
사용자가368c8eb push와 새 production pin을 승인했고 exact368까지 일반 fast-forward push를 완료했다.
main은 변경하지 않았다. 새368 release로 기존 canonical을 사용해25.363초/70초 readiness를 통과했고,
사용자 `/내정보`·`/랭킹`·`/요약` PASS와 볼륨100% 표시를 확인했다. 즐겨찾기 버튼 계속 비활성 보고로
06:52:58Z 정지·새 보존본 검증을 완료했다. `⭐`와 `💾 보관함`의 구분 및 live 실패 원인은 미확정이다.
Canonical/new copy DB는fab61b…로 동일하고 기존 failed-attempt52d…는 변경하지 않았다.
Current pin은368을 유지하며 production pair/staging/ops6 services는 inactive/MainPID0,
boot 및 backup/update/manual timers disabled다. Music 실제 음성/TTS/Watch와 off-host backup/restore는
이번 순차 smoke에서 미실행이다.58 samples/330.637초의 내부 health 정상은 기능 통과를 대체하지 않는다.
새 보존본·정확한 hash와 각 gate 결과는 최신 PHASE10 보고서 첫 절을 따른다.
사용자 지시대로 결과를 기록하고 중단하며, 추가 수정·재시작은 이번 실행에 포함하지 않는다.
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
