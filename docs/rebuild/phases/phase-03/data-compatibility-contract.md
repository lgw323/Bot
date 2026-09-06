# PHASE 3 Data Compatibility Contract

2026-09-05 사용자 PHASE 3 지시와 current ADR-002/010/013/014/017/018을 따른다.
이 계층은 V1 route, Discord/Watch process, Pi 또는 운영 데이터 경로에 연결하지 않았다.

## Boundaries and ownership

- `engagement/ports/repository.py`, `music/ports/repository.py`, `watch/ports/repository.py`는
  frozen DTO, Python scalar와 명시적 `DatabaseRequest`만 노출한다. SQLite row/connection,
  Fernet, Discord/FastAPI type은 외부 계약에 없다.
- 기능별 `adapters/sqlite_repository.py`가 parameterized SQL을 소유한다. 공통 connection,
  schema/ledger/backup은 `storage/adapters/`, vendor-neutral 설정·요청·검증 결과는
  `storage/ports/`에 둔다. storage는 비즈니스 context를 import하지 않는다.
- application/ports는 storage ports만, feature adapter는 storage adapters/ports만 사용할 수
  있다. domain의 storage import, application의 executor/composition import는 금지한다.
- `SqliteDatabase`는 주입 가능한 required `ManagedResource`다. `start()`가 read-only
  validation을 통과해야 다음 capability가 시작한다. production composition 변경은 없다.
- Watch repository는 조회만 제공한다. Watch session write owner와 lifecycle은 PHASE 6,
  play-count 증가·top-50 정책·playback idempotency는 PHASE 7에서 연결한다.

## Stored meaning

| 데이터 | 유지 계약 |
| --- | --- |
| users | 기존 `(user_id,guild_id)`, xp, level과 초 값을 그대로 읽고 보존한다. 소수 voice seconds를 정수로 바꾸거나 XP 공식을 적용하지 않는다. |
| legacy global users | `(user,0)` 행을 삭제·병합하지 않는다. 일반 membership 조회는 양수 guild를 요구한다. favorites 저장은 새로운 가짜 membership을 만들지 않는다. |
| birthday | null pair와 기존 값을 보존한다. 과거 잘못된 calendar 날짜는 aggregate warning이며 자동 정정하지 않는다. 새 입력의 calendar 정책은 PHASE 4 application 책임이다. |
| favorites | `(user_id,url)` 공용 목록. URL 원문·제목·따옴표·Unicode·줄바꿈을 보존하며 guild 범위를 추가하지 않는다. |
| music settings | 저장된 volume 그대로. 저장 행 부재는 `None`으로 전달하며 새 session의 0.5 default는 PHASE 7에서 결정한다. |
| play counts | 기존 guild/URL/title/count를 읽고 50개 초과 synthetic history도 자르지 않는다. 과거 count를 재계산하지 않는다. |
| Watch | guild와 session을 함께 검사한다. playlist query도 session→guild join을 거친다. timestamp/channel/message와 order_index를 보존한다. |

목록은 정해진 정렬과 `limit/offset` pagination을 제공한다. 이는 저장 데이터 삭제나 Discord UI
pagination 구현이 아니다. 목록이 변하는 동안의 stable UI selection은 담당 feature Phase에서
stable key를 사용한다. DTO의 repr에는 사용자 데이터가 나오지 않는다.

## Execution, deadline and cancellation

한 `SqliteDatabase`가 PHASE 2 `BoundedExecutor` 두 개를 소유한다: writer 1개, reader 1개.
각 lane은 기본 waiting 8개, 최대 64개다. media/default executor와 공유하거나 process-global
async DB lock을 잡지 않는다. cross-process writer contention은 SQLite의 잠금으로 처리한다.
실제 Pi 용량·p95/p99는 아직 측정하지 않았다.

- 연결은 worker thread 안에서 생성·사용·종료한다. 기존 파일은 `mode=ro/rw`, 새 파일은
  bootstrap/candidate builder만 만든다. 읽기는 `query_only` + read transaction, 쓰기는
  `BEGIN IMMEDIATE` + 짧은 단일 transaction이다.
- 기존 DB journal mode는 startup에서 바꾸지 않는다. explicit 새 DB는 WAL로 만들고
  `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-2000` 정책을 유지한다.
  archive/restore candidate는 self-contained DELETE journal이다. 이를 live WAL로 전환하는
  운영 절차는 PHASE 8에 남긴다.
- request deadline은 queue 대기부터 계산한다. 기본 busy wait 100ms(설정 최대 1초),
  남은 deadline 이하로 설정한다. SQLite progress handler와 commit/publish 직전 checkpoint가
  취소·deadline을 관찰한다. thread는 강제 종료하지 않는다.
- awaiter 취소 후에도 실제 running worker가 끝나기 전 capacity를 반환하지 않는다.
  queued cancellation은 늦은 mutation을 실행하지 않는다. lane을 닫으면 새 admission을 거부하고
  기본 2초, 최대 10초 grace 내 drain한다. 미종료 작업은 typed failure로 드러난다.
- busy/I/O는 `DatabaseUnavailableError`, corrupt/schema/semantic/ledger는 `DataIntegrityError`,
  saturation은 `CapacityError`, deadline은 `DatabaseDeadlineError`다. SQL, row, path, key,
  원문 exception을 오류 메시지에 포함하지 않는다.
- commit/publish checkpoint를 이미 지난 뒤 취소되면 성공이 적용됐을 수 있다. deadline error는
  `retryable=False`, `commit_outcome=unconfirmed`이며 자동 재시도하지 않는다. 다음 Phase의
  application은 결과 재조회/idempotency를 구현해야 한다.
- bounded observation ring은 lane/phase/result/correlation, queue와 execution 시간을 남긴다.
  awaiter 종료와 late worker 결과를 별도로 관찰한다. 기본 40, 최대 264개 이력이며 raw SQL·행을
  보관하지 않는다. metrics/alert exporter 연결은 PHASE 8 책임이다.

## Validation and explicit recovery

`inspect()`와 `start()`는 schema-create, migration, backup fetch/restore를 실행하지 않는다.

| 입력 상태 | 결과 |
| --- | --- |
| 정상 existing DB | `valid`; legacy schema/ledger/semantic 검사 후 ready |
| 파일 없음 | `missing`; fail-closed, 새 파일 없음 |
| existing 0-byte | `zero_byte`; fail-closed, bytes 그대로 |
| corrupt SQLite | `corrupt`; fail-closed, 자동 복구 없음 |
| wrong/partial schema | `wrong_schema`; fail-closed, 자동 ALTER 없음 |
| invalid semantic rows | `invalid_data`; fail-closed, 삭제/정정 없음 |
| unknown/tampered ledger | `invalid_ledger`; fail-closed |
| valid backup | 명시적인 restore-to-new-path operation으로만 candidate 생성 |
| invalid local + valid supplied candidate | 최대 8개의 명시적 순서에서 invalid index를 기록하고 정상 candidate 선택 |

현재 six-table schema의 column 순서/type/default/PK를 검사한다. users birthday pair와 Watch
channel/message pair가 **둘 다 없는** 이전 schema만 알려진 variant로 읽는다(NULL projection).
pair 한쪽만 누락되거나 알 수 없는 table/column/view/trigger/user_version이면 거부한다.
기존 semantic 검사에는 key/type, nonnegative XP/seconds/count, birthday pair, orphan playlist가
포함된다. 실제 날짜 오류는 V1 legacy warning으로 분리한다.

`bootstrap()`은 호출 자체가 명시적 empty-init operation이며 기존 파일은 0-byte라도 거부한다.
restore/migrated copy는 원본과 다른 **새 목적지**만 게시한다. corrupt canonical file을
자동 교체하지 않는다. live connection·WAL sidecar가 있는 canonical 교체는 PHASE 8/10 운영
gate의 책임이며 이 API로 우회하지 않는다.

## Migration ledger and rollback

`storage/adapters/migrations.py`에 registry와 SQL을 함께 둔다. import 시 실행하지 않으며 별도
SQL 파일이나 migration framework/dependency는 추가하지 않았다.

| version | identity | expansion |
| --- | --- | --- |
| 1 | `legacy-nullable-pairs` | 알려진 네 nullable column 중 없는 column만 추가 |
| 2 | `legacy-guild-query-indexes` | users guild/birthday와 Watch guild 조회 인덱스 3개 |

`v2_migrations(version PK, identity UNIQUE, checksum, state, applied_at)`만 새 metadata table이다.
checksum은 version/identity/statements의 canonical JSON에 SHA-256을 적용한다. state는
transaction과 함께 확정되는 `applied`만 허용하고 UTC 적용 시간을 기록한다. registry는 version
오름차순이며 gap/duplicate/unknown version/identity/checksum mismatch를 거부한다. applied column과
index가 실제로 존재하는지도 검사한다. `PRAGMA user_version=0`은 legacy 호환을 위해 유지한다.

공개 operation은 verified snapshot을 만든 뒤 그 candidate에만 migration을 실행한다. 각 step의
DDL과 ledger insert는 같은 transaction이다. 실패한 step은 전부 rollback하고 이전 step의 applied
기록은 유지한다. 새 connection의 재실행은 미적용 step부터 재개한다. 공개 copy 작업은 실패한
candidate를 폐기하고 원본에서 다시 안전하게 시작할 수도 있다.

검증은 count와 별개로 PK 순서의 기존 모든 column 값을 streaming SHA-256으로 비교한다.
nullable expansion은 이전에도 NULL로 투영되므로 동일 digest를 가져야 한다. 이 digest는 내부
reconciliation용이며 raw row/production-derived fixture를 출력하거나 commit하지 않는다.

rollback은 데이터 down-migration 없이 이전 reader/release를 사용한다. 추가 table/index/nullable
column을 삭제하지 않고 최소 7일 V1 reader window를 유지한다. 실제 cutover와 window 시작은
PHASE 10 승인 뒤다.

## Backup and publication

[SQLite online backup](https://www.sqlite.org/backup.html)과 명시적으로 고정한 read transaction을
사용한다. 검증과 snapshot이 같은 시점을 공유하고 WAL writer는 그동안 별도 commit할 수 있다.
복사본에서만 SQL dump를 생성하고 exact encrypted output을 다시 restore하여 schema, ledger,
semantic checksum과 counts를 검사한다.

현재 `DISCORDBOT_BACKUP_V2\n` + 전체 SQL Fernet token 형식을 그대로 쓴다. 새 key는 명시적 bytes
인자로만 받으며 env/운영 credential을 읽지 않는다. legacy whole-schema plain SQL과 favorites/
play-count URL·제목의 부분 Fernet 암호화를 읽는다. SQLite parser로 quoting/줄바꿈을 처리한다.
V1이 허용했던 empty/sparse dump에서 누락 table을 새로 만드는 복구는 V2에서 거부한다.

restore SQL은 시작/종료 transaction과 SQLite authorizer를 통과해야 한다. ATTACH, PRAGMA,
extension/function, trigger/view/virtual table, destructive statement와 unknown table을 거부한다.
입력/출력 encrypted backup은 기본 64MiB, 설정 최대 256MiB다. snapshot/restore candidate DB는
그 4배의 디스크 상한을 적용한다. plaintext는 private temp DB와 bounded memory에만 머물며
전체 작업과 검증을 마친 뒤 임시 DB와 sidecar를 정리한다.

완료된 candidate는 fsync 후 같은 filesystem의 atomic hard link로 **no-clobber** 게시한다.
지원하지 않는 filesystem에서는 실패하며 overwrite 방식으로 우회하지 않는다. encrypted latest
backup만 검증 후 `os.replace`하고 Linux에서는 parent directory도 fsync한다. publication 뒤 OS
오류·응답 취소는 outcome이 불확실할 수 있으므로 재조회가 필요하다. 전원 차단 durability와
filesystem 특성은 실제 Pi에서 검증해야 한다.

운영 cron/timer, remote Git fetch/push, retention, key rotation, scheduler와 production 경로 복구는
구현·실행하지 않았다. 다른 process가 마련한 local/downloaded candidate를 주입할 수 있는
primitive만 제공한다.

## Evidence and scope discrepancies

자동 증거는 `tests/integration/data/`, PHASE 3 소유 zero-byte characterization과 architecture test다.
실제 DB 사본의 결과는 [migration rehearsal](migration-rehearsal.md)에 별도로 기록한다.

| 관찰 | 문서 주장 | 영향 / 처리 |
| --- | --- | --- |
| 진입 baseline 213 passed, 13 xfailed | PHASE 2 report 211 passed, 13 xfailed | 이후 문서 구조 commit이 test 2개 추가. 회귀 없음. Phase 3 보고에만 기록 |
| V2 골격의 ports는 빈 package | current가 repository boundary 준비로 설명 | concrete Protocol/DTO/adapter를 이번 Phase에 추가 |
| V1 empty/sparse SQL restore 뒤 schema-create | baseline/current의 fail-closed 목표와 다름 | V2는 full known schema candidate만 허용. V1 source/test는 보존 |
| baseline Phase 3에 music JSON도 기재 | 이번 사용자 지시는 SQLite Data Compatibility로 한정, Music migration 금지 | JSON 0.5/version/ACK 교정은 PHASE 7에 남김. xfail marker 유지 |
| 실제 Watch 두 table은 0행 | Watch compatibility 요구가 존재 | 실제 데이터의 nonempty 검증을 주장하지 않고 synthetic test로 보완 |
| product-spec의 bootstrap 미구현 설명은 V1 기준 | V2에는 explicit bootstrap 구현 | 제품 문서에 V2 미연결 상태 안내를 추가; V1 설명 삭제 안 함 |
