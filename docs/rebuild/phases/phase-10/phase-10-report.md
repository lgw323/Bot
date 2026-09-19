# PHASE 10 report

Updated: 2026-09-19. **10A IN PROGRESS / PC·Pi·Bot-Data isolated recovery verified; 10B NOT AUTHORIZED.**
이 보고서는 현재 재개 지점이며 production 성공 보고서가 아니다. 최종 cutover 승인 질문은 아직 올리지 않았다.

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
초기 production pin은 `d54ff36`, 자동 업데이트 비활성화, 이후 새 commit은 수동 검토·승인 정책이다.
후속 로컬 수정은 이 승인에 포함되지 않는다. Bot-Data push는 별도 승인된 backup drill이다.
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
추가한다. 기존 readiness 기준/주기/timeout은 유지한다. 수정본의 Pi 실행·효과 및 DB 실패 원인 재관찰은
아직 미검증이다. allowlisted archive SHA256은
`8948ad0da780f81336d7bb30f7fc41fc3485602f5cd91c757d658221fb5cec69`이며 Pi로 전달했다.
별도 `verify_candidate.py` interactive sudo 창을 열고 사용자 입력을 요청했다. 승인된 production pin을 임의 변경하지 않는다.
**24h 관찰 완료와 무결점 soak PASS는 다르며**, production/provider 부하는 미검증이다.

## Live Integration / Watch / Cloudflare

Gateway, command sync, `/내정보`, `/랭킹`, `/요약`/Gemini, Music/provider/voice/TTS,
Watch browser/public route 실제 smoke는 모두 NOT RUN. 최소 visible action과 startup side effect를
[cutover runbook](cutover-runbook.md)에 명시했다. 기존 친구 서버에 메시지를 전송하지 않았다.
사용자 선택 origin은 **`https://watch.lgw323.com`**. 제시 경로는 existing Cloudflare tunnel →
`http://127.0.0.1:9000`; signed control 9001과 health 9010/9011은 public 금지.
hostname 선택은 기록했고 DNS/public route 생성·변경은 10B final approval까지 실행하지 않는다.

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

남은 위험/작업: 실제 API 인증/resources/permissions, 새 release pair activation, live providers 및 command UI,
off-host durability, 24h 중 probe failures/HTTP 누락의 상세 원인, 로그 수정의 Pi 재검증,
power-loss와 실부하 capacity, production RPO/RTO,
미이전 V1 config overrides/log admin UI, maintenance/rollback operator 확인. 준비된 copy 성공은 이를 닫지 않는다.
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
후속 로그 수정 `63c7722`는 독립 로컬 commit이며 push/production pin 변경은 하지 않았다.
수정 전 회귀 2개가 예상 실패했고 수정 후 관련 54개 및 전체 strict **735 passed, 0 xfailed, 52.97s**다.
기존 audioop deprecation warning 1개만 남았다. readiness/DB schema/실제 사용자 동작은 변경하지 않았다.
2026-09-17 후속 remote source ref 재조회는 자동 승인 검토 사용량 한도로 거절되어 갱신하지 못했다.
2026-09-18 SSH 상태 조회는 정상 승인 경로로 성공했고 차단된 조회를 우회하지 않았다.

Source publication/update policy는 승인·실행 완료다. maintenance 시간은 미확정이다.
선택된 Bot-Data actual drill과 ARM64 runtime backup wiring은 완료했고, 용량 증가와 로그 수정 검토는 남는다.
`activate-stopped.py`와 6개 guard/uncertain-outcome test를 구현했지만 실제 실행은 10B 승인 뒤다.
관찰 이상 항목 검토 및 최종 release/config/drop-in/rollback command sheet 확정도 남는다.
모든 risk·backup·source·downtime·smoke가 검토 가능한 상태가 된 뒤에만 10B 명시적 승인을 요청한다.
