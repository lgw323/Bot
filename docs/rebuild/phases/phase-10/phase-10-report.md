# PHASE 10 Report — Production Cutover

## PHASE 10B result — FAILED LIVE SMOKE / SERVICES STOPPED

2026-09-19 사용자 명시적 승인으로10B를 실행했으나 실제 Music/Watch smoke가 실패했다.
**PHASE 10 INCOMPLETE / 10B FAILED LIVE SMOKE**다. 두 production 서비스는05:09:43Z 정상 중지됐다.
아래10A 완료 보고는 승인 전 증거로 보존하며, 현재 실행 상태는 이 절을 우선한다.

### Actual live results and remaining gate

| 검증 대상 | 실제 결과 |
| --- | --- |
| Discord Gateway / command sync | 양쪽 ready 통과. Discord ready 조건에 Gateway ready 및 완료된 command sync 포함. 아래 실제 명령 응답도 사용자 확인 |
| Engagement | 사용자 `/내정보`·`/랭킹` PASS |
| Summary / Gemini | 사용자 최소 범위 `/요약` PASS |
| Music / Voice / provider | **FAIL**: 노래 추가 후 계속 로딩되다가 종료됨. 정상 재생·정지·voice lifecycle은 미확인 |
| Favorites / volume | **FAIL**: 기존 즐겨찾기 조회 불가. 데이터 소실 여부나 원인은 미확정; volume 별도 결과 미확인 |
| TTS | Music 실패로 사용자가 건너뜀. **NOT TESTED** |
| Watch / public HTTPS-WSS | HTTPS/health 및 route는 PASS. **기능 FAIL**: 새로고침 문제, 실시간 사용자 표시 누락, YouTube 탭에서 돌아오면 연결 끊김. WSS 전체 정상·동기화 PASS로 간주하지 않음 |
| Watch private admin | 사용자 세션 강제종료 성공 확인. 나머지 초대/정리 전체 경로는 미확정 |
| Birthday | production start에서 scheduler 연결 코드 경로 확인. 독립 scheduler readiness 측정 미확정; 테스트 생일/XP 삽입 없음 |
| Production backup / off-host / isolated restore | 주요 live smoke 실패로 **NOT RUN**.10A 복구 증거는 보존하되 이번 실제 writes의 백업 성공으로 대체하지 않음 |
| Timer / boot | 이번 production boot enable/backup timer 활성화 **NOT RUN**, update/manual/backup timer inactive 유지 |
| Final Audit gate | Audit0–10/통합 Audit 및 PHASE11 **NOT STARTED**. V1/env/원본/backup/release/history 삭제 없음 |

Failure matrix에 따라05:09:42Z 감시를 먼저 중지하고 두 서비스를 정지했다.05:09:43Z 관련6개 service의
MainPID0/ActiveState inactive/Result success, 두 production unit NRestarts0을 확인했다.
05:11:16Z operation lock 아래 latest data/state/cache/backups/config/audit 전체를
`/var/lib/discordbot/phase10-precutover-63c7722/failed-attempt/`에 보존했다(root:root0700).
Canonical과 preserved DB SHA256은 모두 `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af`다.
Graceful stop 후 WAL/SHM은 없었으며 agent가 삭제하지 않았다. Canonical은 그대로 남겨 두었다.
Candidate8d17018f…와 hash가 달라졌으므로 startup/smoke 이후 writes를 보존해야 한다.
보존본 자체의 추가 integrity/application 검사와 변경 의미 분석은 아직 하지 않았다.
보존 시 production backup directory는 첫 backup 전 상태이며 이번 writes를 담은 off-host 복구본은 없다.
기능 실패의 원인은 아직 확정하지 않았다. 안전한 journal 분류에서는 Watch 단발 database_unavailable1회 외
원인을 결정할 예외 종류/코드 위치를 확보하지 못했다. 오류 문구를 삼키는 UI 경로가 있어 로그 부재는 정상 증거가 아니다.
원본 candidate 자동 replay, schema down-migration, V1 시작, synthetic fallback, 운영 code 교체는 실행하지 않았다.
Cloudflare origin은 사용자가 변경한9000 그대로이며 두 서비스 정지로 public Watch는 현재 서비스되지 않는다.
새 운영 commit을 적용하려면 수정·검증 후 exact commit/release에 대한 별도 승인이 필요하다.

### Maintenance timeline and bounded observation

- Maintenance start04:44:21Z → first ready04:55:24.770327Z: **11분3.770초**.
- First full successful live smoke: **없음**. Maintenance success end: **없음**.
- 실패 후 안전 정지05:09:43Z까지 작업 구간: **25분22초**. 실제 운영 성공 downtime으로 보고하지 않는다.
  V1은 이 작업 이전부터 정지했으므로 기존 V1 중단 시간까지 측정한 수치가 아니다.
- 관찰04:59:45.637128Z–05:09:40.185469Z, **594.548초/114 samples**, 모든 표본 ready, unexpected restart0.
  계획600초를 채우기 전에 실제 기능 실패 때문에 operator가 observer를 중지했다.
  Summary JSON의 `observing`은 마지막 sample 상태이며 현재 worker가 실행 중이라는 뜻이 아니다.
- Discord RSS82,148–85,736KiB/FD9–15/threads6–9, Watch RSS68,624–70,224KiB/FD9–13/threads4–5.
  실사용 부하가 섞인 짧은 관찰이며 증가만으로 누수 여부를 확정하지 않는다.
- 온도55.65–60.05°C, throttling samples0, disk free delta-692,224bytes.
  Watch probe failed1→1/Discord0→0; 최초 Watch 오류는 관찰 시작 전04:59:35Z였다.
  resource/ready 통과가 사용자 기능 성공을 보장하지 않았으며 post-cutover 안정성 PASS로 사용하지 않는다.

### Execution and preservation evidence

- Repository 문서/계약/Git 재확인: HEAD `53c79e7`, 시작 worktree clean. 운영 pin은63c7722 그대로다.
- Writer 최종 확인: 사용자가 이후에도 V1 실행 없고 보존본이 최신이며 다른 token owner 없음을 재확인했다.
  PC Python process0, Pi는 문서의 synthetic PID43017/43018 외 새로운 bot writer가 없었다.
- 04:39:45Z precheck PASS: authoritative 원본 hash, Pi candidate hash, source/prepared/staging config hash,
  기존 Pi encrypted recovery artifact hash,63c7722 release manifest/commit/schema identity 일치.
  source 원본은 hash만 확인했으며 SQLite로 열지 않았다.
- 단계별 실행: exact 명령표의 한 block씩 별도 SSH 명령으로 실행/검증한다. 전체 cutover 자동 실행 도구는 만들지 않는다.
  사전 검사 evidence는 `/var/tmp/phase10b-00-precheck.txt` (`step_exit=0`).
- **실제 production DB 승격 및 Discord/Watch 첫 시작 완료.** 아래 단계는 각각 결과를 확인한 뒤 다음 단계를 실행했다.
- Maintenance 시작 **2026-09-19T04:44:21Z**, 전체 관련 서비스 중지 확인04:44:23Z.
  Update/manual/backup timer와 synthetic peer는 중지·비활성화했다.
- 04:45:20Z synthetic data/state/cache/backups/config/marker 보존 완료:
  `/var/lib/discordbot/phase10-precutover-63c7722` (root:root2700,04:48:07Z에0700 확정).
  두 mode 모두 root 외 접근 금지다. Audit/operation lock 보존, WAL/SHM 삭제 없음.
- 04:48:07Z production config digest `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`
  설치 및5개 secret·전용 backup SSH credential·backup drop-in 설치 완료. Source candidate는 그대로 보존했다.
  Config root:discordbot0640, secret source root:root0600/부모0700, systemd-analyze verify PASS.
- 04:49:01Z Discord/Watch/Operations의 설치 경로 scoped preflight3개 PASS. 네트워크 login/DB open 없이
  형식·정확한 mount 이름·readonly mount 확인. Runtime/operations UID의 unmounted source 접근 거부 확인.
- 04:51:22Z exact63 stopped activation PASS, 모든 writer 정지 유지.
- 04:52:32Z 승인된 candidate → canonical `/var/lib/discordbot/data/bot_database.db` promotion PASS.
  직후 SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`, schema5와
  runtime UID readonly application validation PASS. Staging marker는 private preservation으로 옮겼다.
- First start **04:54:59.943605Z**, both ready/live **04:55:24.770327Z** (**24.827초**,70초 내).
  Exact release `r-63c77229d1a6e76a-d026a47ed4f4b38a`, Discord PID47277/Watch PID47279, NRestarts0.
  단계 전용 guard가70초 deadline과 restart/identity를 검사했으며 전체 전환 자동화는 아니다.
  Production startup부터 실제 writes/Discord 외부 효과가 발생할 수 있으므로 원본 candidate 자동 replay 금지.
- Cloudflare는 **사용자가 직접 변경 완료**를 확인했다. Connector의 최신 config event에서도
  기존 `watch.lgw323.com` route1개 → `http://127.0.0.1:9000`, internal9001/9010/9011 route0 확인.
  공개 HTTPS TLS 검증0(성공), HTTP200, `/health/ready`의 `ready=true` 확인.
  Pi listener9000/9001/9010/9011은 모두127.0.0.1이었다. 이후 실제 Watch 기능 실패로 서비스를 중지했다.
- 사용자 live smoke 결과는 위 표에 기록했다. Music/Watch 실패로 후속 성공 절차를 중단했다.
- 04:59:45.637128Z부터10분 한정 maintenance 감시 시작. 실제 production 서비스 재시작/identity 불일치는 즉시,
 5초 간격3회 연속 ready 실패는 pair stop. 이 감시는 post-cutover 완료 후 관찰을 대체하지 않는다.
- 04:59:35.433430Z Watch `database.probe_failed` / `database_unavailable`1회 기록. 후속 ready 회복,
  05:01:15Z까지18 samples/ready failure0. SQLite busy/I/O 등 원인은 미확정이며 corruption으로 단정하지 않는다.
- **Production backup / off-host publication / isolated restore / boot enable / backup timer는 아직 NOT RUN.**
  최초 production backup 전 backup_age=-1은 예상 초기값이며 RPO PASS 증거가 아니다.
- 성공한 maintenance end/full live smoke completion은 없다. V1의 기존 정지 기간과 이번 전환 시간은 구분한다.
- 실행 중 오류2개는 production 설치 전 해결했다: (1) Windows CRLF로 `set -euo pipefail` 실패;
  shell2행에서 종료되어 side effect 없음을 확인하고 LF 전송으로 수정. (2) preservation 부모의 setgid 상속으로
  mode2700 검사 실패; 설치 전 정지, 별도 빈 경로에서 GNU chmod 동작 확인 후 `chmod g-s`로0700 확정했다.
  실패 결과를 성공으로 덮어쓰지 않고 `03-install` 실패와 `03b-install` 성공을 별도 보존했다.
- Evidence: Pi `/var/tmp/phase10b-00-precheck.txt`~`phase10b-07-start.txt` 단계별 결과,
  `phase10b-start-gate-result.json`, `phase10b-live-monitor/`의 allowlisted 측정치. Secret/DB 내용/raw log는 보고하지 않는다.
  실패 중지/보존은 `phase10b-09-failure-stop.txt`, `phase10b-10-preserve-failure.txt` (`step_exit=0`).
- V1/source/env/schema0 원본/기존 encrypted backups/releases/history 보존. 운영 code pin 변경·새 push 없음.
- 명령표의 LF 전송/보존권한 교정은 local docs commit `bca8df9`로 기록했다. Runtime/source63은 변경하지 않았다.
- 이번 tracked 변경은 운영 결과 문서다. Staged diff/whitespace 검사를 수행했고 application 전체 test는
  다시 실행하지 않았다. 실제 DB를 test fixture로 사용하지 않았다. 이전10A의746 passed 증거는 아래에 보존한다.
- 사용자에게 즐겨찾기의 정확한 응답 유형, 음악 입력 방식, Watch 기기/브라우저를 요청했다.
  이 정보와 격리 재현으로 원인을 좁혀야 하며 UI 실패를 token/Cloudflare/데이터 손실로 추측하지 않는다.
- 종료 후 별도 Final Audit(Audit0–10 및 통합 Audit) 지시를 기다린다. Audit0/PHASE11 자동 시작 금지.

## Preserved PHASE 10A completion evidence

Updated: 2026-09-19. **10A COMPLETE / 10B NOT AUTHORIZED.**
준비 단계의 완료이며 PHASE 10 전체 완료나 production 성공을 뜻하지 않는다.
Production canonical promotion/login/service start/public route 변경/production backup timer는 실행하지 않았다.

## Phase 10A Status

| 최종 승인 자료 | 판정 / identity / 한계 |
| --- | --- |
| Authoritative DB source | PC `docs/rebuild/bot_database.db`; 최신성 사용자 확인. SHA256 `4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25` 재확인, 원본 SQLite open 없음 |
| Candidate DB | Pi `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`; SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b` 재확인. schema5/semantic/count/복구 PASS 증거 재사용, 재migration 없음 |
| Approved source/release | commit `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`, release `r-63c77229d1a6e76a-d026a47ed4f4b38a`; ARM64 build PASS. 해당 commit까지 일반 FF push 완료, main 보존 |
| Config/secrets | 기존 production-candidate와 세 credential scope 검증 유지. 새 별도 설치 준비 config digest `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`; exact 경로·권한·mount·보존 순서 확정. 현재 staging config 불변 |
| Corrected staging observation | 실제 synthetic pair에63 적용, **300.171초/31 samples**, 같은 release, live/ready PASS, NRestarts 증가0. 정상 주기 lifecycle journal0; failure/cancel/deadline/retry와 probe stable code 보존을 별도 Pi fault worker로 확인 |
| DB probe/health anomaly classification | 기존24h +12/+17, HTTPError1의 원인/status 소급 미확정. 새 `database_unavailable` 분류는 주입 증거이며 과거 원인을 뜻하지 않음. 손상 증거 없음, readiness/rollback trigger 아래 명시 |
| Watch tunnel | 실행 중 connector의 최신 config event에서 `watch.lgw323.com → http://localhost:8000` 확인. ingress2개, 내부9001/9010/9011 route0. 10B에서 기존 route origin만 `http://127.0.0.1:9000`으로 변경 |
| Off-host readiness | private Bot-Data 전용 SSH key, 실제 encrypted upload/download/decrypt 및 d54 runtime drill PASS 유지. 설치/drop-in/timer/retention/실패 정책 확정. 지속 production RPO·Git 총용량은 미측정 |
| Exact activation/promotion/rollback sheet | [최종 명령표](final-command-sheet.md) 준비 완료. 실제 release/DB/config hash, operation lock, 보존·설치·승격·first start와 단계별 실패 절차 고정, 입력 placeholder 없음 |
| Downtime plan | 승인 뒤30–60분 예상(실측 아님). Codex 단계별 실행, 사용자 직접sudo 및 Discord/browser smoke 확인. V1은 기존 확인상 이미 정지 상태 |
| Live smoke effects | command sync/dashboard/생일 due 알림 가능. `/내정보`, `/랭킹`, `/요약`, Music1곡, TTS, Watch create/connect/close, 실제 production backup/isolated restore는10B에서만 실행 |
| Remaining risks | 실제 token/guild/channel 권한·provider 부하 미검증, 과거 transient 원인 불명, short observation 한계, V1 music_state 부재, 새 V2 writes 이후 원본 복구 시 데이터 손실 판단 필요, Git history 증가 |
| Production / PHASE11 | **NOT AUTHORIZED / NOT RUN**. auto-update/manual timer 비활성화 유지. V1/env/history/backup 삭제 없음 |

## Corrected-release Actual Pi Observation

증거: `/var/tmp/phase10-corrected-63c7722/progress.json` stage `complete`, 같은 디렉터리 samples/summary.
PC ignored 보존본 `scratch/phase10/corrected-release-result.json`, `corrected-release-samples.jsonl`.
prebuilt63을 기존 synthetic pair에 적용했으며 production credential/DB/login을 사용하지 않았다.
작업 중 synthetic backup timer만 일시 정지 후 원래 active 상태로 복원했다. Update/manual은 계속inactive다.
관찰 UTC **2026-09-19 04:08:13.576–04:13:13.584**, observer elapsed **300.171초**.
service restart 전후 PID 변경은 명시적 release 적용 때문이며 관찰 중 PID43017/43018은 일정했다.

| 실제 측정 | Synthetic Discord | Watch |
| --- | --- | --- |
| Health | 9010, 31/31 ready, HTTP errors0 | 9011, 31/31 ready, HTTP errors0 |
| Release | r-63c77229d1a6e76a-d026a47ed4f4b38a | 동일 |
| NRestarts | 0→0 | 0→0 |
| RSS KiB 범위 | 52,524–52,660 | 68,276–68,584 |
| FD / threads | 7 / 2→3 | 9 / 3→4 |
| DB probe | 관찰 종료까지60 ok, failed0 | 관찰 종료까지60 ok, failed0 |
| 관찰 구간 journal entries | 2 | 2 |
| 3개 주기 task 정상 started/succeeded | 0 | 0 |

관찰 전후 `Services.smoke`의 ready/live pair 검증과 synthetic canonical schema/application validation PASS.
31개 sample 모두 ready이나10초 표본 사이 무중단을 입증하지는 않는다. 자원 범위에는 첫 probe/executor
thread 생성이 포함된다. 이전24h의 각 service 약379,000 journal entries와 달리 정상 주기 로그가 사라졌다.
global journal 사용량은 양쪽 모두 도구 표시 **3.2G**(반올림)였고 실제 journal byte 증가0을 뜻하지 않는다.
관찰+후속 점검/fault worker 구간 disk free delta **-118,784 bytes**; sample 첫/끝 차이는-110,592 bytes.
global disk 차이를 journal에만 귀속하지 않는다. 온도56.2–68.85°C, throttling samples 모두0.
첫 sample만 양쪽 backup_age=-1/RPO gauge1이었다. 코드상 최초5초 probe 전 초기값이며 이후30개는
age 정상/RPO gauge0, 마지막age 약773초였다. 이5분은 새 scheduled backup 실행/RPO 지속 증거가 아니다.

별도 transient `discordbot-phase10-telemetry-fault.service`는 approved63의 실제 TaskSupervisor/Probe를
사용하되 fake DB dependency와 PrivateNetwork로 실제 DB/API/secret에 접근하지 않았다.
실제 journal에 `task.failed`, `task.cancelled`, `task.deadline_exceeded`, `task.retrying`,
`database.probe_failed` 각1회와 **`database_unavailable`**1회를 확인했다. 주입 후 readiness false도
worker assertion을 통과했다. 자연 발생 장애를 재현하거나 기존24h 실패의 원인을 확정한 증거가 아니다.

## Anomaly Classification and Cutover Triggers

| 항목 | 확인된 category / readiness / 손상 evidence | 10B 처리 기준 |
| --- | --- | --- |
| 기존 synthetic probe +12 | probe read 실패 집계만 있음; 당시 stable code 없음. 수집된 ready false0이나 사이 순간 저하 가능 | 신규 failure 시 code/time/health status 기록. 단발은 제한 재확인;5초 간격3회 연속 ready false/error면 pair stop·조사 |
| 기존 Watch probe +17 | 위와 동일. SQLite busy/I/O/deadline 중 하나로 추측하지 않음 | 동일 기준. data_integrity나 schema/digest 이상은 즉시 stop/reconcile |
| 9010 HTTPError1 | HTTPError category 확정, status 미저장.503이라고 단정 불가. 해당 ready payload 미수집 | status와 양쪽 live/ready를 제한 확인;70초 startup gate 초과 또는 maintenance 중 예상 밖 restart면 stop |
| 신규 injected probe | database_unavailable + ready false. 구체적인 SQLite busy 대 I/O 구분은 이 code로 불가능 | error message/SQL/사용자 값 없이 code만 기록. 원인조사는 별도 안전한 진단으로 진행 |

기존 migration/restore/schema/integrity 검증과 이번 synthetic validation에 데이터 손상 증거는 없었다.
과거 모든 transient가 무해했다는 뜻은 아니다. 첫 검증 backup 이후 age<=6h, remote publication 실패,
identity split, audit/fsync uncertainty, writer 충돌을 성공 선언 중단/복구 검토 trigger로 둔다.
세부 [monitoring 및 rollback 절차](final-command-sheet.md#7-monitoring-stop-triggers)를 따른다.

## Final Config / Route / Installation Evidence

`prepare_install_sheet.py`를 Pi에서 interactive sudo로 실행해 **별도 준비 경로만** 생성했다.
`/var/tmp/phase10-install-sheet-result.json` stage `prepared_not_installed`, production_activated=false.
원본 user-entered config digest는 `5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3`,
새 준비 config는 `/var/lib/discordbot/phase10-install-plan-63c7722/config.json`이다. 변경은 검증된
backup_remote opt-in object 하나이며 최종 digest는 위 표와 같다.5개 secret 및 SSH2개 source는
root-owned regular/nonempty/0600 검사를 통과했다. 값은 출력·기록하지 않았다. 기존 scoped offline 검증을
반복하지 않았으며10B 실제 목적지 설치 뒤 다시 scope preflight를 수행한다.
PC authoritative hash와 Pi verified candidate hash는 그대로다. 새로운 source/writer는 보고되지 않았다.

Cloudflare read-only helper는 **현재 cloudflared InvocationID**의 마지막 config update event만 읽었다.
event_time_unix_us `1789357096890474`, matching hostname1/ingress2/internal port route0;
현재 origin은 `http://localhost:8000`이다. dashboard/API를 독립 검증했다는 뜻은 아니며10B 편집 직전에
대상을 다시 확인한다. DNS/route/connector는 변경하지 않았다. 설정의 token/다른 hostname/raw 로그는 출력하지 않았다.

## Implemented / Validation / Approval Boundary

추가 도구는 synthetic bounded observation, allowlisted connector route 조회, 별도 설치 config 준비에 한정한다.
기존 immutable63 runtime/DB schema/dependency는 변경하지 않았다. Windows 전체 strict 결과는 아래 최종 기록을 따른다.
직접 guard/config/문서 검증 **13 passed**. 최종 전체 strict **746 passed, 0 xfailed, 60.71초**이며
기존 audioop deprecation warning1개다. 작성 중 문서 anchor 오류1개를 수정한 뒤 전체 검사를 다시 통과했다.
실제 사용자 DB/API/systemd에 접근하는 pytest는 없다.
Pi63 ARM64 build/운영 tests/manifest/세 scope 검증은 기존 **138.196초 PASS** evidence를 유지한다.
off-host actual upload/download/decrypt를 불필요하게 반복하지 않았다. 이번 로컬 commits는 push하지 않는다.

실행 순서는 [최종 명령표](final-command-sheet.md), 기능 smoke/배경은 [runbook](cutover-runbook.md),
데이터 identity는 [migration contract](production-migration-contract.md), 입력 가이드는
[config guide](config-migration-guide.md)를 따른다. 과거 증거는 아래에 보존하며 최신 판정은 이 요약을 따른다.

## Baseline / Production Source Data

Repository branch `codex/rebuild-v2`, 시작 HEAD `4692caa`. PHASE 3/8/9 계약과 current plan/trace/decisions,
deploy runbooks 및 migration registry를 재구성했다. 시작 시 worktree clean. Windows baseline strict
**688 passed, 0 xfailed**를 재실행했다. 원본 DB/real network를 사용하는 테스트는 없다.
operator가 “이후 V1 실행 없음, 보존본이 최신”이라고 확인하여 `docs/rebuild/bot_database.db`를 authoritative
source로 확정했다. `.env`를 읽거나 복사하지 않았다.

## Original Preservation / Migration / Data Compatibility

[Production migration contract](production-migration-contract.md)에 source/candidate/restored SHA256,
ledger 1–5 checksums, counts, semantic/V1 reader 증거를 기록했다. source 65,536 bytes의 before/after hash
동일. candidate 143,360 bytes, schema 5, integrity/repeat/semantic/old-reader PASS.
six-table counts: users 15, favorites 40, music_settings 1, music_play_counts 50, Watch 양쪽 0.
PII/content row를 보고서에 저장하지 않았다. 실제 Watch nonempty 검증은 synthetic 증거만 있다.
원본은 hash/byte-copy만 했으며 SQLite는 새 working copy만 받았다. migration candidate는 PC isolated
path에 보존되어 있고 Pi canonical은 교체하지 않았다.

## Backup / Restore Evidence

PC `scratch/phase10/candidate-20260915-01/` 아래 실제 candidate encrypted backup과 independent
isolated restore PASS. Identity `20260915T015843161244-45854a29b85740c9b605da6163980095`.
source schema 0의 separate working copy도 `preservation-recovery/pre-migration.enc`로 암호화하고
별도 restore하여 counts/data/metadata/version 일치를 검증했다. backup identity/digests/복구 파일 위치는
migration contract에 있다. Windows private 계정 ACL 차이 때문에 첫 recovery가 파일 열기 전에 실패했고,
후보 경로에 operator의 최소 접근만 추가한 뒤 성공했다. secret 권한을 일반 사용자에게 열지 않았다.

사용자가 hidden prompt로 기존 DB key를 직접 입력했다. key ID `production-key-1`, 값 출력 없음.
key path `scratch/phase10/credentials/db_key`는 operator private ACL이며 Git ignored다.
schema 5 복구는 decrypt, checksum, schema, semantic, application isolated open/close를 모두 통과했다.
PC 검증 reference release는 `r-0376f14868461d16-d026a47ed4f4b38a`다. 아래의 새 ARM64 후보 release도
별도 빌드했지만 production으로 activate하지 않았다.
Pi에서도 사용자 입력 key의 scoped mount로 approved artifact 복구, 새 암호화 backup/재복구와 runtime UID
open/close를 통과했다. 증거는 `/home/os/discordbot-phase10/recovery-progress.json`, stage
`verified_not_promoted`다. 격리 후보는 `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`다.
schema 5와 위 six-table counts, data/metadata semantic reconciliation PASS. 새 Pi backup identity는
`20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71`이며 digests는 migration contract에 기록했다.
candidate digest/current pointer/canonical inode 보존 검사를 통과했고 production promotion/login은 없었다.
worker의 0.304초는 격리 복구·재백업 작업 시간이며 end-to-end 운영 RTO가 아니다.
이 rehearsal은 production canonical timer나 자동 off-host 복구 검증을 대체하지 않는다.

## Config / Secrets / Security

[직접 입력 가이드](config-migration-guide.md), invalid-placeholder template, hidden double-entry tool,
network/DB startup 없는 scoped preflight를 추가했다. V1 template의 모든 변수에 destination 또는
직접 매핑 없음/현재 typed default를 표시했다. Summary retention 등 기존 Phase 구현과 V1 template 차이,
raw Discord log/admin UI 미연결도 숨기지 않았다. production placeholder를 config/secret 단계에서 거부하는
guard와 regression을 추가했다. valid-looking 값의 실존/권한/API 인증은 live gate다.

사용자 요청에 따라 파일별 편집 대신 한 번 실행하는 한국어 `setup-production.py`를 추가했다.
세 기존 secret은 숨김 두 번 입력, 다섯 ID와 origin은 한국어 안내, Watch control/capability는 안전한
독립 무작위 키 자동 생성이다. 후보 생성/owner/mode/기본 validation을 수행하고 기존 후보/staging을
덮어쓰지 않는다. echoed getpass fallback과 noninteractive 실행을 거부한다. **사용자 직접 입력 완료 확인**을 받았다.
Pi `/home/os/discordbot-phase10/`에 wizard/config template/enter_secret/preflight를 전달했다.
Pi 임시 synthetic 디렉터리에서 owner/mode, exclusive-create, staging sentinel 보존을 실제 검증했다.
현재 `/etc/discordbot/config.json` 및 staging credentials는 그대로다. 새 release로 production candidate의
필수 config/ID/secret basic format, root-owned source files/modes와 실제 세 systemd credential mount 검증이
통과했다. 모든 probe는 PrivateNetwork=yes로 실행했고 DB와 실제 API login을 시작하지 않았다.
Discord: discord_token/gemini_key/control_key; Watch: capability_key/control_key; Operations: db_key.
모든 mount는 정확한 이름 목록, read-only, root:root 0440 + 기존 loader가 검증하는 service UID ACL이었다.
Discord/Watch UID 999, Operations UID 997. 모든 서비스에서 원본 secret 경로 직접 접근은 거부됐다.
검증 command의 argument에는 경로/식별자만 있으며 secret 값은 없었다. 구조/권한 PASS는 실제 token/API key
인증 또는 guild/channel 실존·권한 PASS가 아니다. 같은 UID의 적대적 완전 격리를 주장하지 않는다.
안전한 증거: Pi `/home/os/discordbot-phase10/verification-progress.json`, stage `verified_not_activated`.

## Source / Release Identity

Origin `https://github.com/lgw323/Bot.git`. 사용자가 exact commit
`d54ff3696c1a81d48a88008110d044d0e14edc89`의 새 `refs/heads/codex/rebuild-v2` 일반 push를 승인했다.
2026-09-19 전체 ancestry 1,415 objects / 661 blobs / 5,275,062 bytes를 검사했다. 민감 파일명 검사 결과 0,
내용 pattern 7곳은 credential 경로 참조 3곳과 synthetic fixture 4곳으로 분류했다. 실제 secret/key/data를
발견하지 않았다. pattern 검사가 모든 형태의 비밀을 수학적으로 배제한다는 뜻은 아니다. PC `.env`는 읽지 않았다.
승인된 exact commit만 push했고 remote ref hash 일치를 재조회했다. main은 전후
`8432fdef40cddc131176fa875e350660dc897e12`로 동일하다. force/history rewrite 없음.
당시 초기 production pin은 `d54ff36`이었다. 후속 사용자 승인으로 아래 `63c7722`까지 변경했다.
자동 업데이트 비활성화와 이후 새 commit 수동 검토·승인 정책은 유지한다. Bot-Data push는 별도 승인된 backup drill이다.
PHASE 10 guard 포함 commit `672694d3f0c5418ece99aecd0e886a42c53961ab`를 allowlisted git archive로
전달하여 offline ARM64 build/operations strict tests/manifest validation/publish까지 **133.961초**에 통과했다.
candidate release **`r-672694d3f0c5418e-d026a47ed4f4b38a`**, schema range [5,5], wheel lock SHA256
`d026a47ed4f4b38ad8b7d3ba4fb70d18a42f9abadce0ace763ca01329b80f394`.
source archive SHA256 `7a53f8a3ae9f0ed4234dd937a4d6b821c77e9fe41e2254bd4b29f2cf39c2f100`.
빌드는 외부 네트워크가 없는 transient unit에서 기존 sealed wheelhouse만 사용했다. current pointer와
staging config digest는 전후 동일하다. 새 release의 production pair activation/live smoke는 아직 미실행이다.

후속 off-host runtime 연결/전환 guard를 포함한 소스는 commit
`d54ff3696c1a81d48a88008110d044d0e14edc89`, allowlisted archive SHA256
`fadf41bf1befdf0d4859f0f8203b2b1d2ac1035c0e57c798f53765e617b1fb0f`다.
2026-09-18 실제 ARM64 offline build/operations strict/manifest [5,5] PASS, 소요 137.568초.
새 release는 `r-d54ff3696c1a81d4-d026a47ed4f4b38a`다. 실제 runtime `backup_once`의 opt-in 경로로
격리 production copy backup → Bot-Data publish/read-back → independent download → decrypt/semantic/count
비교를 통과했다. 증거 `/home/os/discordbot-phase10/offhost-wiring-progress.json`, stage
`verified_not_activated`. candidate config/current pointer/canonical inode 보존, production_enabled false.
새 release activation 또는 production timer 검증은 아니다.

## Pi staging / Longer observation

2026-09-15 01:45:12 UTC 재확인: real Watch PID 2417, synthetic Discord PID 2406, NRestarts 둘 다 0,
same release `r-0376f14868461d16-d026a47ed4f4b38a`, ready true. 실제 discord-bot PID 0 / inactive.
boot ID `77ce3f22-660f-45f6-a3d5-1a6e40650dbe`. cloudflared active PID 939, NRestarts 1(Phase 9 재부팅 이후
상태), connector 설정 변경 없음. four-hour synthetic backup timer active, 마지막 trigger 09:00 KST,
당시 다음 trigger 13:00 KST; backup Result success, update timer inactive. temperature 60.6°C.
이전/현재 PID 일치만으로 사이의 모든 시간을 실제 관찰했다고 주장하지 않는다.

처음 snapshot의 synthetic `database_recent_failures=2`, 후속 snapshot은 0이었다.
후속 누적 probe metric은 ok 15877 / failed 15, 당시 readiness 1, last DB latency 약 0.000769s,
backup age 약 7163s, RPO exceeded 0. 이 누적 실패의 개별 원인/발생 시각은 확인되지 않았다.
실패 수가 0이었다거나 장기 안정성이 증명됐다고 표시하지 않는다.

`deploy/staging/observe.py`: 24h/60s cadence의 finite root observer, 외부 통신 없이 loopback HTTP,
systemd, proc/sysfs 및 파일 개수/bytes만 읽는다. RSS/FD/threads/restart, probe success/failure/latency,
backup age/trigger, audit count, disk/cache growth, load/temp/throttling availability를 fsync된 JSONL/summary로 남긴다.
secret/DB contents/raw journal은 읽지 않는다. synthetic marker가 없거나 production이 시작되면 중단한다.
throttling sysfs가 없으면 unavailable로 기록하며 throttling 없음으로 간주하지 않는다.

첫 unit `phase10-observation-20260915`의 결과는 `/var/lib/discordbot` 상위 권한 때문에 operator가
바로 읽지 못했다. 두 번째 창은 PowerShell의 `&&` 구문 오류로 실행되지 않았다. shell chaining을 없앤
`finish_candidate_checks.py`로 격리 복구와 기존 evidence 집계를 실행했고, interactive sudo 후 성공했다.
새 경로 `phase10-observation-20260915-02`에는 samples가 없지만 **첫 observer는 실제 24시간 완료**했다.
안전한 집계는 `/home/os/discordbot-phase10/observation-review.json`에 보존했다.

| 관찰 항목 | 실제 결과 |
| --- | --- |
| 기간 / 표본 | elapsed 86,400.135초, 1,438개; first-to-last 86,400.013초, 최대 간격 60.555초 |
| 프로세스 | synthetic PID 2406 / Watch PID 2417 유지, 둘 다 NRestarts 0 |
| RSS | synthetic 52,864→52,868 KiB; Watch 68,944→69,064 KiB |
| FD / threads | synthetic FD 7, threads 3; Watch FD 9→9 (최대 12), threads 4 |
| DB probe 실패 누적 | synthetic 15→27 (+12), Watch 17→34 (+17); recent failures 각각 최대 2 |
| 표본의 마지막 DB 실행 시간 최대 | synthetic 0.079287초, Watch 0.397054초; 전체 요청의 최대/percentile은 아님 |
| Health 수집 | 9010 누락 1회, 9011 누락 0회; 수집된 응답의 not-ready 0회 |
| Backup | 최대 age 약 14,396.34초 (<4h), RPO exceeded 0; timer trigger 값 7개 (초기값 포함) |
| 온도 | 54.55–63.9°C |
| Disk / cache / audit | free 113,764,929,536→112,809,566,208 bytes; cache 0; audit files 88→100 |

DB probe 실패 원인은 기존 증거로 분류할 수 없다. 추가 집계에서 9010 누락은 `HTTPError` 1회로
좁혔지만 HTTP status는 당시 저장하지 않아 503이라고 단정하지 않는다. 1,438개 throttling 표본은 모두
numeric 0이었다(표본 사이 상태는 미관찰). 큰 disk 감소 구간 5개의 backup/audit bytes 증가는 0이었다.
2026-09-18 journal 사용량은 2.5GiB. 관찰 window의 metadata 집계는 Watch INFO 379,222건,
synthetic Discord INFO 379,218건이었다. 후속 MESSAGE는 메모리에서 allowlist category로만 변환했고
원문을 출력·보존하지 않았다. 45초 제한으로 일부만 집계한 각 서비스 309,526건 전부가
server-maintenance/telemetry-drain/database-probe의 정상 started/succeeded였다. 전체 기간의 메시지
분류가 완료됐다고 주장하지 않는다. 주기 작업당 이벤트 2개가 발생하는 코드와 일치한다.
로그가 disk 증가에 기여하는 원인은 확인했지만 free-space 감소 전부를 byte 단위로 귀속하지 않았다.
후속 로컬 수정 `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`는 세 주기 작업의 정상 lifecycle만 journal에서 제외하고 metrics/bounded task history와
실패·취소·deadline/retry 기록은 유지한다. DB probe 실패는 message/context 없이 stable error code만
추가한다. 기존 readiness 기준/주기/timeout은 유지한다. 수정본의 Pi build/운영 테스트/세 scope 검증도 138.196초에 PASS했다. 새 release는
`r-63c77229d1a6e76a-d026a47ed4f4b38a`, schema [5,5]이며 current/staging config는 전후 동일하다.
당시 서비스 적용은 미실행이었다. 후속 실제 bounded 관찰은 위 최종 증거에 기록했다. 과거 DB 실패 원인은 소급 미확정이다. allowlisted archive SHA256은
`8948ad0da780f81336d7bb30f7fc41fc3485602f5cd91c757d658221fb5cec69`이며 Pi로 전달했다.
별도 `verify_candidate.py`로 검증했으며 처음 잘못 지정한 run 경로는 실행 전 guard가 거부했다.
수정한 경로로 성공했다. 이후 sudo 입력 완료 답변은 별도로 요구하지 않고 safe progress로 확인한다.
63c7722 ancestry의 1,434 objects / 667 blobs를 검사했고 이전 7개 fixture/path 외 새 탐지는 없었다.
사용자가 exact `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`까지 기존 branch 일반 fast-forward
push와 초기 production 예정 commit 변경을 명시적으로 승인했다. push 직전에 전체 ancestry의
1,434 objects / 667 blobs / 5,314,031 bytes 및 역사적 파일명·commit 메시지를 재검사했다.
민감 파일명/commit 메시지 탐지 0, 기존 credential 경로 3곳과 synthetic fixture 4곳 외 새 내용 탐지 0.
추가 1 commit·6 files의 diff도 재검토한 뒤 `d54ff36..63c7722` 일반 fast-forward push를 완료했다.
원격 `refs/heads/codex/rebuild-v2`는 exact 승인 commit과 같고, main은
`8432fdef40cddc131176fa875e350660dc897e12`로 보존됐다. force/history rewrite는 수행하지 않았다.
이후 로컬 문서 commits는 승인된 push 범위에 포함하지 않았다. production 예정 release는
`r-63c77229d1a6e76a-d026a47ed4f4b38a`; auto-update 비활성화 및 별도 10B 최종 승인 경계 유지.
**24h 관찰 완료와 무결점 soak PASS는 다르며**, production/provider 부하는 미검증이다.

## Live Integration / Watch / Cloudflare

Gateway, command sync, `/내정보`, `/랭킹`, `/요약`/Gemini, Music/provider/voice/TTS,
Watch browser/public route 실제 smoke는 모두 NOT RUN. 최소 visible action과 startup side effect를
[cutover runbook](cutover-runbook.md)에 명시했다. 기존 친구 서버에 메시지를 전송하지 않았다.
사용자 선택 origin은 **`https://watch.lgw323.com`**. 제시 경로는 existing Cloudflare tunnel →
`http://127.0.0.1:9000`; signed control 9001과 health 9010/9011은 public 금지.
hostname 선택은 기록했고 DNS/public route 생성·변경은 10B final approval까지 실행하지 않는다.
2026-09-19 read-only DNS 조회에서 해당 이름의 A/AAAA 응답이 이미 존재함을 확인했다.
DNS만으로 route를 판단하지 않았다. 후속 current connector config event 검토 결과는 위 최종 증거를 따른다.

## Backup / Off-host Status

Pi timer는 여전히 synthetic DB 대상이다. Production candidate의 PC 및 Pi isolated encrypted recovery는 완료했다.
2026-09-17 사용자가 private `https://github.com/lgw323/Bot-Data.git`을 destination으로 선택하고,
source 인증과 분리한 write deploy key 등록/Private 상태를 확인했다. `git_backup.py`와 별도 수동 drill은
기존 `db-backup` branch에 암호화 artifact/allowlisted metadata만 fast-forward publish/read-back한다.
최신 8개 + 최근 7개 UTC 날짜별 1개 retention은 현재 V2 tree만 정리하며 Git history와 legacy는 보존한다.
과거 object의 실제 저장 용량은 계속 증가하므로 물리 삭제 보장이라고 주장하지 않는다.
11개 offline synthetic Git test가 통과했고, **actual Pi upload/download/isolated decrypt PASS**다.
Pi `/home/os/discordbot-phase10/offhost-progress.json`의 stage는 `verified_not_enabled`다.
Remote commit `1d6d6f5317d27581425e70cabb1a94c111f2c753`, active V2 recovery point 1개.
Identity `20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71`, artifact SHA256
`3dcaf8eafd9cb33309531e556593dc4a968b3696df2f9236b254625ce1b43766`로 Pi 원본과 read-back/download가 일치했다.
복구 DB SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`, schema 5와
six-table counts도 앞의 Pi 후보와 일치했다. 업로더는 SSH scope만, no-network 복구 worker는 DB key만 받았다.
증거와 plaintext isolated restore는 `/var/lib/discordbot/phase10-offhost-20260917-01/`에만 보존했다.
실제 remote pruning은 아직 대상이 없어 실행되지 않았다. retention 삭제/legacy 보존은 synthetic Git test로 검증했다.

후속 `4abaaa2`는 정확한 repository/ref opt-in을 loader/backup entrypoint에 연결했고 remote read-back
성공 후에만 latest를 갱신한다. transport는 총 90초 deadline, 실패 때 이전 latest/로컬 artifact를 보존한다.
현재 Pi config는 여전히 `backup_remote:null`; ARM64 격리 runtime wiring은 PASS, 실제 설치는 10B gate다.
두 번째 remote identity `20260918T002700190443-9da027cd4df542f3912d600d3499dbb0`, SHA256
`c40ef426984524686e1d6fcfee5b6e5cfafbacff3697aa838e09b7955612d956`, remote commit
`94886cab51fd0bf4cdc0ec55f21f05c0c1bd6e55`. schema 5/count/data/metadata reconciliation PASS.
실제 recovery point는 이제 2개이며 retention 삭제는 여전히 synthetic 증거만 있다.
키는 remote에 저장하지 않으며 manual drill만으로 지속 off-host RPO <=6h를 입증하지 않는다.

사용자가 encrypted candidate artifact와 metadata의 정확한 Pi 전송 경로를 승인했다(“ㄱㄱ”).
`/home/os/discordbot-phase10/recovery-input/` (0700)에 파일 두 개(0600)만 전송했고 `.enc` SHA256이
PC 증거와 일치했다. plaintext DB/키는 전송하지 않았다. 최초 전송은 자동 승인 검토가 해당 payload/경로의
명시적 승인 부족으로 거절했고, 사용자 확인 후 승인 범위 그대로 수행했다.
`restore_candidate.py`의 새 private recovery path에서 decrypt/schema/semantic, 재backup/restore,
runtime UID open/close를 완료했다. actual key/path/permissions의 격리 검증이며 canonical timer 검증은 아니다.

## Cutover Timeline / Actual Downtime / Production Smoke

10B 승인·canonical promotion·production login·production timer activation: **NOT RUN**.
Actual downtime, post-cutover health, live production smoke 결과: **N/A**.
30–60분은 미실측 maintenance 계획값이다. V1은 source 보존 이후 이미 실행되지 않았다는 operator 확인만
있으며, 이 세션에서 V1을 종료하거나 삭제하지 않았다.

## Rollback Readiness / Remaining Risks / PHASE 11 Gate

source schema 0 preservation+verified encrypted restore, schema 5 candidate+backup/restore를 PC에 보존했다.
Pi previous immutable releases와 staging DB/config는 유지했다. code-only rollback은 live schema compatibility가
필요하고 V2 writes 뒤 pre-cutover DB로 돌아가면 데이터 손실/reconciliation 판단이 필요하다. down-migration,
동시 V1/V2 writer, 불확실한 promotion 재시도 금지. operator가 2026-09-17 V1 music_state 보존본은
없다고 확인했다. 기존 active queue/voice channel/재생 위치는 미이전이며 synthetic snapshot을 대신 사용하지 않는다.

남은 위험: 실제 API 인증/resources/permissions, live providers 및 command UI, 지속 off-host durability,
기존24h probe/HTTP 실패 원인, power-loss와 실부하 capacity, production RPO/RTO,
미이전 V1 config overrides/log admin UI. Synthetic 수정본 관찰과 설치·복구 명령표는 완료했지만 위 위험은 남는다.
V1 code/scripts/env/legacy compatibility/history/backups/releases를 보존한다. PHASE 11은 별도 지시 전 시작하지 않는다.

## Tests / Commits / Decision Required

직접 regression과 wizard tests PASS. 중간 full strict는 700 passed / 1 failed였으며 실패는 작성 중인
cutover-runbook 문서의 missing-link 검사 하나였다. 문서 완료 후 최종 Windows strict는
setup까지 **705 passed, 0 xfailed, 33.28s**, 후속 host verification/restore 도구 추가 뒤에는
**711 passed, 0 xfailed, 34.37s**다. 기존 Python `audioop` deprecation warning 1개가 남았다.
RuntimeWarning/PytestUnraisableExceptionWarning은 error로 처리했고 xfail_strict=true였다.
기능 코드의 unrelated refactor/schema/dependency upgrade 없음. 작은 responsibility commits로 기록하며
실제 data/key/artifact는 코드 저장소에 stage하지 않는다. 승인된 코드 commit의 push를 완료했고,
승인된 Bot-Data에는 encrypted artifact/allowlisted metadata만 일반 push했다.

후속 entrypoint/observation 집계는 Pi에서 실제 실행 성공했다. 복구/집계 도구는 `6fd1660`에 커밋했다.
직전 Git staging의 자동 승인 검토 사용량 차단은 새 요청에서 정상 승인 경로로 재검토되어 해소됐다.
우회하지 않았다. off-host adapter 추가 뒤 Windows full strict는 **722 passed, 0 xfailed, 47.83s**이며
기존 audioop warning 1개만 남았다. 실제 외부/운영 DB를 테스트가 사용하지 않는다.
runtime wiring의 중간 full strict 실패 2개는 synthetic settings fixture의 새 optional field 누락이었다.
fixture를 명시적 `backup_remote=None`으로 보완한 뒤 725 passed, 최종 stopped activation/host 검증 도구까지
**732 passed, 0 xfailed, 48.96s**다. 실제 Pi 검증 성공과 Windows synthetic 테스트 성공은 구분한다.
코드 커밋은 `6fd1660`, `4f15a34`, `4abaaa2`, `b1562d7`, `d54ff36`으로 책임별 분리했다.
후속 로그 수정 `63c7722`는 독립 commit이며 사용자 별도 승인 후 exact commit만 push하고 production 예정 pin을 갱신했다.
수정 전 회귀 2개가 예상 실패했고 수정 후 관련 54개 및 전체 strict **735 passed, 0 xfailed, 52.97s**다.
기존 audioop deprecation warning 1개만 남았다. readiness/DB schema/실제 사용자 동작은 변경하지 않았다.
2026-09-17 후속 remote source ref 재조회는 자동 승인 검토 사용량 한도로 거절되어 갱신하지 못했다.
2026-09-18 SSH 상태 조회는 정상 승인 경로로 성공했고 차단된 조회를 우회하지 않았다.

Source publication/update policy는 승인·실행 완료다. 실제 시작 시각은10B 승인 뒤 잡으며30–60분을 계획한다.
수정본 synthetic 관찰, 기존 이상 분류/위험 공개, route read-only 검토 및 exact config/off-host/promotion/
rollback 명령표를 완료했다. 최종 상태는 **10A COMPLETE / 10B NOT AUTHORIZED**다.
실제 production 전환 및 PHASE11은 실행하지 않았다. 최종 질문은 다음과 같다.

**“이 상태로 실제 production cutover(PHASE 10B)를 진행할까요?”**
