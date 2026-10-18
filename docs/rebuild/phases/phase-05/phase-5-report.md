# PHASE 5 Report

## Phase 5 Complete

2026-09-08. Summary F006–F010만 V2로 구현했다. PHASE 4 기준선과 clean worktree,
`089182b`, `60d09f5`, `5cf4c55`를 확인한 뒤 진행했다. 현재 contract는
[Summary contract](summary-contract.md)를 따른다. PHASE 6은 시작하지 않는다.

## Implemented

message-ID capture/preload, bounded retention, 기본/고급/refresh/topic, source ACL,
Gemini async adapter, typed failure와 cancellation, FIFO active 1/waiting 4,
전체 60초 budget, pre-sink privacy와 supervised Discord lifecycle을 추가했다.
공개 명령·결과와 비공개 상세 의미를 유지하고 V1 운영 route에는 연결하지 않았다.

## Tests

모든 실행은 `PYTHON_DOTENV_DISABLED=1`, 기존 Python 3.12 `.venv`에서 수행했다.
RuntimeWarning과 PytestUnraisableExceptionWarning은 error로 취급했다.

- PHASE 4 기준선: **358 passed, 9 xfailed**, 15.97초.
- 핵심 application/capture 커밋 검증: **34 passed**, 0.09초.
- Summary integration + architecture: **82 passed**, 0.97초.
- 최종 전체 회귀: **434 passed, 4 xfailed**, 15.10초. 일반 경고 1개는 기존 discord.py
  `audioop` deprecation이다. RuntimeWarning/unraisable error는 없었다.
- deterministic barrier/fake-clock 기반 8개 concurrency/cancel/reconnect case를 100회 실행해
  **800 passed**, 81.16초를 확인했다.
- 최종 adapter에서 handoff cancellation을 추가한 9개 case × 100회: **900 passed**, 82.81초.
  FIFO/early-cancel/active·waiter timeout/remaining-budget/ACL 철회/단일 timeout 응답/
  handoff cancel/reconnect coalescing을 실제 V2 경로로 반복 실행했다.
- 문서 inventory/상대 링크 검사: **2 passed**, 0.06초.
- 중간 전체 수집에서 다른 기능과 test module 이름이 겹쳤으나 Summary test package에
  `__init__.py`를 추가해 해결했다. 최종 전체 수집과 실행은 정상이다.

기본 전체 명령은 `pytest tests/`이며 실제 사용한 strict command는 다음과 같다.

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
.venv\Scripts\python.exe -m pytest tests/ -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

## Architecture Check

기존 architecture 검사 12개를 유지했다. domain/application vendor import, cross-context import,
raw create_task/blocking dispatch를 추가하지 않았다. 새 V2 모듈 전체의 fresh-process import에서도
DB/socket/subprocess/task/thread/env/root logging side effect 금지 검사를 통과했다.

## Capture / Retention

`test_capture.py`: preload/live interleave, duplicate, ID ordering, reconnect cursor, first-observation,
age/count ordering, disabled, scope, failed preload retry와 typed config 상한을 검증한다.
`test_lifecycle.py`: ready storm coalescing, resumed listener, bounded lifecycle과 late-ready 종료를
검증한다. runtime은 source preload가 완료되지 않으면 partial history를 요약하지 않는다.

## Basic / Advanced Summary

`test_discord.py`에서 `/요약 hours:number=6.0`, 공개 defer/성공 embed, no-data/error private,
모달 세 필드와 기간 상속, filter와 public submit을 호출했다. `test_requests.py`는 범위, keyword/user
filter, KST timestamp, 다른 guild의 데이터 제외와 untrusted preference 분리를 검증한다.

## Refresh / Topic Interaction

새 공개 refresh result는 이전 query를 유지하고 immutable result token + absolute topic index로
선택을 연결한다. 26번째 topic도 다음 페이지와 비공개 detail로 접근했다. stale/expired result,
다른 message/guild/channel, invalid token을 거절한다. view/result/modal capacity와 정리도 검증했다.

## Gemini Boundary

vendor type은 adapters 안에만 있다. Gemini REST session은 explicit start에서 생성하며
generate 외에는 API를 호출하지 않는다. async total/connect/read timeout, redirect 금지, 0 retry,
bounded response와 strict result validation을 fake HTTP transport로 검증했다. malformed/blocked/
oversized response와 transient/permanent/timeout/cancel에 실제 API를 사용하지 않았다.

## ACL / Privacy

configured source의 view/history 권한을 extraction 전에 검사하고 대기 후·외부 호출 직전·결과 생성
전에 다시 확인한다. queue 중 권한 철회와 topic/modal 권한도 검증했다. telemetry에는 raw diagnostic을
전달하지 않고 PHASE 2 pre-sink sanitizer를 사용한다. synthetic secret/raw provider output이
telemetry 또는 private error 문구에 들어가지 않는다. 추가 filter/preference를 system instruction에
보간하지 않으며 외부 모델에 다른 source나 환경 secret을 읽는 도구를 주지 않는다.

## Concurrency / Deadline

CF-08: active 1/waiting 4, sixth immediate capacity, FIFO, waiter cancel/timeout/실행 전 cancel 회수.
CF-09: 실제 60초 설정에 연결한 controllable timer, 59.999초 성공/60초·61초 실패,
queue 대기 50초 후 remaining 10초, ACL 소요 시간 차감, 늦은 result 폐기.
stalled Gemini 중 unrelated async probe와 다른 guild capture가 진행되는 것도 검증했다.

## Failure / Cancellation

CF-19: ACK 전 validation, defer 후 provider/no-data/parse/timeout failure, uncertain defer/followup,
refresh/modal/detail/page의 단일 responder. handoff 직후 cancel도 결과를 회수한다.
CF-20: shutdown은 모든 admitted request와 background work를 취소·drain하고 provider/UI/cache를
정리한다. CF-16: ready/resumed 이벤트는 bounded reconciliation으로 합친다.

## Pi Impact

Pi 접속·측정·설치·배포를 하지 않았다. systemd, auto update/backup, Cloudflare, 운영 token/login과
실제 Discord/Gemini API는 사용하지 않았다. 원본 `docs/rebuild/bot_database.db`는 read/hash/copy/modify
모두 하지 않았다. schema와 dependency도 변경하지 않았다.

## Compatibility

V1 PRESERVE test 본문은 변경하지 않았다. 기존 기본 공개 요약, private detail/error, modal 이름과
필터 의미를 유지했다. V1의 date modal/refresh 원본 갱신이라는 historical 서술은 실제 코드와 다르므로
새 contract에 관찰 차이를 기록했고 과거 문서는 수정하지 않았다. edit/delete/system 의미도 기존
listener 구독 기준으로 보존했다. Engagement·Music·Watch 코드는 변경하지 않았다.

## Corrected Legacy Bugs

Summary-owned strict xfail 5개를 실제 V2 application/controller 호출로 전환했다: source ACL,
60초 total timeout, active 1, waiting 4, malformed raw output redaction.
공동 pagination spec의 Music marker는 유지하고 Summary의 실제 26-topic callback spec을 분리했다.
남은 strict xfail은 **4개**이며 PHASE 6 Watch 2개, PHASE 7 Music 2개다.
추가로 preload/live gap·duplicate, reconnect reconciliation과 bounded interaction state를 교정했다.

## Documentation Updated

이 보고서와 Summary contract, current plan/trace/ADR/open questions, rebuild README,
root README/product spec의 V2 안내와 changelog를 갱신했다. 문서 inventory test에 phase-05를 추가했다.
baseline과 PHASE 0–4 산출물은 동결 상태를 유지했다.

## Remaining Risks

- 실제 Gemini 응답 품질, REST/model 지원과 Discord Gateway/cache/ACK behavior는 staging 미검증이다.
- 공개 결과는 게시 channel의 Discord 권한을 따른다. 실제 source/result channel 권한 배치와
  member cache/intent는 staging에서 검증해야 한다. private UX로 임의 전환하지 않았다.
- configured retention/count 밖 이력, Discord에서 이미 삭제된 원문은 복구 대상이 아니다.
- provider는 cooperative cancellation 계약을 지켜야 한다. 악의적 비협조 coroutine의 강제 종료는
  보장하지 않는다. delivered 여부가 불확실한 Discord 실패는 자동 재전송하지 않는다.
- 초기 Pi memory/latency/capacity와 장기 soak는 PHASE 9 gate다.

## Next Phase Gate

PHASE 6 Watch migration은 다음 사용자 지시 후 시작한다. 이번 변경에서 Watch/FastAPI/Music을
구현하지 않았다. production DB migration/cutover와 배포는 후속 별도 승인 gate다.

## Decision Required

이번 Summary migration에 추가 제품 결정은 필요하지 않다. 실제 배포 권한 구성과 외부 API 검증은
staging 단계의 운영 확인이며 이 Phase에서 production 실행을 승인받거나 수행하지 않았다.

## Commit / rollback

- `c81f4d1 feat: bound summary capture and authorized request lifecycle`: core/ports/capture/application과 테스트.
- `643b75a feat: wire summary Discord interactions and Gemini boundary`: adapters/composition과
  관련 integration·CORRECT characterization.
- `docs: complete V2 phase 5 summary migration`: 이 보고서와 current trace/contract/documentation 검사.
  문서 commit은 자기 hash를 포함하지 않으며 `git log`의 해당 제목으로 식별한다.

rollback은 문서 → Summary adapter → core 순서의 revert다. 다른 Phase와 기존 사용자 변경을
되돌리지 않는다. V1 route가 그대로여서 운영 전환이나 DB 복원이 필요하지 않다.
push, PR, deploy를 하지 않았다.
