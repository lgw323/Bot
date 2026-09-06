# PHASE 4 Report

## Phase 4 Complete

**YES — 2026-09-06 완료.** Engagement 구현, synthetic 검증과 반복/전체 suite를 완료했다.
PHASE 5는 시작하지 않았다.

## Implemented

F029–F036의 text/voice XP, profile/ranking, 생일 등록/삭제/목록/알림을 domain/application/ports와
SQLite/Discord adapters로 구현했다. 명시적 composition builder와 supervised scheduler를
추가했다. V1 entrypoint나 운영 process에는 연결하지 않았다.
세부 계약은 [engagement contract](engagement-contract.md)에 기록했다.

## Tests

- 진입 baseline: **282 passed, 12 xfailed, 1 warning in 10.44s**.
- Engagement + corrective characterization + architecture/documentation: **95 passed in 4.81s**.
- 첫 커밋의 staged tree만 별도 export한 독립 전체 검증:
  **343 passed, 12 xfailed, 1 warning in 14.42s**.
- 동시성/취소/생일 중복 시나리오 6개를 각각 100회 실행: **600 passed in 82.61s**.
  session-local pytest autouse fixture의 `params=range(100)`을 사용했으며 repeat plugin은 설치하지 않았다.
- 최종 전체 suite: **358 passed, 9 xfailed, 1 warning in 16.09s**.

환경은 repository `.venv` Python 3.12.14, `PYTHON_DOTENV_DISABLED=1`이다. 전체 명령은
`python -m pytest tests/ -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.
기존 audioop deprecation warning만 남아 있다. 설치/upgrade 없이 synthetic 임시 DB, fake clock,
barrier, fake Discord send만 사용했다. 실제 API/production network나 보관 DB는 사용하지 않았다.

## Architecture Check

SQLite는 adapter, Discord type은 adapter 안에만 있다. application은 PHASE 3 writer/read lane과
typed repository를 사용한다. raw task/blocking dispatch 우회와 import side effect 검사는 유지된다.
SDK loading은 명시적 생성 시점이고 Cog에 voice/XP dictionary가 없다. TaskSupervisor가 birthday
task와 lease handover를 소유한다. 실제 Bot 객체를 network 없이 만들고 command 등록, readiness
전 scheduler 미시작, 종료 시 bot/task/DB 정리를 검증했다.

## Text XP

모든 한글 완성형 음절 11,172개와 Unicode/whitespace/Jamo edge case를 실제 V1 함수와 대조했다.
모든 guild 채널, bot/DM 제외, 기존 XP 더하기, 동시 event, 동일 message ID 중복, 다른 guild의
같은 user와 restart replay를 검증했다. receipt와 XP는 같은 transaction이다. 새로운 cooldown/
지급량 상한은 없다. retention/cap은 live-event dedupe 자원 정책으로 contract에 명시했다.

## Voice XP

completed-minute 계산을 하나의 Progress policy로 통일했다. join/leave/move, self/server mute와
deaf, 60초 미만 반복 체류, fractional legacy seconds, multi-guild, replay sequence, shutdown
race를 검증했다. 프로세스 재시작은 이미 관찰된 duration만 정산하고 offline time을 추가하지
않는다. DB observation 실패 뒤 종료 시 잘못된 외삽을 막는 fail-closed 경계도 검증했다.

## Profile / Ranking

다섯 명령의 description/parameter/type/required/default를 V1 command 객체와 직접 비교했다.
profile private defer, master-other/일반 self, missing 0 XP, embed fields와 guild isolation을
검증했다. ranking은 기존 합산 TOP 10, 공개성 옵션과 empty 문구를 유지하며 completed-minute
XP를 표시한다. 동점은 user ID 오름차순으로 고정했다. text/voice 선택 옵션은 추가하지 않았다.

## Birthday

master exact match, 실제 calendar 날짜, leap-century cases, Feb 29 → 비윤년 Feb 28, KST 09:00,
같은 날 반복 tick/재시작/취소와 multi-guild를 검증했다. 긴 목록은 원소를 버리지 않고 embed
한도에 맞게 나눈다. send 직전 durable claim으로 재전송을 막는다. 외부 send와 SQLite의 원자성
한계 때문에 claim 이후 불확실한 실패는 알림 누락 가능성이 있으며 자동 재전송하지 않는다.

## Concurrency / Failure Check

CF-17 voice state/leave/shutdown, CF-18 daily guild/date claim, CF-19 ACK 전후 한 responder,
CF-20 bounded shutdown과 CF-21 multi-guild를 검증했다. DB busy에는 typed failure가 전파되고
text receipt/XP rollback 뒤 안전한 retry가 가능하다. voice 관찰 실패는 fail-closed하며 잘못된
체류 누적을 하지 않는다. scheduler는 중복 start와 lease handover에도 bounded 상태다.

## Data Compatibility

PHASE 3 schema/ledger reader와 verified-copy migration을 사용했다. version 3은 부가 table 4개와
index 1개이며 legacy six-table schema와 migration 1/2 checksum은 그대로다. version 2 synthetic
DB는 implicit migration 없이 feature startup을 거절한다. 명시적인 expanded copy는 V1 reader로
읽힌다. metadata를 포함한 encrypted backup/restore/repeated-copy checksum도 검증했다.
`docs/rebuild/bot_database.db` 원본은 이번 Phase에서 접근·복사·수정·stage하지 않았다.

## Pi Impact

없음. Pi 접근, production token/network, Discord 로그인/command sync, service/systemd/cron,
Cloudflare, 실제 data migration/cutover, push/PR/deploy를 수행하지 않았다.

## Compatibility

V1 code와 PRESERVE characterization은 변경하지 않았다. 명령 이름·옵션·master permission·공개성,
XP/Jamo·short-stay 의미와 생일 문구를 유지했다. birthday register/delete의 정상 처리만 ACK
deadline을 위해 private defer/followup으로 연결했다. Summary/Watch/Music 기능을 구현하지 않았다.

## Corrected Legacy Bugs

PHASE 4 소유 CORRECT 3개를 실제 V2 경로로 전환했다: ranking의 fractional-minute 오류, 존재하지
않는 생일 허용, 비윤년 Feb 29 누락. 단순 xfail marker 삭제가 아니라 V2 repository·application/
Discord adapter와 fake clock을 호출한다. 나머지 strict xfail 9개는 PHASE 5–7에 남긴다.

## Documentation Updated

PHASE 4 contract/report, current ADR/trace/plan/open questions, rebuild index, README/product-spec와
CHANGELOG를 갱신했다. baseline과 PHASE 0–3 문서는 역사적 산출물로 보존했다.

## Remaining Risks

- 실제 Gateway/Discord HTTP와 Pi capacity/latency/소켓·intent 설정 검증은 staging에 남아 있다.
- crash 전 마지막으로 관찰하지 못한 voice 구간은 복구할 수 없고 offline time을 추측하지 않는다.
  observation 불확실 시 voice capability는 재시작 reconciliation을 요구한다.
- durable birthday claim 후 실패는 알림이 누락될 수 있다. 외부 exactly-once delivery를 주장하지
  않으며 operator 검토 없이 같은 날 자동 resend하지 않는다.
- bounded receipt/voice capacity와 7일 live-event horizon은 실측 후 조정할 운영 parameter다.
  장기 message history backfill, 자동 voice fault recovery와 전체 운영 alert/runbook은 구현하지 않았다.
- Phase 3 V2 validator는 version 3을 모른다. rollback은 V1 reader compatibility에 근거하며
  production 적용/복구/승인 절차는 후속 gate에 남는다.

## Next Phase Gate

PHASE 5 Summary는 사용자 지시 후에만 시작한다. 다음 Phase는 이 suite와 PRESERVE baseline을
재실행해야 한다. production migration/cutover와 V1 삭제는 각각 PHASE 10/11 별도 승인 대상이다.

## Decision Required

없음. 승인된 Engagement 의미 안에서 구현했다. 역할 관리/새 권한 정책, 실제 데이터 삭제,
운영 credential 또는 Pi 접근이 필요하지 않았다.

## Commit / rollback

- `089182b` — `feat: persist engagement XP and birthday event ownership`: domain/application,
  transactional metadata, supervised clock와 관련 synthetic 검증.
- `60d09f5` — `feat: wire engagement Discord commands and supervised lifecycle`: explicit Discord
  composition, five command/Gateway/lifecycle adapter와 세 CORRECT spec 전환.
- 이 보고서를 포함한 `docs: complete V2 phase 4 engagement migration`: 계약/완료 결과,
  current decision/trace/next gate와 문서 구조 검사. 자신의 hash는 Git log로 확인한다.

각 commit 전 staged diff와 `git diff --cached --check`를 검사했다. 코드 rollback은 연결 계층부터
역순 revert하며 사용자 데이터/metadata를 destructive down-migration하지 않는다. 실제 보관 DB와
운영 배포가 없으므로 원본 data rollback은 필요하지 않다. 검증용 code export는 ignored scratch에만
남긴다. 최종 worktree 상태는 완료 응답에 별도로 보고하며 push/PR/deploy는 하지 않는다.
