# PHASE 10B Full-Sweep Report

이 문서는 bounded full-sweep 정책·검증·실행·실패·수정·재시도의 상세 근거를 관리하는 기준 보고서다.
[PHASE 10 부모 보고서](phases/phase-10/phase-10-report.md)는 10A 준비·migration/cutover·기존 10B 이력과
전체 PHASE 10 상태를 관리한다. PHASE 10 작업을 재개할 때 두 보고서와
[current plan](current/current-plan.md)을 함께 읽으며, 각 문서의 책임 범위에서는 최상단 최신 continuation이 우선한다.
아래 두 continuation은 기존 부모 보고서에서 이동했다. 당시 판정·승인 경계·수치를 변경하지 않았다.
과거 본문의 이전 보존 이력 참조는 부모 보고서에 남아 있다. 이후 상세 full-sweep 근거는 이 파일에만 추가한다.
문서 분리는 production 상태 변경이나 새로운 runtime 활성화 승인이 아니다.

## Continuation — H2 subtype remediation VERIFIED / exact push-pin approval required

2026-09-19 첨부 지시에 따라 current plan·부모 보고서·최신 full-sweep continuation으로 상태를 재구성하고,
정지 상태 재검증 →synthetic 재현 →최소 진단/정책 수정 →회귀 →exact Windows/Pi 검증을 완료했다.
**PHASE 10B INCOMPLETE. 새 production activation0/push0/provider request0.**
다음 승인 후보는 아래 **ecd391ff 단 하나**다. 기존 운영 H2의 실제 SQLite 하위 코드는 소급 확정하지 못했다.
이번 결과는 가능한 BUSY 경로의 실제 재현 및 엄격한 subtype 처리·진단 보강을 검증한 것이며,
과거 H2가 BUSY였거나 모든 live 문제가 해결됐다는 주장이 아니다.

### Current production reconciliation and H1 boundary

- Current source/pin `92c25546af6b49044e17ed2a705a7cdf885532a0` /
  `r-92c25546af6b4904-3dac82a792fad576` 그대로. Dependency3dac82a…/config41edd03… 불변.
- Fresh root read-only `h2-stopped-baseline.json`: **verified_stopped_preserved_integrity**;
  canonical/copy **`678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66`**, schema5/integrity PASS.
  Favorites40/owners3, music_play_counts53/music_settings1/users15, Watch sessions/playlists0.
  Data checksum6c32578e…/metadata318a1331… 및 current/preservation inventory는 직전 H2 evidence와 같다.
  최신8번째 preservation inventory `6cb75333b6e47812a28a7d1bc1284fc0a03768852b713dcc42782035e08cc0e8` 불변.
- Production/staging/operations inactive/MainPID0, production/staging boot disabled,
  backup/update/manual timers disabled/inactive, auto-update OFF, current Watch9000 route/internal route0 확인.
  재현/빌드 전후 protected data/state/cache/backups/audit/config 및 모든8개 preservation 불변.
  테스트는 canonical에 mutation/lock을 걸지 않았고 candidate replay/restore/remigration/down-migration/V1 start 없음.
- H1은 직전 actual production ACL PASS가 유효하다. H1 구현을 재설계하거나 ACL 허용 범위를 바꾸지 않았다.
  최종 후보에서도 세 credential scope와 root observer view의 exact/read-only/direct-source-denied 검증을 통과했다.

### Concurrency review and what can cause the umbrella error

1. Discord와 Watch는 같은 파일에 각각 독립적인 `SqliteDatabase`를 구성한다. 각 process는 reader1/writer1
   bounded executor를 소유하며 worker가 매 요청의 connection을 열고 같은 thread에서 닫는다.
   Process-global DB lock은 없고 cross-process 동시성은 SQLite가 관리한다.
2. `connect`는 existing mode=ro/rw, busy100ms(남은 deadline 이하), synchronous=NORMAL/temp_store=MEMORY/
   cache_size−2000/trusted_schema OFF, read query_only를 설정한다. Reader BEGIN, writer BEGIN IMMEDIATE;
   callback은 동기 SQL transaction이고 DB transaction 안에서 provider/network await를 하지 않는다.
3. 두 process의 health probe는 정상 주기5초마다2초 request budget으로 reader lane을 사용한다.
   Watch writer는 owner lease heartbeat/receipt cleanup을 수행하고 Discord의 engagement/Music도 짧은 writer
   transaction을 사용한다. 별도 reader lane이 다른 process나 같은 process writer의 SQLite 잠금을 없애지는 않는다.
   장시간 transaction이 운영에서 실제 관찰됐다는 증거는 없다.
4. Phase3 계약은 explicit bootstrap WAL, archive/restore DELETE, startup journal 유지 및 busy/I/O typed umbrella를
   명시한다. WAL 전환 운영 절차를 Phase8로 넘겼지만 실제 promotion은 bytes를 보존하고 별도 WAL 전환을 하지 않는다.
   이번 root verifier는 DB header format bytes18/19만 읽어 **rollback**을 확인했다. 초기 immutable URI의
   `PRAGMA journal_mode` 결과만으로 mode를 확정하지 않고 header로 보완했다.
   따라서 **live WAL 전환이라는 과거 계획이 실제 운영 경로에는 구현되지 않은 차이**를 기록한다.
   Rollback 자체를 corruption으로 간주하지 않으며 이번 수정에서 journal/schema/DB 경로를 바꾸지 않았다.
5. SQLite rollback EXCLUSIVE는 다른 reader와 공존할 수 없고, BUSY는 process 간 충돌에서 발생할 수 있다.
   LOCKED는 같은 connection/shared-cache 상황을 구분한다. [SQLite locking](https://www.sqlite.org/lockingv3.html),
   [SQLite result codes](https://www.sqlite.org/rescode.html)를 코드·실제 synthetic 결과와 함께 대조했다.
   이 일반 규칙은 지난 H2의 실제 원인 확정 근거를 대신하지 않는다.

기존 `database_recent_failures=2`는 같은 요청의 worker/awaiter observation 두 개이며 독립 실패2건이 아니다.
지난354.569초/17 samples/Watch66 success+1 failure/ready snapshot 및 무결성 PASS는 그대로 유지한다.

### Isolated reproduction and causal limits

모든 재현은 fixture가 만든 임시 synthetic DB만 사용한다. Windows와 network-disabled Pi ARM64에서
동일 test case를 실행했다. Production 데이터/원문 exception/SQL/user content/credential을 출력하지 않았다.

| Condition | Reproduced evidence / classification |
| --- | --- |
| Separate process BEGIN / IMMEDIATE / EXCLUSIVE × DELETE / WAL | Pipe barrier로 writer 잠금을 확정한 뒤 실제 probe 실행. DELETE+EXCLUSIVE만 configure-stage SQLITE_BUSY5, connection_opened=true/close_succeeded=true. 나머지5조건 PASS. 기존 read+SELECT1 경로도 같은 BUSY umbrella 실패 재현. |
| Short writer overlap | 별도 process EXCLUSIVE를 probe connection 생성 뒤 해제하여 같은 request가 성공. 테스트를 위한 명시적 barrier이며 runtime retry/sleep 추가 없음. |
| SQLITE_LOCKED | Synthetic shared-cache schema lock에서 실제 extended LOCKED 재현. 현재 application은 shared cache를 켜지 않으므로 정상 process 간 transient로 허용하지 않음. |
| Missing file/parent | Actual temporary missing path CANTOPEN, 자동 DB 생성 없음. CANTOPEN만으로 missing과 permission을 항상 구별할 수 있다는 주장은 하지 않음. |
| Permission | Pi의 nonroot test worker에서 actual mode000 파일 접근 거부. Windows는 같은 PermissionError boundary 주입으로 대조; Windows POSIX chmod 검증이라 주장하지 않음. |
| Read-only filesystem / I/O | EROFS/EIO/ENOSPC 및 SQLite extended IOERR의 안전한 boundary 주입. 실제 디스크 고장·filesystem remount를 하지 않음. |
| Non-database / corruption | 임시 non-database bytes 및 SQLite 첫 B-tree page type 손상에서 실제 NOTADB/CORRUPT →data_integrity. |
| Open/configure/begin/execute/fetch/commit/close | 각 단계의 BUSY/LOCKED/IOERR/CORRUPT/NOTADB fault injection으로 단계·family·숫자·close 결과 검증. 임의 sqlite_errorname/경로/원문 메시지 미출력. |
| Cancellation / cleanup | Awaiting probe 취소 후 worker capacity를 조기 반환하지 않고 동일 reader lane barrier까지 drain·close 확인. Primary BUSY 뒤 close 실패는 cleanup_failed=true로 HARD; 원래 실패를 가리지 않음. |
| Threshold / observer | BUSY1→healthy1→healthy2 회복,60초 내 재발,15초 만료,stale readiness,unknown/malformed subtype,LOCKED/extended BUSY/close failure,terminal deadline/capacity 모두 fail-closed 검사. 실제 observer loop가 BUSY 뒤 계속하고 다음 hard event에서 stop하는 회귀 포함. |

처음 회귀는 새 `probe` 진단 API 부재로 실패했다. 이후 actual shared-cache test의 URI keyword 중복 문제를
fixture에서 수정했고 해당 실패를 production failure로 분류하지 않았다. 최종 full strict에는 skip/xfail로 숨긴 H2 test가 없다.

### Minimal repair and precise safety policy

- **`5e1a8b8`**: 고정 `select1_probe`의 stage, exception family, numeric SQLite code, allowlisted SQLite/errno
  family, connection_opened/close_succeeded/cleanup_failed만 기록한다. AppError context와 observer extraction에서
  두 차례 allowlist를 적용하며 raw exception/SQL/path/row/임의 symbol을 내보내지 않는다.
  `SqliteDatabase.probe`는 기존 connect/PRAGMA/busy deadline/reader executor를 공유하는 고정 read operation이다.
  Application data transaction/API, journal, schema, dependency, credential/config 값은 변경하지 않았다.
- **허용 조건 모두 일치해야 함**: database_unavailable + select1_probe + probe_configure +
  sqlite_operational + exact numeric5 + family busy + connection_opened=true + close_succeeded=true + cleanup_failed=false.
  Extended BUSY와 LOCKED도 허용하지 않는다. 재현한 subtype 이외 일반 DB 오류의 global downgrade는 없다.
- 직전 readiness가 유효하고 pending recovery가 없으며 최근60초 동안 허용 BUSY가 없을 때만1회
  `database.probe_contention`으로 기록한다. 실패 metric/history는 그대로 증가한다. 추가 요청/retry/backoff를
  만들지 않고 기존5초 정기 probe에서 **15초 미만에 연속 정상2회**를 요구한다.
- 회복 중 readiness가 사라지거나15초 만료/60초 내 두 번째 failure/정리 실패/다른 오류이면 HARD.
  Terminal failure는 readiness를 latch하고 다음 probe scheduling을 중단한다. 임의 성공1회로 terminal 상태를 풀지 않는다.
  Release/DB/schema/credential/writer/restart/resource/public-route 안전 조건은 계속 독립적으로 즉시 적용한다.
- **`ecd391f`**: terminal probe의 deadline/capacity 등 최상위 code가 database_unavailable이 아닌 경우도
  `database.probe_failed` event/count 자체로 HARD STOP을 유지한다. 최근 event tail에서 사라져도 누적 count가 보존한다.
- **`1014a08`**: stopped verifier를 최신92 pin/678e93 DB/8개 preservation에 맞추고 boot/timer disabled,
  header metadata 검증을 추가했다. H1 ACL 검사는 그대로 사용한다.

### Exact final candidate and verification

- Runtime source **`ecd391ff4548b7bda572ef916c30be296b714f94`**.
- Source archive SHA256 **`6d75f95d151c954cc84b3ee309b085ae954896cdeaaede143f1c882fb68f3418`**.
- 유일한 다음 승인 후보 immutable release **`r-ecd391ff4548b7bd-3dac82a792fad576`**.
- Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`** 불변.
- Manifest **`f023b1fa6d412b81300a9dd64a1ed584b653fd3040513399d14e755421d8ea6a`**;
  **17416 files / schema range [5, 5] / immutable validation PASS**.
- Focused data/operations363 PASS 후 verifier header3/terminal-error5 회귀를 추가했다.
  최종 Windows 전체 strict **978 PASS/0 skip/0 xfail/0 fail/0 error**,79.62초,
  RuntimeWarning/PytestUnraisableExceptionWarning error 및 xfail_strict, 기존 audioop deprecation1.
  새 H2 test는 data57/policy23/header3 = **83개**, 최종 전체에 모두 포함됐다.
- Exact-source Pi ARM64 **969 PASS/9 intentional skips/0 fail/0 error/0 xfail**,
  build+strict+immutable verification 168.827초. PrivateNetwork/production paths inaccessible인 nonroot
  격리 build/test service에서 승인된 기존 wheelhouse만 사용했다. 실제 운영 DB/서비스 요청 없음.
- 최종 상태 **verified_not_activated**; 세 application credential scopes + 세 root observer views PASS,
  readonly/exact/direct-source-denied, current pin/config/canonical/protected inventory/8개 preservation 불변 확인.
- 중간1014 source도 Windows973/Pi964+9 skip으로 검증됐으나, terminal probe HARD 정책 보완 뒤 final ecd에서
  두 플랫폼 full strict를 다시 실행했다. 중간 release는 **미활성·미승인 superseded build evidence**로 보존하며,
  다음 activation 후보로 제시하거나 별도 pin 승인 대상으로 삼지 않는다.

Pi Node-less browser skip9개는 아래 **동일 testcase 이름의 final Windows PASS와 일대일 대조**했다.
이는 harness 검증이고 PC Chrome/public-path live PASS는 아니다.

- `test_shipped_watch_browser_client[iframe-independent-presence]`
- `test_shipped_watch_browser_client[empty-player-protocol]`
- `test_shipped_watch_browser_client[hydrate-before-player]`
- `test_shipped_watch_browser_client[recoverable-return]`
- `test_shipped_watch_browser_client[terminal-stays-closed]`
- `test_shipped_watch_browser_client[page-lifecycle]`
- `test_shipped_watch_browser_client[bounded-reconnect]`
- `test_shipped_watch_browser_client[return-open-probe]`
- `test_shipped_watch_browser_client[select-before-player]`

### Preservations and publication boundary

아래 모든 path는 `/var/lib/discordbot/` 아래이며 DB SHA256 기준이다. 전체 directory inventory도 빌드 전후
일치했다. Latest canonical은 마지막 행과 같고, 이 작업에서 어떤 보존본도 덮어쓰지 않았다.

| Preservation | DB SHA256 |
| --- | --- |
| `phase10-precutover-63c7722/failed-attempt` | `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af` |
| `phase10-retry-368c8ebf7cbf-favorites-failed-20260919T065256492640Z` | `fab61bdda1dd2c8b664c5fd19525d1cdd46f20c82d630a94ce2ed4caf6f5cc65` |
| `phase10-retry-368c8ebf7cbff244-favorites-resume-guard-preservation` | `fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f` |
| `phase10-retry-49639828a3c2f181-operator-failed-20260919T092351777156Z` | `28291bf37128dd62815c818ac45865c8a504cc04a2b3dbb9a8a564d8226dab1d` |
| `phase10-retry-d14eba80bdec9126-live-smoke-guard-preservation` | `1d871bed4ba8b8fe4fd9426cfa15c8b373f700baca2f548f5cea571570252363` |
| `phase10-retry-2c768ec98d1fc8b1-live-smoke-guard-preservation` | `6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099` |
| `phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01-guard-preservation` | `f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` |
| `phase10-retry-92c25546af6b4904-live-smoke-h1-full-sweep-20260919-01-guard-preservation` | `678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66` |

원격 `codex/rebuild-v2=af37aa58a17753663ff33543e487da6455318cc9`,
`main=8432fdef40cddc131176fa875e350660dc897e12` read-back 불변.
미게시 source range **af37aa58…→ecd391ff…:4 commits/16 new blobs**(기존 live 결과 docs commit e15f062 포함).
각 range commit tree/message/blob의 forbidden artifact/secret pattern 검사 finding0.
이후 tail은 이 전용 보고서/current plan만 변경하는 docs-only 기록이며 최종 HEAD/range를 다시 검사한다.
최종 docs-only tail을 포함한 게시 예정 범위는5 commits/18 new blobs다. 최종 검사 결과와 HEAD는
`h2-git-audit-<HEAD>.json` 및 통합 승인 요청에 고정한다. 문서 구조·relative link2 PASS와 diff whitespace 검사도 통과했다.
사용자 미추적 handoff/zip은 수정·추가하지 않았다. 새 runtime/safety code 변경 **있음**;
dependency/config/schema/DB mode/location 변경 **없음**. Main/force/rebase/history rewrite 없음.

안전한 evidence: `h2-stopped-baseline.json`, `h2-focused.xml`, `h2-windows-ecd391ff4548.xml`,
`retry-build-ecd391ff4548.json`, `h2-cross-platform.json`, `h2-git-audit-*.json`.
Production 상태/30-gate 판정은 바로 아래 H2 live continuation의 **PASS3/BLOCKED27** 그대로다.
새 audible Music/TTS·Chrome/Watch·backup/restore/boot/timer/final-observation PASS는 없다.

**다음 단계는 한 번의 통합 승인**: final ecd391ff runtime + 이후 report/current-plan docs-only tail의
normal FF push, 위 exact immutable pin의 activation, newest678e93 canonical DB를 유지한 단일 bounded30-gate
full-sweep. 승인 전 push/production activation은 하지 않는다. 단순 재시도 대신 subtype·stage·cleanup evidence를
수집하며, generic DB failure와 검증 범위 밖 오류는 계속 HARD STOP/new preservation 대상으로 남긴다.
Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy cleanup은 시작하지 않는다.

## Continuation — approved H1 retry / H2 DB probe HARD STOP / preservation VERIFIED

2026-09-19 exact candidate 승인에 따라 단일 bounded full-sweep을 실행했다.
**PHASE 10B INCOMPLETE — STOPPED AND PRESERVED.** H1 ACL correction은 실제 production credential
검사에서 통과했다. 별개 **H2 `database.probe_failed / database_unavailable` HARD STOP**으로
감시기가 두 서비스를 정지하고 새 보존본을 생성했다. 원인을 확정하거나 safety 정책을 완화하지 않았다.
아래가 최신 상태이며, 이전 continuation의 승인 대기/787 pin/7개 보존본 상태보다 우선한다.

### Publication, exact identity and admission

- Runtime source **`92c25546af6b49044e17ed2a705a7cdf885532a0`**;
  current immutable pin **`r-92c25546af6b4904-3dac82a792fad576`**.
- Dependency `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`;
  manifest `fcc5d91f65aaf29b19018fa16f5e833f41e69e05d6b262b0c47780ac2b76e543`,17411 files/schema[5,5].
- Push 직전1715c1f…→**`af37aa58a17753663ff33543e487da6455318cc9`**의4 commits/11 new blobs와
  각 commit tree/message를 재검사했다. Runtime92 이후 전용 report/current-plan docs-only,
  source/dependency 변경0, secret/.env/DB/SQL/backup/private key/credential/운영 데이터 finding0.
  기존 `codex/rebuild-v2`에 normal FF push 후 exact af37aa58… remote read-back 완료.
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변; force/rebase/history rewrite 없음.
  미추적 사용자 handoff/zip은 추가·수정하지 않았다. 실행 결과 문서는 이 push 이후 로컬에서 갱신했다.
- 승인 후보의 exact tests: Windows895 PASS/0 skip/0 xfail; Pi886 PASS/9 intentional Node-less
  Watch skips/0 fail/0 error/0 xfail. 동일9개 Windows PASS 대조 완료. 상세 및 최초 잘못된 Windows
  runner 실패는 바로 아래 역사적 H1 검증 절에 남겼다. 이번 실행 중 runtime/dependency 변경0.
- Fresh preflight `verified_stopped_ready_for_approved_start`: canonical f47fbef…/schema5/integrity,
  config `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`, 모든 기존7개
  preservation/protected inventory, stopped writers/extra Python·media0/listeners0 확인.
  Boot/backup/update/manual timers disabled/inactive, exact credential scopes 및 direct source access denied,
  세 root credential observer view PASS. Public Watch9000 route1/internal9001·9010·9011 route0.
  Candidate replay/old restore/remigration/down-migration/V1 start 없음.

### Activation and H2 evidence

- Unique run **`h1-full-sweep-20260919-01`**, 새 root marker/observer path/preservation target 사용.
  22:33:37.702774 KST start →22:34:02.566434 ready, **24.856초/70초 PASS**.
  Discord/Watch exact release/Gateway/command sync/NRestarts0 및 live corrected credential safety PASS.
- Observer **354.569초/17 samples** 뒤 `guard_stopped_pair`; diagnostic에는
  `database.probe_failed=1`, `database_unavailable=1`, SOFT FAIL0, journal exit0/truncation false.
  전체 검사를 끝낸 정상 final observation이 아니라 HARD STOP까지의 부분 관찰이다.
  실제 sampling은 immutable inventory 검사 등을 포함해 약20–21초 간격이었다. 5초 간격이라 주장하지 않는다.
- 마지막 sampled health: Discord probe67 ok; Watch66 ok/1 failed. 두 health는 그 snapshot에서 ready=true였고
  Watch `database_recent_failures=2`였다. Adapter가 한 요청의 worker/awaiter failure를 각각 기록하므로
  이 수치를 독립적인 DB 장애2건으로 해석하지 않는다. Journal의 typed DB failure로 guard가 정지했다.
- 같은 마지막 safety 검사: schema5/integrity/identity/credential_scope/writer_scope/route verified.
  Restart0, Music processes0, cache5 files/6,567,679 bytes, Watch sessions0/clients0,
  telemetry/metric dropped0. 서비스 정보는 정지 직전 snapshot이고 정지 후 상태는 아래 inspector로 별도 검증했다.
- 정지 직전 RSS Discord82,292 KiB/Watch68,672 KiB, FD10/10, threads6/4,
  disk free105,053,290,496 bytes, temperature63.9°C/throttling0, audit156 files/32,570 bytes.
  Backup0/age−1은 최초 실제 production backup 미완료를 뜻하며 PASS가 아니다.

**확인된 범위와 미확정 원인:** 실패는 Watch process의 주기적 `SELECT 1` probe 경로다.
`storage/adapters/execution.py`는 여러 SQLite 오류와 filesystem OSError를 `database_unavailable`로
분류하지만 `operations/adapters/probe.py`는 최상위 error_code만 emit한다. 따라서 이번 telemetry로
SQLITE_BUSY/LOCKED/IO/permission 등의 세부 원인을 구분할 수 없다. 원문 DB/credential/log를 노출해
추측을 보완하지 않는다. 이번 정지 뒤 무결성 PASS는 corruption 증거가 없음을 보여 주지만,
일시적인 DB 접근 실패를 배제하지 않는다. H1 재발·credential 노출·Gemini quota·Music 원인으로 결론내리지 않는다.

### Current 30-gate matrix — this release only

**PASS3 / BLOCKED27 / functional FAIL0 / safety HARD STOP1.** 기본 기능 확인 안내 후 보고 시점까지
새 release의 사용자 성공/실패 답변을 받지 못했다. 4–30은 H2로 현재 검증이 차단되었으며,
사용자가 실제 실행하지 않았다고 단정하는 의미는 아니다. 뒤늦은 답변은 정지 전 실행임을 확인해 별도로 반영한다.
과거 Music/TTS/Chrome PASS는 승계하지 않는다. SOFT FAIL 때문에 independent gates를 생략한 것이 아니다.

| # | Gate | Result |
| --- | --- | --- |
| 1 | bounded startup | PASS |
| 2 | Gateway ready | PASS |
| 3 | command sync | PASS |
| 4 | /내정보 | BLOCKED BY H2 database_unavailable HARD STOP |
| 5 | /랭킹 | BLOCKED BY H2 database_unavailable HARD STOP |
| 6 | /요약 | BLOCKED BY H2 database_unavailable HARD STOP |
| 7 | 💾 보관함 | BLOCKED BY H2 database_unavailable HARD STOP |
| 8 | dashboard / stored volume | BLOCKED BY H2 database_unavailable HARD STOP |
| 9 | Music URL request | BLOCKED BY H2 database_unavailable HARD STOP |
| 10 | Music search request | BLOCKED BY H2 database_unavailable HARD STOP |
| 11 | result selection | BLOCKED BY H2 database_unavailable HARD STOP |
| 12 | queue addition | BLOCKED BY H2 database_unavailable HARD STOP |
| 13 | actual human-audible Music | BLOCKED BY H2 database_unavailable HARD STOP |
| 14 | normal stop | BLOCKED BY H2 database_unavailable HARD STOP |
| 15 | voice disconnect | BLOCKED BY H2 database_unavailable HARD STOP |
| 16 | join TTS actual audibility | BLOCKED BY H2 database_unavailable HARD STOP |
| 17 | TTS not overwritten by Music | BLOCKED BY H2 database_unavailable HARD STOP |
| 18 | Music after TTS completion | BLOCKED BY H2 database_unavailable HARD STOP |
| 19 | consecutive TTS / pause intent | BLOCKED BY H2 database_unavailable HARD STOP |
| 20 | PC Chrome Watch create | BLOCKED BY H2 database_unavailable HARD STOP |
| 21 | Watch connect | BLOCKED BY H2 database_unavailable HARD STOP |
| 22 | viewer presence | BLOCKED BY H2 database_unavailable HARD STOP |
| 23 | refresh | BLOCKED BY H2 database_unavailable HARD STOP |
| 24 | reconnect | BLOCKED BY H2 database_unavailable HARD STOP |
| 25 | tab leave / return | BLOCKED BY H2 database_unavailable HARD STOP |
| 26 | playback hydration | BLOCKED BY H2 database_unavailable HARD STOP |
| 27 | playback synchronization | BLOCKED BY H2 database_unavailable HARD STOP |
| 28 | normal Watch close | BLOCKED BY H2 database_unavailable HARD STOP |
| 29 | private admin close | BLOCKED BY H2 database_unavailable HARD STOP |
| 30 | actual public Chrome path | BLOCKED BY H2 database_unavailable HARD STOP |

Music/TTS audible 및 ordering 사용자 확인0, PC Chrome/public-path 사용자 확인0.
Telemetry/health/Cloudflare route 검증을 actual audio/browser PASS로 대체하지 않았다.
Service 자동 정지는 gate14/15의 정상 사용자 stop/voice-disconnect PASS가 아니다.

### Newest stopped state and preservation

- 자동 guard: pair_stopped/newest_state_preserved/inventory_verified 모두true.
  별도 sudo read-only inspector **`verified_stopped_preserved_integrity`** 완료.
- Pre-retry canonical SHA256 `f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` →
  **최신 canonical = 새 preserved DB `678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66`**. 최신 DB를 유지하며 f47로 되돌리지 않는다.
- 새 preservation: `/var/lib/discordbot/phase10-retry-92c25546af6b4904-live-smoke-h1-full-sweep-20260919-01-guard-preservation`.
  전체 inventory SHA256 **`6cb75333b6e47812a28a7d1bc1284fc0a03768852b713dcc42782035e08cc0e8`**.
  data/state/cache/backups/audit/config byte inventory 모두 current/copy 일치, fsync PASS.
  Canonical/copy schema5/integrity 및 counts/data/metadata checksum 일치. Read-only 검사 전후 protected inventory 불변.
- Counts favorites40/owners3, music_play_counts53, music_settings1, users15, watch sessions/playlists0.
  Data checksum `6c32578e5cf1109496f3ebbb86dc22c4b1f924e79275750c13bdb4d838295a16`;
  metadata checksum `318a1331957dd522d918b7915c73f3a3e8985e12f2a78dc6aedbdf14c44d2803`.
  Counts는 시작 전과 같지만 data/metadata hash는 변경됐다. 실제 row를 읽어 변경 내용을 추정하지 않는다.
  정상 종료 후 canonical/copy WAL/SHM/journal sidecars 없음을 확인했으며 별도 삭제하지 않았다.
- 기존7개 preservation/config 불변, 새 보존본 포함 총8개. Credential source7개 root0600 regular/nonsymlink;
  종료된 runtime credential mounts 없음. 이것을 종료 전 mount 검사 대신 사용하지 않는다.
- Production/staging/operations/guard inactive/MainPID0/NRestarts0. Production/staging boot 및
  backup/update/manual timers disabled/inactive. Auto-update OFF. Cloudflare Watch9000 route만 유지.

### Consolidated remediation / finalization boundary

| Group | Evidence and next requirement |
| --- | --- |
| A. application/runtime | H2 Watch DB probe failure confirmed; precise SQLite/filesystem cause unresolved. 다음 수정은 안전한 numeric error code/operation-stage 분류를 먼저 보존하고 synthetic multi-process SQLite/동시 reader·writer 조건에서 재현해야 한다. Runtime 재활성화 없이 준비하며, 재현 전 임의 busy timeout 증가나 failure 무시 금지. |
| B. external/provider | 이번 run에서 Summary/Music provider 실패 증거 없음. 이전503/음성 evidence를 이번 결과로 승계하지 않는다. |
| C. browser/integration | 이번 PC Chrome Watch evidence 없음; 전체 lifecycle/public-browser 검사는 H2로 차단. |
| D. operations/deployment | H1 정상 named-service ACL 검사 live PASS. H2 guard stop/new preservation/7개 old preservation 검증 PASS. 새 활성화는 이번 단일 실행 승인에 포함되지 않는다. |
| E. insufficient evidence | 27개 functional gates 및 DB 하위 원인 미확인. 정지 뒤 성공 요청을 다시 보내거나 과거 telemetry로 PASS 채우지 않는다. |

Mandatory live gates가 완료되지 않아 actual newest encrypted backup →private Bot-Data publication →remote
read-back/independent download/decrypt/schema/count/data/metadata/semantic/application restore를 **시작하지 않았다**.
Boot/4-hour timer enable 및 bounded final production observation도 **미실행**이다.
운영 pair는 정지 상태로 유지하고 이 승인에 따른 live 작업은 여기서 끝낸다.
Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy cleanup은 시작하지 않는다.

안전한 evidence: `h1-approved-preflight.json`, `h1-approved-push.json`, `h1-approved-start.json`,
`h1-observer-stopped.json`, `h1-observer-samples.jsonl`, `h1-approved-stop-inspection.json`,
`h1-approved-gates.json`. 로컬 `scratch/phase10`의 ignored safe 결과만 보고에 사용했고 원본 DB/로그/credential을
Git에 추가하지 않았다. 새 runtime 수정 없이 보고서와 current plan만 실제 결과로 갱신한다.
최종 문서 검증: tracked source archive에 변경된 보고 문서3개만 overlay하여 구조·relative link **2 PASS**;
사용자 미추적 handoff/zip은 검사 대상 archive에 넣지 않았다. `git diff --check` PASS, runtime/dependency diff0.

## Continuation — H1 ACL correction VERIFIED / new push-pin approval required

2026-09-19 사용자 지시에 따라 보고서 분리 뒤 같은 세션에서 H1 조사·격리 재현·최소 수정·후보 검증을 계속했다.
**PHASE 10B INCOMPLETE.** 이 continuation의 production activation/restart/provider request는0이다.
Current source/pin은787b3178908c08ffa926f41c64ae73753c39799a /
`r-787b3178908c08ff-3dac82a792fad576`, canonical DB는
`f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` 그대로다.
기존 일곱 preservation·설정·data/state/cache/backups/audit의 전체 inventory 불변을 Pi 재현 전후 확인했다.
Services stopped/boot·backup/update/manual timers disabled, auto-update OFF를 유지한다.
마지막 실제 [30-gate matrix](#single-current-30-gate-live-matrix)는 PASS3/BLOCKED27/functional FAIL0이며
새 준비 검사를 audible Music/TTS·Chrome PASS로 승계하지 않는다.

### Reporting split and reconstruction

- 별도 commit **`9829aa3`**에서 부모 보고서의 최신 full-sweep 두 절을 이 파일로 이동했다.
  이동한 내용은 relative runbook link와 마지막 빈 줄 외에 그대로이고, 부모의 초기2c 이하 역사적 본문은 불변이다.
  이동 대상 원문(normalized text) SHA256 `b2ea46bdf620c2fa2295f50c7c93feba74d2e124c82737c154dd2967ba991575`.
- 부모는 실제 기존 위치 `phases/phase-10/phase-10-report.md`를 유지하고 current production 요약·이관 링크만 둔다.
  새 전용 보고서는 요청한 `docs/rebuild/phase-10-full-sweep-report.md`다.
  Current plan/README는 PHASE10에서 두 보고서를 모두 읽고 책임별 최신 continuation을 우선하도록 안내한다.
  Tracked `master_prompt.txt`는 없어 별도 파일을 만들지 않았다.
- 문서 구조 검사의 root 파일 목록을 새 보고서에 맞게 변경했다. Tracked archive 기반 구조·링크 **2 PASS**.
  사용자 미추적 handoff/zip, evidence, DB, preservation, release, Git history를 제거하거나 수정하지 않았다.
  보고서 분리 커밋은 production 동작 변경과 분리했다.

### H1 evidence and classification

현재 H1은 **observer/application-validator 정책 불일치로 재현된 운영 검증 결함**으로 분류한다.
Credential 노출이 확인됐다는 의미는 아니다. 과거 정지된 mount 자체는 남아 있지 않으므로 당시 모든
접근 권한을 소급 증명하지 않으며, 아래 실제 Pi 격리 재현과 당시 HARD STOP을 구분한다.

- Pi **systemd255 (255.4-1ubuntu8.17)**에서 운영 Discord/Watch와 동일한 LoadCredential source binding을 typed D-Bus로 확인했다.
  운영 pair는 정지한 채, 별도 bounded transient unit의 network를 차단하고 production data/state/cache/backups/audit를
  접근 불가로 설정했다. Credential 내용은 읽지 않고 stat/ACL metadata 및 access 여부만 검사했다.
- Discord3/Watch2/operations3 entries **모두 root-owned regular/non-symlink0440**,
  exact service-user read-only ACL, read-only mount. Root와 해당 service UID 외 reader가 없는 ACL이며 service의 source 직접 접근은 거부됐다.
  모든 entry에서 application `private_mode` PASS, 이전 observer의 `st_mode & 0o077` predicate FAIL을 재현했다.
  안전한 결과 `h1-credential-reproduction-02.json`: **validator_policy_mismatch_reproduced**,
  protected_state_unchanged=true, preservation_count7, production_started=false, DB/provider/network 요청0.
- 첫 격리 도구는 `systemctl show LoadCredential`의 복합 속성을 단순 문자열로 비교하다 child 실행 전에 멈췄다.
  이를 credential security 실패로 분류하지 않는다. D-Bus `a(ss)` 방식으로 source 일치를 확인한 후
  새 경로02에서 재현했고01 evidence/run은 보존했다. Production 재시도나 provider blind retry가 아니다.
- 로컬 회귀에서 기존 predicate가 exact named-service ACL을 거부하는 실패를 먼저 기록했다.
  수정은 `private_mode`를 공유하여 같은 ACL 판정을 사용하며, credential bytes는 읽지 않는다.
  Root observer의 UID 대신 실제 configured `discordbot` UID와 runtime process owner 일치를 요구한다.
  Descriptor nofollow/nonblock/cloexec, 성공·실패 close, directory/file mount read-only를 검사한다.
  다른 UID, owning group/other reader, extra ACL, writer/malformed/missing ACL, symlink/nonregular,
  잘못된 owner 및 writable mount는 계속 `credential_permission` HARD STOP이다.
- 기존 strict/full-sweep SOFT FAIL 정책·Music/TTS/Watch 동작·dependency/schema/DB/config/credential 권한은 바꾸지 않았다.
  회귀에는 실제 shared ACL 검사기를 통과하는 observer loop와 잘못된 ACL에서 즉시 stop하는 loop를 포함했다.
  관련 ACL/observer **67 PASS**, 이 중 새 회귀24개. Summary503 뒤 정상 ACL에서는 independent Watch ready 유지,
  unsafe ACL에서는 HARD STOP 유지 확인. 이것은 synthetic evidence이며 live smoke가 아니다.

### Exact retry candidate and verification

- Fix commit **`391e415`**: observer ACL 정책 정렬 + 회귀 + changelog.
- Verifier commit/runtime source **`92c25546af6b49044e17ed2a705a7cdf885532a0`**:
  newest f47 DB·787 pin·7개 preservation에 stopped admission을 고정했다.
  후보의 root observer가 `/proc/<isolated PID>/root/run/credentials`를 직접 검사하는 세 scope 검증을 추가했다.
  Protected wheelhouse symlink metadata 검사는 sudo 이후 수행하되 symlink 거부는 유지한다.
- Exact source archive SHA256 **`236630a076e6c9f448378eab9dda5a0dda40ff1d632e975cfa608204bed8f87a`**.
  Dependency requirements와 승인된 wheelhouse는 변경하지 않았다.
- 첫 Windows 전체 검사: 기본 개발 venv의 Deno launcher 부재로 **894 PASS/1 FAIL**,
  65.17초. 원인은 `test_pinned_provider_and_runtime_load_without_network`의 실행 파일 부재로 확인했다.
  해당 실행을 PASS로 숨기지 않는다. 이미 존재하던 `windows-media-venv`의
  yt-dlp2026.8.19/EJS0.8.0/Deno2.9.7 pin과 launcher를 확인해 같은 archive에서 다시 검증한다.
- Exact pinned Windows full strict **895 PASS/0 skip/0 xfail**,63.80초,
  RuntimeWarning/PytestUnraisableExceptionWarning error 및 xfail_strict 적용; 기존 audioop deprecation warning1.
- Pi exact ARM64 **886 PASS/9 intentional Node-less Watch harness skips/0 failures/0 errors/0 xfails**,
  151.390초.9개 testcase name 모두 위 Windows895의 PASS와 대조 완료, 예상 밖 skip0.
  최종 상태 **verified_not_activated**.
- 새 immutable candidate **`r-92c25546af6b4904-3dac82a792fad576`**.
  Manifest **`fcc5d91f65aaf29b19018fa16f5e833f41e69e05d6b262b0c47780ac2b76e543`**,
  17411 files/schema[5,5], immutable inventory PASS.
  Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`** 불변.
- Pi Discord/Watch/operations 세 scope의 config/credential-format/exact scope/read-only/direct-source-denied 검사 PASS.
  별도로 새 safety code를 root에서 실행해 실제 isolated service의 `/proc/.../root/run/credentials`를 검사한
  **세 root observer view 모두 PASS**. 이 root probe는 credential contents/DB/network를 읽거나 요청하지 않았다.
  재현·빌드 전후 current pin·canonical f47·config41edd0…·7개 preservation 및 protected inventory 불변,
  production pair inactive/MainPID0/boot disabled, backup/update/manual timers disabled/inactive 재확인.
- 원격 read-back `codex/rebuild-v2=1715c1f5d1de80b8693996662985eb6221259968`,
  `main=8432fdef40cddc131176fa875e350660dc897e12` 그대로다. 이 continuation의 push0/activation0.
  Remote1715c1f..runtime92c2554 **3commits/9newblobs**, 모든 새 commit tree/message/blob의
  secret/.env/DB/SQL·backup/private key/credential/운영 data artifact 검사 PASS, findings0.
  이후 검증 결과는 이 보고서/current plan만 변경하는 docs-only tail로 기록한다.

안전한 증거: Pi `/home/os/discordbot-phase10/h1-credential-reproduction-02.json`,
`retry-build-92c25546af6b.json`; local ignored `h1-windows-pinned-92c25546af6b.xml`,
`h1-cross-platform.json`, `final-push-audit-92c25546af6b.json`. 최초 도구/runner 실패 evidence도 유지했다.

### Consolidated remediation state

| Group | Current finding | Remaining boundary |
| --- | --- | --- |
| A — runtime validator | Exact service ACL에 대한 observer/application 정책 불일치 수정·24개 새 회귀·전체 strict PASS | 새 candidate의 production 동작은 미검증 |
| B — provider | 이 continuation의 external provider 호출0 | Summary503/429 및 Music provider 상태는 다음 단일 live 요청에서만 판정; blind retry 금지 |
| C — browser/audio integration | 현재 production 기능 gate27개는 기존 H1로 BLOCKED | 실제 사용자 Music/TTS/order 및 PC Chrome public lifecycle 확인 필요 |
| D — operations | 동일 Pi systemd mount에서 과거 판정 거부/새 root 판정 PASS, metadata-only 재현 완료 | 새 push/pin 승인 후 fresh reconciliation·70초 readiness·bounded sweep 필요 |
| E — evidence limits | 당시 종료된 mount ACL은 남아 있지 않음. 노출을 보여주는 증거 없음 | 재현한 정상 mount의 정책 불일치와 과거 instance에 대한 증거 한계를 구분 |

### Remaining gate / approval boundary

이번 준비는 production 재활성화 승인이 아니다. 후보의 Windows/Pi/root metadata 검증과 source-range 검사를 완료했으며,
새 source/pin 일반 FF push와 production activation을 위 정확한 identity로 승인 요청한다.
승인 대상은 `codex/rebuild-v2`로 runtime92c2554 및 그 뒤 full-sweep report/current plan docs-only tail의
일반 FF push, pin `r-92c25546af6b4904-3dac82a792fad576`를 사용한 단일 bounded full-sweep retry다.
Push 직전 최종 HEAD/range/secret 검사와 새 canonical/config/release reconciliation을 다시 수행한다.
현재 마지막 live H1와27 BLOCKED는 실제 재검증 전까지 남는다. 승인 후에는 단일 bounded full-sweep에서
HARD STOP만 즉시 중단하고 일반 feature/provider SOFT FAIL은 기록 후 독립 gate를 계속한다.
Actual audible Music/TTS/order 및 PC Chrome public Watch 전 gate PASS 뒤에만
actual newest encrypted backup/private Bot-Data read-back/independent restore/boot/4h timer/final observation으로 진행한다.
DB replay/old restore/remigration/down-migration/V1 start·Audit·PHASE11·legacy cleanup은 진행하지 않는다.

## 10B continuation — APPROVED FULL SWEEP / CREDENTIAL HARD STOP

**PHASE 10B INCOMPLETE.** 2026-09-19 exact full-sweep 후보 승인을 받아 production activation을
1회 수행했다. 70초 readiness gate는 **24.870초**에 통과했으나 첫 안전 검사에서
`safety_invariant_failed / credential_permission` HARD STOP이 발생했다.
감시기가 두 서비스를 정지하고 최신 상태를 **새 일곱 번째 preservation**에 보존했다.
이것은 Summary/Music 기능 실패에 따른 과거 fail-first 중단이 아니다. 사용자 지정 HARD STOP 경계이며,
재시작·자동 재시도·runtime 수정 없이 정지 후 확인과 통합 보고만 진행한다.
아래가 현재 결과이며, 이후 절은 당시의 역사적 기록이다.

### Exact publication and activation evidence

- Approved runtime **`787b3178908c08ffa926f41c64ae73753c39799a`**;
  current immutable pin **`r-787b3178908c08ff-3dac82a792fad576`**.
- Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`**;
  manifest **`906c8bcad00c5e78f54a42dd67d2b56fc0c5022d6430c058c70dd4f1786314ad`**,
  17410 files/schema[5,5]. Source archive
  `ce1760794f196620d372ee30b808ca9b5ed17168f33058ea3b1afd97049e5bb6`.
- Normal FF push/read-back **`e616511b77f5eb4553c7ede4fffdf2f0e69acf2c`** to `codex/rebuild-v2`.
  Before-push range `686b946439ab5404cf194f8282f4559be245a1ea..e616511b77f5eb4553c7ede4fffdf2f0e69acf2c`:
  5 commits/17 new blobs, all new commit trees/messages/blobs inspected; actual secret/forbidden artifact/binary0.
  Runtime 이후 tail은 phase report/current plan 두 문서뿐이며 runtime/dependency 변경0.
  `main=8432fdef40cddc131176fa875e350660dc897e12` read-back 불변; force/rebase/history rewrite0.
  미추적 `gpt_handoff` 자료와 zip은 포함하거나 변경하지 않았다.
- Exact archive Windows **871 PASS/0 skip/0 xfail**, 65.39초;
  Pi **862 PASS/9 skip/0 failures/0 errors/0 xfail**, 155.342초.
  Pi9개는 Node 부재에 따른 의도된 Watch harness skip이며 같은9개 testcase의 Windows PASS 대조 완료.
  이 검증 결과를 실제 audible/Chrome PASS로 승계하지 않는다.
- Fresh stopped preflight: canonical
  **`6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099`**,
  schema5/integrity/현재·최신2c 보존본 inventory 일치 및 이전 보존본6개 전체 불변.
  Favorites40/owners3, play counts53/settings1/users15, Watch sessions0/queue0.
  Config **`41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`** 불변.
  세 credential scope exact/read-only/direct source access denied, 외부 login 없는 preflight PASS.
  `watch.lgw323.com → http://127.0.0.1:9000` route1/internal9001·9010·9011 route0.
- Activation은 code pointer만 변경했고 현재 canonical DB를 사용했다.
  DB promotion/replay/old restore/remigration/down-migration/V1 start0.
  2026-09-19 **21:17:00.664 KST** start → **21:17:25.540 KST** readiness.
  Discord/Watch ready=true, same approved release, NRestarts0.
  Discord readiness는 Gateway ready와 `DeferredMusic`의 `tree.sync()` 완료 후에만 true이므로
  Gateway/command sync의 기술 증거로 기록한다.

### Single current 30-gate live matrix

**H1 = 첫 full-sweep safety 검사 `credential_permission` HARD STOP으로 production pair가 정지됨.**
사용자 기능 검사 요청을 보내기 전 H1이 발생했다. 기능 gate를 FAIL이나 과거 PASS로 대체하지 않는다.

| # | Gate | Result | Evidence / dependency |
| --- | --- | --- | --- |
| 1 | Bounded startup (70s) | PASS | 24.870s, exact release ready |
| 2 | Gateway ready | PASS | current runtime readiness true |
| 3 | Command sync | PASS | readiness requires successful tree sync |
| 4 | `/내정보` | BLOCKED BY H1 | no current-release user test |
| 5 | `/랭킹` | BLOCKED BY H1 | no current-release user test |
| 6 | `/요약` | BLOCKED BY H1 | no current-release provider request |
| 7 | `💾 보관함` | BLOCKED BY H1 | no current-release user test |
| 8 | Dashboard / stored volume | BLOCKED BY H1 | no current-release user test |
| 9 | Music URL request | BLOCKED BY H1 | no current-release request |
| 10 | Music search request | BLOCKED BY H1 | no current-release request |
| 11 | Result selection | BLOCKED BY H1 | search path not executed |
| 12 | Queue addition | BLOCKED BY H1 | selection/add path not executed |
| 13 | Human-audible Music | BLOCKED BY H1 | no human confirmation |
| 14 | Normal stop | BLOCKED BY H1 | guard stop is not a normal Music stop test |
| 15 | Voice disconnect | BLOCKED BY H1 | no functional voice-disconnect test |
| 16 | Join TTS human audibility | BLOCKED BY H1 | no human confirmation |
| 17 | TTS not overwritten | BLOCKED BY H1 | no observed Music/TTS ordering |
| 18 | Music starts after TTS | BLOCKED BY H1 | no observed Music/TTS ordering |
| 19 | Consecutive TTS / pause intent | BLOCKED BY H1 | no independent live TTS/pause test |
| 20 | Chrome Watch create | BLOCKED BY H1 | no actual Chrome session |
| 21 | Watch connect | BLOCKED BY H1 | create/connect path not executed |
| 22 | Viewer presence | BLOCKED BY H1 | no actual Chrome session |
| 23 | Refresh | BLOCKED BY H1 | no actual Chrome session |
| 24 | Reconnect | BLOCKED BY H1 | no actual Chrome session |
| 25 | Tab leave / return | BLOCKED BY H1 | no actual Chrome session |
| 26 | Playback hydration | BLOCKED BY H1 | no actual Chrome session |
| 27 | Playback synchronization | BLOCKED BY H1 | no actual Chrome session |
| 28 | Normal Watch close | BLOCKED BY H1 | guard shutdown is not normal browser close |
| 29 | Private admin close | BLOCKED BY H1 | no current-release admin close test |
| 30 | Actual Cloudflare public browser path | BLOCKED BY H1 | route inspection alone is not Chrome evidence |

30개 중 **PASS3 / BLOCKED27 / 기능 FAIL0 / NOT TESTED0**. 별도 safety gate H1은 FAIL/HARD STOP이다.
SOFT FAIL0은 기능 성공을 뜻하지 않는다. 이 activation의 allowlisted Music/Summary event0,
safe error code0, journal exit0/truncation=false였으며 기능별 실제 요청이 수행되지 않았다.
실제 audible Music/TTS와 Chrome public-path evidence는 모두 없고 과거 청취·harness 결과와 구분한다.

### Stop, preservation and observation

- Observer result `guard_stopped_pair`, policy `full-sweep`, first safety result
  `RuntimeError / credential_permission`, trigger `safety_invariant_failed`.
  보존 결과 `pair_stopped=true / newest_state_preserved=true / inventory_verified=true`.
  후속 read-only systemd 확인에서 두 production unit 및 guard inactive/MainPID0/NRestarts0/Result=success.
- New preservation:
  `/var/lib/discordbot/phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01-guard-preservation`.
  기존 보존본 overwrite 없음. Current release pin은787 그대로이며 재활성화하지 않는다.
- 독립 sudo read-only 결과 **`verified_stopped_preserved_integrity`**.
  Canonical after = preserved DB SHA256
  **`f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748`**.
  두 DB schema5/integrity/count/data/metadata reconciliation PASS, WAL/SHM/journal sidecar 모두 없음.
  Data checksum **`d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`** 및
  Favorites40/owners3/play counts53/settings1/users15/Watch0/0 유지.
  Metadata checksum은 before `4cae0601ec1209414019e6028e1b702101f464e9fd928c06a647f0c3d4ff797d` →
  after **`4958e8f59c02677ade32e91da63f8c655bbab2ae2dd6a528a50304664f519933`**.
  최신 상태를 보존했으며 historical hash로 되돌리지 않았다.
- Data/state/cache/backups/audit/config 전체 원본·보존본 inventory 일치, fsync 확인,
  **이전 보존본6개 및 설정 전체 inventory 불변**, read-only 검사 전후 protected state 불변.
  새 preservation 전체 inventory SHA256
  **`6cb61f67b87d2bd7d7f699a7621bf88b476bec6b797e2cc075453386cabc1d7b`**.
  Production/staging/ops/guard inactive/MainPID0, production boot 및 backup/update/manual timer disabled/inactive.
- Source credential 파일7개 metadata는 모두 regular/non-symlink/root:root0600.
  정지 후 두 runtime credential mount는 실제로 없어져 당시 mount ACL은 이 검사로 재확인할 수 없다.
  Unit User/Group=discordbot, UMask0077, NoNewPrivileges=yes, ProtectSystem=strict, ProtectHome=yes.
  현재 Cloudflare invocation의 마지막 구성에서 public9000 route1/internal route0 재확인;
  actual browser path 성공으로 해석하지 않는다.
- Live observer는 **1 sample /22.105초**이며 그 시간에는 안전 검사·정지·보존이 포함된다.
  정상 운영 22초 관찰이나 완료 후 final observation으로 해석하지 않는다.
  첫 표본: Discord RSS82052KiB/FD11/threads6, Watch RSS68380KiB/FD10/threads3,
  Music child0/cache6567679bytes, Watch sessions0/clients0, DB recent failures0,
  telemetry/metric drops0, backup age-1/RPO exceeded1, audit154files/32101bytes,
  free disk105517568000bytes, temperature67.2°C/throttling0. NRestarts0.
  첫 actual production backup 이전이므로 backup age-1은 PASS가 아니다.
  Journal priority6 count26, safe feature event0; journal 사용량·장기 자원 추세는 측정하지 않았다.

### Consolidated failure and remediation matrix

| Group | Current evidence | Conclusion / later batch remediation |
| --- | --- | --- |
| A — application/runtime | 설정 검증의 `private_mode`는 exact named-service ACL을 검사하지만 `sweep-safety.py`는 `st_mode & 0o077`만으로 거부 | 두 검증기의 정책 불일치 확인. 승인 runtime은 그대로 두고, 향후 동일 ACL 정책·부정 사례·observer integration을 함께 검증할 것 |
| B — external/provider | 이번 Summary/Music provider request0, historical Summary503 및 Music 실패만 존재 | 현재 provider 상태/무료 quota 여부 미확정. 새 PASS/FAIL로 승계하거나 blind retry하지 않음 |
| C — browser/integration | 실제 PC Chrome Watch0, current audible Music/TTS confirmation0 | 모든 관련 gate H1 차단. Harness PASS는 실제 browser/audio 증거를 대체하지 않음 |
| D — operations/deployment | readiness PASS 뒤 credential permission HARD STOP, pair stop/new preservation 성공 | 감시기의 credential 판정으로 sweep 종료. Mode/ACL metadata와 실제 접근 범위를 구분해 후속 격리 검증 필요 |
| E — insufficient evidence | 실패 이벤트에 실제 credential mode/ACL/파일 종류 세부 값이 없고 정지 후 두 mount 부재 확인 | 실제 노출인지 정상 ACL 오탐인지 이 이벤트만으로 확정하지 않음. Source 파일0600은 mount ACL의 대체 증거가 아님. 후속 검사는 값 없이 metadata만 사용 |

정지 후 값 없는 합성 ACL 검사에서 root-owned0440/named-service-read-only ACL은 기존 application validator가
허용하고 새 observer predicate는 거부하는 차이를 재현했다. 기존 ACL 회귀 **10 PASS/0 skip**, 0.35초.
이는 코드 정책 불일치의 증거이며 실패 당시 mount의 실제 ACL을 복원한 증거는 아니다.
Source/dependency/설정/실제 credential 권한을 변경하지 않았다.
최종 보고 두 문서의 tracked archive 문서 구조·링크 검사 **2 PASS**; 사용자 미추적 handoff는 검사용 archive에 포함하지 않았다.

안전한 증거 파일은 Pi `/home/os/discordbot-phase10/`의
`full-sweep-approved-preflight.json`, `full-sweep-approved-start.json`, `full-sweep-approved-push.json`,
`full-sweep-approved-stop-inspection.json`과
`/var/tmp/phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01/summary.json`이다.
원문 DB/개인 ID/음악 제목·URL/secret 값 없이 집계·identity·안전한 오류 분류만 보고했다.

Actual newest production encrypted backup → private Bot-Data publication/read-back/independent download →
decrypt/schema/count/data/metadata/semantic/application restore는 **BLOCKED BY H1 and incomplete live gates**.
실행·성공 identity 없음. Boot enable/4h backup timer enable/final bounded production observation도 진행하지 않았다.
Auto-update 및 manual source polling은 OFF를 유지한다. Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy정리0.
최종 보고서만 갱신하고 중단하며 새 runtime 수정·push/pin 재시도는 이 실행에 포함하지 않는다.

## 10B continuation — FULL-SWEEP POLICY VERIFIED / NEW RUNTIME APPROVAL REQUIRED

2026-09-19 새 사용자 지시로 fail-first 검사를 HARD STOP / SOFT FAIL의 단일 bounded full-sweep로 변경했다.
일반 기능 실패는 독립 gate를 막지 않고 수집한다. 이 세션에서 production activation은 **0회**다.
현재 production은 정지한2c pin이며 새 정책 release를 활성화한 것으로 기록하지 않는다.
**PHASE 10B INCOMPLETE**. 아래는 정책 구현·검증과 다음 live sweep의 승인 경계다.

### Verified current state and candidate

- Actual current source `2c768ec98d1fc8b1325f88cdfa1558bc6972d551`, pin
  `r-2c768ec98d1fc8b1-3dac82a792fad576` 유지.
- 새 runtime source **`787b3178908c08ffa926f41c64ae73753c39799a`**.
  정책fa53f3f, 최신 stopped verifier c72428e, probe connection 정리787b317의 원자적 로컬 commits.
  Dependency 변경 없음: `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`.
  정확한 Git archive SHA256 `ce1760794f196620d372ee30b808ca9b5ed17168f33058ea3b1afd97049e5bb6`.
- Candidate **`r-787b3178908c08ff-3dac82a792fad576`**, stage **verified_not_activated**.
  Pi exact ARM64 full strict **862 PASS /9 intentional Node-less Watch skips/0 failures/0 errors/0 xfails**,
  155.342초. 동일9개 testcase name의 Windows PASS 대조 완료, 예상 밖 skip0.
  Manifest **`906c8bcad00c5e78f54a42dd67d2b56fc0c5022d6430c058c70dd4f1786314ad`**,
  17410 files/schema[5,5]/immutable inventory와 세 credential scope 검증 PASS.
  Windows exact archive full strict **871 PASS /0 skip/0 xfail**,
  65.39초, 기존 Python3.12 audioop deprecation warning1. 새 정책/actor/marker/DB-close 회귀34개 포함.
  관련 Music/Summary/observer258 PASS 뒤 최종 DB-close regression24 PASS. 최종 문서 링크/구조2 PASS.
- 중간 후보c72428e는 Windows870 PASS, Pi861 PASS/Node-less Watch9 skip/0 failures/0 errors,
  154.328초였으나 최종 후보가 아니다. 서비스에 활성화하지 않았으며 immutable 보존한다.
- Remote 재조회: `codex/rebuild-v2=686b946439ab5404cf194f8282f4559be245a1ea`,
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변. 이 세션 push0/force0/rebase0/history rewrite0.
  787b317까지 원격686b946 기준4 commits/15 new blobs·모든 새 commit tree/message 검사에서 secret/금지 artifact0.
  새 runtime push/pin 승인은 아직 받지 않았다. 최종 보고 문서 tail은 source 뒤 docs-only로 별도 기록한다.
- Fresh sudo read-only `sweep-stopped-preflight.json`: current/schema5/integrity/manifest17406 files,
  data/state/cache/backups/audit/config 및 기존 **보존본6개 전체 inventory 불변**.
  Canonical before=after **`6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099`**,
  최신2c preservation과 동일. 다른 DB로 되돌리거나 후보를 replay하지 않았다.
  Favorites40/owners3, play counts53/settings1/users15, Watch0/0.
  Data checksum `d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`,
  metadata `4cae0601ec1209414019e6028e1b702101f464e9fd928c06a647f0c3d4ff797d` 유지.
  Config `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 유지.
- Production/staging/ops services inactive/MainPID0, boot·backup/update/manual timers disabled/inactive.
  Auto-update OFF. Pi 추가 Python/media process0, runtime listener0 확인. 다른 host writer 부재를 이 검사만으로
  단정하지 않는다. 세 credential scope exact/read-only/direct source access denied, 외부 login0.
  Public route `watch.lgw323.com → http://127.0.0.1:9000`1개, internal9001/9010/9011 public route0.
  실제 Chrome 검증과 구분한다. 미추적 gpt_handoff/zip은 건드리지 않았다.

### Why the external observer alone cannot implement this sweep

2c `MusicActor._stop_for_smoke`는 첫 기능 실패에서 admission을 영구 잠그며
`DiscordFeatures.ready()`도 false가 된다. Summary trigger만 observer에서 제거하면 Music URL 실패 뒤
검색·독립TTS가 거부되고 결국 readiness HARD STOP으로 Watch도 막힌다. Marker 제거는 정상 retry를
재활성화하므로 no-blind-retry 요구에 어긋난다. 따라서 외부 observer만의 변경으로 충분하다고 주장하지 않는다.
사용자 첨부3절의 “If this requires changing runtime code ... obtain the required approval before activation”에
따라 새 exact source/release 검증 후 push/pin 승인을 받는다. 2c 승인 범위를 임의로 확장하지 않는다.

### Policy and regression evidence

- Root-owned, group/other non-writable, exact release, started/expires 최대1800초 JSON marker와
  `--policy full-sweep --run-id UNIQUE`를 동시에 요구한다. 기본 runtime 및 strict observer 정책 유지.
- Summary503/429·일반 Music/TTS/UI/command 기능 실패는 safe category/status를 남기고 SOFT FAIL.
  새 명시적 검색·정지/퇴장·독립 TTS는 허용하고, 실패한 current media와 대기 작업의 자동 retry/autoplay는 막는다.
  실패 current가 있는 상태에서 다른 취득 경로를 실제 재생하려면 기존 정지/퇴장으로 먼저 명시적으로 정리한다.
  독립TTS 완료가 기존 실패 media를 자동 재취득하지 않는 회귀도 통과했다.
- DB typed corruption/unavailable, schema/ledger/quick-check, exact release/dependency/config,
  writer/credential scope/public route, restart/crash, readiness 연속3회, 기존 resource cap·child capacity,
  관찰된 task.retrying, diagnostic coverage loss와 operator emergency는 HARD STOP이다.
  보존은 stop → unique copy → fsync → 전체 inventory 일치이며 기존 보존본 overwrite/restore 없음.
  DB read-only probe는 성공·예외 모두 connection을 명시적으로 닫는다.
- Fake clock의 실제 observer loop에서 Summary503 → Music prepare 실패 → TTS 실패 뒤에도
  Watch ready를 유지하며 다음 표본을 관찰했다. 정지는 지정 deadline에서1회 발생했다.
  이 synthetic 증거를 실제 Chrome/audible PASS로 기록하지 않는다. 실제 외부 provider 재시도0.
- Deadline/finish는 controlled stop·새 preservation. 전30 gate PASS와 사용자 실제 audio/Chrome 확인 및
  이미 active인 replacement post-cutover guard를 모두 확인해야 서비스 중단 없는 finalization handoff 허용.
  자세한 operator 절차·dependency 처리·rollback은 [cutover runbook](phases/phase-10/cutover-runbook.md) 최신 절을 따른다.

### Single current full-sweep gate matrix

아래는 **새 full-sweep 후보**의 live 결과다. 승인 전이므로 과거2c PASS를 승계하지 않는다.
현재 선행 조건은 검증된 새 runtime의 push/pin 승인이다. Pi 격리 검증은 완료됐으며 실제 live는 미실행이다.

| # | Gate | Current result |
| --- | --- | --- |
| 1 | Bounded startup (70s) | NOT TESTED — new runtime approval pending |
| 2 | Gateway ready | NOT TESTED — new runtime approval pending |
| 3 | Command sync | NOT TESTED — new runtime approval pending |
| 4 | `/내정보` | NOT TESTED — new runtime approval pending |
| 5 | `/랭킹` | NOT TESTED — new runtime approval pending |
| 6 | `/요약` | NOT TESTED — new runtime approval pending |
| 7 | `💾 보관함` | NOT TESTED — new runtime approval pending |
| 8 | Dashboard / stored volume | NOT TESTED — new runtime approval pending |
| 9 | Music URL request | NOT TESTED — new runtime approval pending |
| 10 | Music search request | NOT TESTED — new runtime approval pending |
| 11 | Result selection | NOT TESTED — new runtime approval pending |
| 12 | Queue addition | NOT TESTED — new runtime approval pending |
| 13 | Human-audible Music | NOT TESTED — new runtime approval pending |
| 14 | Normal stop | NOT TESTED — new runtime approval pending |
| 15 | Voice disconnect | NOT TESTED — new runtime approval pending |
| 16 | Join TTS human audibility | NOT TESTED — new runtime approval pending |
| 17 | TTS not overwritten | NOT TESTED — new runtime approval pending |
| 18 | Music starts after TTS | NOT TESTED — new runtime approval pending |
| 19 | Consecutive TTS / pause intent (if applicable) | NOT TESTED — new runtime approval pending |
| 20 | Chrome Watch create | NOT TESTED — new runtime approval pending |
| 21 | Watch connect | NOT TESTED — new runtime approval pending |
| 22 | Viewer presence | NOT TESTED — new runtime approval pending |
| 23 | Refresh | NOT TESTED — new runtime approval pending |
| 24 | Reconnect | NOT TESTED — new runtime approval pending |
| 25 | Tab leave / return | NOT TESTED — new runtime approval pending |
| 26 | Hydration | NOT TESTED — new runtime approval pending |
| 27 | Synchronization | NOT TESTED — new runtime approval pending |
| 28 | Close | NOT TESTED — new runtime approval pending |
| 29 | Private admin close | NOT TESTED — new runtime approval pending |
| 30 | Actual Cloudflare public browser path | NOT TESTED — new runtime approval pending |
| 31 | Actual production encrypted backup / Bot-Data publication / read-back | NOT TESTED — all live gates prerequisite |
| 32 | Independent download/decrypt/schema/count/semantic/application restore | NOT TESTED — production backup prerequisite |
| 33 | Production boot /4h backup timer | NOT TESTED — restore prerequisite; disabled |
| 34 | Final bounded production observation | NOT TESTED — finalization prerequisite |

### Consolidated remediation and evidence boundary

| Group / stage | Safe category / policy | Independent continuation / blocked gates | Supported layer / repair evidence |
| --- | --- | --- | --- |
| A — full-sweep Music admission | validation policy limitation; code prepared | New mode permits explicit search/TTS; actual gates await approval | Existing fail-fast latch/ready coupling confirmed; focused and full strict tests |
| B — prior2c Summary | `external_temporary/http_server_error/503`; SOFT FAIL in new mode | Must continue Music/TTS/Watch; no dependent blocking | External provider response confirmed historically; current availability/quota unknown; one intended live request required |
| C — Watch/Chrome integration | insufficient live evidence | All browser lifecycle checks remain independently required | No new browser defect established; actual PC Chrome public path needed |
| D — observer workflow | old Summary/Music fail-first policy; replaced only for bounded mode | New guard classifies safety separately; no automatic request retry | Synthetic multi-failure loop and safety tests; actual live observer not yet exercised |
| E — audible Music/TTS/input | insufficient exact-release evidence | Prior Music no-response followed Summary stop; no isolated active-runtime failure proven | Need fresh URL/search, actual hearing/order, normal stop/disconnect and pause checks |

이번은 승인 대기 준비 결과이며 실행한 full-sweep의 완료 결과가 아니다. 원래 사용자 목적은 아직 남아 있다.
일반 feature bug를 live 중 하나씩 고치거나 provider/model/config/dependency를 바꾸지 않았다.
새 canonical preservation 생성0(서비스 시작0), 기존6개 identities는 바로 아래 보존 이력 표와 동일하다.
Actual backup/publication/restore/boot/timer/완료 후 observation0. Audit/PHASE11/V1 삭제/legacy cleanup0.
최종 검증을 완료했다. Exact new source787b317/pin r-787b3178908c08ff-3dac82a792fad576와
보고 docs-only tail의 일반 FF push 및 단일 full-sweep activation을 승인 요청한다.
Safe evidence: `sweep-stopped-preflight.json`, `retry-build-787b3178908c.json`,
local `full-sweep-final-windows.xml`, `full-sweep-cross-platform.json`.
**Final verdict: PHASE 10B INCOMPLETE — policy verified, production sweep awaiting required new-runtime approval.**
