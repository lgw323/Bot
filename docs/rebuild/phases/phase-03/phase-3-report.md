# PHASE 3 Report

## Phase 3 Complete

**YES — 2026-09-06 완료.** PHASE 3 data compatibility 구현과 synthetic 검증, 실제 DB의
독립 working-copy rehearsal 두 차례를 완료했다. PHASE 4는 시작하지 않았다.

## Implemented

- context-owned SQLite repository/DTO와 공유 storage infrastructure, guild/user 범위 검증.
- bounded writer 1 / reader 1, deadline·취소·capacity·typed failure와 lifecycle readiness gate.
- known legacy schema reader, semantic validation, expand-only version/checksum/time ledger와 resume.
- explicit absent-file bootstrap, invalid existing DB fail-closed, verified copy-only migration/restore.
- point-in-time online snapshot, 현재 전체 암호화 V2 backup, legacy plain/field-encrypted SQL reader,
  candidate validation과 atomic no-clobber publication.
- PII를 출력하지 않는 offline actual DB working-copy rehearsal 도구.

세부 의미·API·상한·commit point는 [data contract](data-compatibility-contract.md)에 기록했다.

## Tests

- 진입 baseline: `213 passed, 13 xfailed, 1 warning in 4.37s`.
- concurrency 전체 7개 case와 migration failure/resume 1개 case를 각각 100번 실행:
  **800 passed in 73.69s**. pytest의 session-local autouse fixture에 `params=range(100)`을
  적용했다. package 설치나 repeat plugin dependency 추가는 없다.
- 최종 전체 test: **282 passed, 12 xfailed, 1 warning in 10.27s**.
- data integration + architecture/documentation: **81 passed in 4.29s**.
- 첫 SQLite 기반 계층 커밋은 staged tree만 별도 export해 독립 검증했다:
  **235 passed, 12 xfailed, 1 warning in 8.81s**.

전체 명령은 `python -m pytest tests/ -q -W error::RuntimeWarning
-W error::pytest.PytestUnraisableExceptionWarning`이다. 별도 build/lint/type-check 명령은 없다.

모든 실행은 repository `.venv` Python 3.12.14, `.env` loading을 끈 환경에서 수행했다.
RuntimeWarning과 PytestUnraisableExceptionWarning을 error로 취급했다. baseline의 일반 warning은
discord.py가 import하는 `audioop`의 Python 3.13 제거 예고다. 실제 API/Discord/Gemini/YouTube/
Git network/systemd/Pi 또는 실제 backup을 test에 사용하지 않았다.

## Architecture Check

- domain/application의 SQLite/vendor import 금지, raw background task/blocking dispatch 규칙 유지.
- shared storage에 대한 좁은 dependency 규칙, inward layer의 executor/legacy runtime 의존 금지 강화.
- fresh-process 전체 V2 import는 DB/network/server/thread/subprocess/root logging side effect 없음.
- 실제 SQLite resource를 PHASE 2 composition에 test로 주입해 DB validation 전 다음 capability
  기동을 막고 failure readiness=false와 clean shutdown을 검증했다. production wiring은 없다.

## Data Compatibility Check

Synthetic V1 schema에서 two-guild same-user, user-global favorites, guild=0 legacy row, 소수 voice
seconds, null/잘못된 calendar birthday, persisted volume, 원문 URL/제목, 27 favorites와 60 historical
play-count rows, Watch session/playlist ordering을 검증했다. migration 뒤 unchanged V1 reader도
동작한다. schema/type/default/PK, ledger identity/checksum와 semantic invariants를 확인한다.

## Actual DB Rehearsal

[실행 결과](migration-rehearsal.md): SQLite integrity `ok`, legacy-current schema, ledger 0→2,
repeat migration과 old reader PASS. users 15 / favorites 40 / settings 1 / counts 50 / Watch
sessions 0 / playlists 0행이 전후 동일하고 모든 기존 값의 semantic checksum이 일치했다.
실제 row/ID/URL/생일/제목은 문서·fixture·output에 기록하지 않았다.

## Reliability / Failure Check

CF-07/14 data-side/20 data-side/21 repository-side를 구현했다. busy writer와 독립 read 진행,
queue saturation, waiting/running cancellation, deadline, long-query progress interruption,
rollback-before-commit, per-step migration failure/restart, checksum drift, simultaneous cross-table
write 중 pinned backup, wrong key/tampering, invalid local→good supplied candidate, partial SQL,
SQL ATTACH/PRAGMA/extension/trigger 방어, disk/publication failure와 last-good 보존을 검증했다.

기존 V1 test schema builder의 미종료 connection은 synthetic fixture에서 GC 후 hash를 측정한다.
V2 worker connection은 항상 같은 thread에서 close한다. Windows fsync에는 writable candidate
descriptor가 필요함을 확인해 반영했다.

## Original DB Integrity Check

원본 `docs/rebuild/bot_database.db`: 65,536 bytes.
작업 전과 rehearsal 후 SHA-256은 모두
`4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25`다.
Git ignore 유지, add/commit 제외. 원본의 rename/move/delete/SQLite open/migration은 없다.
원본에는 hash와 read-only copy 생성만 수행했다.

## Pi Impact

없음. Pi 접근/설치/clone, service/systemd/cron/timer 활성화, token/key 사용/교체, production
restore/migration/Discord 실행, Cloudflare/Tunnel/DNS 변경은 수행하지 않았다. 신규 package 설치와
dependency upgrade도 없다. Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet target만 유지한다.

## Compatibility

V1 source/public functions, command UX, SQL envelope, music JSON, Watch API/WS와 timing은 그대로다.
새 schema metadata/index/nullable expansion은 작업 사본 또는 explicit bootstrap에만 적용된다.
rollback은 down-migration 없이 V1 reader를 유지하는 방식이며 production 최소 7일 window는
cutover 후 시작한다. favorite 추가 시 새 guild=0 row를 요구하지 않지만 기존 row는 보존한다.

## Corrected Legacy Bugs

V2 startup에서 missing/zero-byte/corrupt/wrong-schema를 정상 빈 DB로 승격하지 않도록 교정했다.
PHASE 3 소유 zero-byte spec을 실제 V2 gate 검증으로 전환했고 V1 runtime은 수정하지 않았다.
bounded DB admission과 pinned/validated snapshot도 V2에 구현했다. 나머지 strict xfail 12개는
PHASE 4–7에 남긴다. JSON default/version/ACK는 PHASE 7 소유로 명확히 기록했다.

## Documentation Updated

Phase 3 contract/rehearsal/report, current ADR-018/trace/plan/open questions, rebuild README,
project README, product-spec의 V2 미연결 안내와 CHANGELOG를 갱신했다. baseline/이전 Phase는
수정하지 않았다. 문서 상대 링크와 anchor/구조 test에 PHASE 3를 포함했다.
문서·코드의 진입 시 불일치는 data contract의 관찰/주장/영향 표로 남겼다.

## Remaining Risks

- 실제 Watch 데이터는 0행: nonempty compatibility는 synthetic evidence다.
- feature application/Discord/UI, Watch single writer/actors, playback session idempotency와
  snapshot/XP/calendar policy는 이번 Phase 범위가 아니다.
- commit/publish 직후 취소·응답 실패는 outcome이 불확실할 수 있다. 자동 retry 대신 application
  재조회/idempotency가 필요하다. Python thread 강제 중단과 전원 차단 시험은 하지 않았다.
- backup이 단일 read lane을 점유할 수 있다. hard deadline/cap으로 제한했으나 실제 Pi의
  latency/capacity/memory/disk 수치는 staging에서 측정해야 한다.
- SQLite archive와 sparse/unknown schema는 자동 수선하지 않는다. 새 사례는 verified copy와
  별도 reviewed migration이 필요하다. restore candidate의 live canonical 교체는 지원하지 않는다.
- private temp directory 권한, hard-link/filesystem와 directory fsync/power-loss durability,
  real key recovery/RPO/RTO/retention/remote transport는 PHASE 8/9 gate다.

## Next Phase Gate

PHASE 3 검증을 완료해 PHASE 4 entry는 가능하지만 **사용자 지시 전 시작하지 않는다**.
PHASE 4는 이 baseline과 PRESERVE suite를 먼저 실행하고 approved engagement policy만 연결한다.
Production migration/cutover는 PHASE 10 별도 승인, V1 삭제는 PHASE 11 별도 승인 대상이다.

## Decision Required

없음. 사용자 데이터 의미 변경·삭제·rollback 포기·외부 비용·보안 정책 변경·credential/Pi 접근을
요구하지 않는 기술 선택으로 완료할 수 있다.

## Commit and rollback

- `f13e374` — `feat: add bounded SQLite compatibility repositories`: repository boundary,
  bounded execution, startup validation과 migration ledger 및 해당 test.
- `0b2193b` — `feat: add verified database recovery and copy rehearsal`: bootstrap/backup/restore,
  verified migration copy, offline rehearsal 도구와 failure/concurrency test.
- 이 보고서를 포함한 `docs: complete V2 phase 3 data compatibility` commit: 완료 문서,
  current trace/gate와 문서 구조 test. 자신의 hash는 포함하지 않으며 Git log로 확인한다.

각 commit의 staged diff와 `git diff --cached --check`를 검사했다. Runtime 미연결 변경이므로
코드 rollback은 복구 계층 → SQLite 기반 계층 순서로 revert하면 된다. 실제 원본 data rollback은
필요하지 않으며 generated expanded copy에 destructive down-migration을 실행하지 않는다.
검증용 실제 DB 사본은 제거했고 safe aggregate report만 ignored scratch에 남겼다. 최종 commit
뒤 worktree 상태는 사용자 완료 응답에 별도로 보고한다. 원격 push/PR은 수행하지 않는다.
