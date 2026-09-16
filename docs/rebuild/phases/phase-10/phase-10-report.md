# PHASE 10 report

Updated: 2026-09-16. **10A IN PROGRESS / production data copy rehearsal verified; 10B NOT AUTHORIZED.**
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
검증 reference release는 설치된 `r-0376f14868461d16-d026a47ed4f4b38a`; final production release는 미확정.
PC rehearsal은 Pi production backup path/key/mount/timer나 자동 off-host 복구 검증을 대체하지 않는다.

## Config / Secrets / Security

[직접 입력 가이드](config-migration-guide.md), invalid-placeholder template, hidden double-entry tool,
network/DB startup 없는 scoped preflight를 추가했다. V1 template의 모든 변수에 destination 또는
직접 매핑 없음/현재 typed default를 표시했다. Summary retention 등 기존 Phase 구현과 V1 template 차이,
raw Discord log/admin UI 미연결도 숨기지 않았다. production placeholder를 config/secret 단계에서 거부하는
guard와 regression을 추가했다. valid-looking 값의 실존/권한/API 인증은 live gate다.

사용자 요청에 따라 파일별 편집 대신 한 번 실행하는 한국어 `setup-production.py`를 추가했다.
세 기존 secret은 숨김 두 번 입력, 다섯 ID와 origin은 한국어 안내, Watch control/capability는 안전한
독립 무작위 키 자동 생성이다. 후보 생성/owner/mode/기본 validation을 수행하고 기존 후보/staging을
덮어쓰지 않는다. echoed getpass fallback과 noninteractive 실행을 거부한다. 실제 입력은 아직 시작하지 않았다.
Pi `/home/os/discordbot-phase10/`에 wizard/config template/enter_secret/preflight를 전달했다.
Pi 임시 synthetic 디렉터리에서 owner/mode, exclusive-create, staging sentinel 보존을 실제 검증했다.
현재 `/etc/discordbot/config.json` 및 staging credentials는 그대로다. Production Discord/Gemini,
master/guild/main/music/private-admin IDs 및 Pi candidate secret scope/mount 검증은 operator 입력 대기다.
Discord: discord_token/gemini_key/control_key; Watch: capability_key/control_key; Operations: db_key.
secret을 argument/journal에 넣거나 모든 서비스에 공유 mount하지 않는다. 실제 namespace/source 접근
검증은 입력 후 별도 no-network probe를 거쳐야 하며 아직 production credential validation PASS가 아니다.

## Source / Release Identity

Origin `https://github.com/lgw323/Bot.git`. PHASE 10 시작에 `git ls-remote origin refs/heads/codex/rebuild-v2`
exit 0 / empty를 재확인했다. normal push 대상 제안은 그 remote의 `refs/heads/codex/rebuild-v2`다.
remote ref/update policy 승인 전 network update는 disabled로 유지한다. push/force-push/history rewrite 없음.
PHASE 10 guard를 포함한 최종 immutable ARM64 release의 build/manifest/pair verification은 남아 있다.
현재 Pi release의 성공을 아직 배포되지 않은 새 guard의 실서비스 검증으로 표시하지 않는다.

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

첫 unit `phase10-observation-20260915`는 시작됐으나 `/var/lib/discordbot` 상위 권한 때문에 operator가
결과를 읽을 수 없었다. 권한을 확대하지 않고 별도 `/var/tmp/phase10-observation-20260915-02/`로
다시 시작할 interactive sudo 창을 준비했다. 2026-09-16 01:57:51 UTC 확인에도 새 unit은 inactive,
새 summary는 없었다. **새 observer의 실제 sample/장기 관찰 시간은 아직 미확인**.
24h complete가 아니다. 기존 evidence는 지우지 않는다.

## Live Integration / Watch / Cloudflare

Gateway, command sync, `/내정보`, `/랭킹`, `/요약`/Gemini, Music/provider/voice/TTS,
Watch browser/public route 실제 smoke는 모두 NOT RUN. 최소 visible action과 startup side effect를
[cutover runbook](cutover-runbook.md)에 명시했다. 기존 친구 서버에 메시지를 전송하지 않았다.
사용자 선택 origin은 **`https://watch.lgw323.com`**. 제시 경로는 existing Cloudflare tunnel →
`http://127.0.0.1:9000`; signed control 9001과 health 9010/9011은 public 금지.
hostname 선택은 기록했고 DNS/public route 생성·변경은 10B final approval까지 실행하지 않는다.

## Backup / Off-host Status

Pi timer는 여전히 synthetic DB 대상이다. Production candidate의 PC encrypted recovery 증거만 완료했다.
Off-host destination은 미확정이며 `backup_remote:null`; 현재 remote adapter가 없다. PC/NAS encrypted
publication 또는 private object storage 선택과 checksum/identity/read-back restore/retention/failure visibility를
runbook에 제시했다. key는 destination에 저장하지 않는다. destination 승인이 없으면 blocker이며
local-only 재해 위험을 사용자가 명시적으로 수락하기 전 cutover로 진행하지 않는다. 초기 RPO <=6h.

## Cutover Timeline / Actual Downtime / Production Smoke

10B 승인·canonical promotion·production login·production timer activation: **NOT RUN**.
Actual downtime, post-cutover health, live production smoke 결과: **N/A**.
30–60분은 미실측 maintenance 계획값이다. V1은 source 보존 이후 이미 실행되지 않았다는 operator 확인만
있으며, 이 세션에서 V1을 종료하거나 삭제하지 않았다.

## Rollback Readiness / Remaining Risks / PHASE 11 Gate

source schema 0 preservation+verified encrypted restore, schema 5 candidate+backup/restore를 PC에 보존했다.
Pi previous immutable releases와 staging DB/config는 유지했다. code-only rollback은 live schema compatibility가
필요하고 V2 writes 뒤 pre-cutover DB로 돌아가면 데이터 손실/reconciliation 판단이 필요하다. down-migration,
동시 V1/V2 writer, 불확실한 promotion 재시도 금지. V1 music_state 최신 보존본/queue restore는 별도 확인 필요.

남은 위험/작업: 실제 credentials/resources/permissions, final ARM64 release, live providers 및 command UI,
off-host durability, incomplete soak와 과거 probe failures, power-loss와 실부하 capacity, production RPO/RTO,
미이전 V1 config overrides/log admin UI, maintenance/rollback operator 확인. 준비된 copy 성공은 이를 닫지 않는다.
V1 code/scripts/env/legacy compatibility/history/backups/releases를 보존한다. PHASE 11은 별도 지시 전 시작하지 않는다.

## Tests / Commits / Decision Required

직접 regression과 wizard tests PASS. 중간 full strict는 700 passed / 1 failed였으며 실패는 작성 중인
cutover-runbook 문서의 missing-link 검사 하나였다. 문서 완료 후 최종 Windows strict는
**705 passed, 0 xfailed, 33.28s**다. 기존 Python `audioop` deprecation warning 1개가 남았다.
RuntimeWarning/PytestUnraisableExceptionWarning은 error로 처리했고 xfail_strict=true였다.
기능 코드의 unrelated refactor/schema/dependency upgrade 없음. 작은 responsibility commits로 기록하며
실제 data/key/artifact는 stage하지 않는다. commit 목록은 책임별 Git log에서 확인하며 push는 미실행이다.

진행에 필요한 입력은 secret 값 대신 완료 경로, approved backup destination 또는 explicit local-only risk
acceptance, source publication/update policy 승인, maintenance 시간이다. 최종 release와 Pi credential/candidate
검증이 끝난 뒤에만 모든 risk·backup·source·downtime·smoke를 다시 제시하고 10B 명시적 승인을 요청한다.
