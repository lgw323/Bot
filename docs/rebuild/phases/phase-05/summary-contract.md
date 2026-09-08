# PHASE 5 Summary Contract

2026-09-08. F006–F010 / FR-026–030과 PHASE 1 CF-08/09/16/19/20의 Summary 범위다.
명시적 사용자 지시, current Q-H01/03/04/11, Q-M04/07, Q-L02와 PHASE 2 platform을 따른다.
V1 route, Engagement, SQLite schema, Watch, Music과 운영 환경은 변경하지 않았다.

## Boundaries and lifetime

- `summary/domain/models.py`: immutable scope/message/query/topic/result, 입력·출력 상한과 typed no-data/malformed.
- `summary/ports/io.py`: requester authorization, paged Discord history, cancellable provider.
- `summary/application/capture.py`: event-loop 소유 이력, ID ordering/dedupe, retention와 reconciliation.
- `summary/application/service.py`: ACL, FIFO admission, 60초 budget, prompt와 bounded result registry.
- `summary/adapters/`: Gemini REST, Discord translation/UI, resource lifecycle. SDK type은 안쪽으로 전달하지 않는다.
- `composition/summary.py`: 명시적 builder. `build_summary`는 runtime과 feature를 반환하며 login/sync하지 않는다.
  resource는 기존 bot에 주입할 수도 있다. builder가 만든 bot만 stop에서 함께 닫는다.

SQLite를 사용하지 않으며 durable schema는 추가하지 않는다. PHASE 3 boundary는 그대로 유지한다.
vendor import는 adapter 함수/명시적 start에서만 수행한다. import/client 생성만으로 network/task가
시작되지 않는다. production `main_bot.py`와 V1 Cog loader에는 연결하지 않는다.

## Capture and retention

source는 guild별 하나, 전체 최대 10개인 immutable `(guild, channel)` 설정이다. 채널당 최대
1,000개, message body 최대 4,000자, display name 최대 100자다. 실제 user ID는 capture에 저장하지
않는다. 기본 retention 24시간(최대 168), initial preload 3시간(최대 retention), history page 최대
100건, reconciliation 한 번에 최신 최대 1,000건이다. overflow는 가장 오래된 ID를 먼저 제거한다.
전체 이력 상한은 10,000개이며 요청 prompt는 최신 메시지부터 JSON row 기준 100,000자까지만 사용한다.
이는 이력·입력 workload 상한이고 Discord 25-option 제한과 별개다.

live 수집을 preload보다 먼저 연결한다. preload는 newest-first `before` message-ID cursor로
과거 방향으로 이동한다. live의 높은 ID를 preload cursor로 삼지 않으므로 조회 중간의 gap을
건너뛰지 않는다. merge는 ID `setdefault`, 조회는 ID 오름차순이다. 첫 관찰을 유지한다.
age prune 후 count prune하므로 오래된 이력 재전송 때문에 최신 메시지가 밀려나지 않는다.

`on_ready`와 `on_resumed` reconnect는 retention 범위를 다시 bounded reconciliation한다. 진행 중 ready storm은 추가 작업
하나로 합치고 완료 후 다시 조회한다. 실패한 preload는 ready를 만들지 않으며 다음 ready에서
처음부터 재조회한다. runtime은 해당 source가 준비되지 않았으면 Summary를 거절한다. 다른 source는
각자 준비 상태를 가진다. 프로세스 재시작 시에는 durable cursor 없이 Discord 최신 이력을 다시 읽는다.
retention/count 밖 데이터와 Discord에서 이미 삭제된 과거 데이터까지 복원한다고 주장하지 않는다.

bot/DM/빈 본문/미설정 source는 제외한다. V1에 system-type 검사나 edit/delete listener가 없음을
확인했다. 따라서 non-bot system message의 nonempty content는 같은 기준으로 수집하며, 관찰한 본문을
edit/delete event로 수정·삭제하는 새 정책은 추가하지 않았다. 재시작 후에는 Discord가 반환한 현재
이력만 복원된다. 이 차이는 기존 in-memory semantics다.

read/add에서 즉시 prune하고 supervised cleanup이 기본 600초(최대 600)마다 idle 상태를 정리한다.
물리적 idle 보관은 retention 경계 이후 최대 cleanup 주기만큼 지연될 수 있지만 만료 원문은 요청에
포함되지 않는다. disabled는 capture/preload/cleanup/provider start를 하지 않는다.

## Basic and advanced Summary

`/요약 hours:number=6.0`, 설명, 공개 thinking defer, 공개 embed와 버튼을 보존한다. no-data와
사용자/provider 오류는 ephemeral이다. overall overview, numbered topics, 참여자/키워드와 requester/token
footer, timestamp를 유지한다. embed는 25개 field와 6,000자 한도를 지킨다. 긴 주제 표시는 축약하고
상세 선택에서 전체 내용을 제공한다. overview는 검증된 전체 3,000자까지 표시한다.

기간은 finite `0 < hours <= retention_hours`다. 고급 modal은 300초이며 기존 세 필드인
`포함할 키워드 (쉼표로 구분)`, `특정 사용자 이름 (쉼표로 구분)`, `추가 요청사항`을 유지한다.
각 필드는 최대 1,000자다. 키워드는 대소문자 무시 substring OR, 사용자 이름은 대소문자 무시 exact OR,
두 종류의 필터 사이는 AND다. 기간은 원래 결과의 hours를 이어받는다.

historical inventory에는 advanced date 입력이 있다고 적혀 있지만 실제 V1과 PHASE 1 modal contract는
세 text input뿐이다. 새 date-picker 제품을 추가하지 않고 hours 범위를 검증했다.

## Refresh and topic interaction

refresh는 동일 query/filter로 새 공개 결과를 만든다. V1의 실제 callback은 `followup.send`이며,
historical inventory의 원본 message 갱신 설명과 다르다. 기존 결과는 expiry/eviction까지 유지한다.
result token과 absolute topic index를 합친 value가 immutable 결과에 연결되므로 새 결과의 같은
index와 혼동되지 않는다. requester 전용 버튼으로 바꾸지 않았으며 source ACL을 가진 커뮤니티
사용자가 참여할 수 있다. result의 guild, destination channel, 실제 bound message ID를 검사한다.

topic 26–100도 25개씩 이전/다음 페이지로 모두 접근한다. pagination은 원본 공개 message의 UI를
갱신하며 detail은 ephemeral이다. unknown result, 다른 message/context, invalid index, expiry와
eviction은 safe typed error다. modal 제출 때 원래 result/message와 ACL을 다시 검증한다.

application result 최대 32개/3,600초, controller view 최대 32개, modal 최대 32개/300초다.
eviction/expiry/stop에서 Discord View/Modal을 stop한다. 유효 topic을 25개로 잘라 저장하지 않는다.
provider 결과는 최대 100 topics, title 200자, 나머지 각 field 800자다. 이 상한을 넘거나 구조가
깨진 결과는 malformed로 거절하고 raw provider output을 공개하지 않는다.

## ACL and privacy

`DiscordAuthorization`은 configured source의 guild/member와 `view_channel`, `read_message_history`
둘 다 검사한다. role-management나 owner-only 제품은 추가하지 않는다. admission된 요청은 queue 전에,
queue 후 extraction 전에, 외부 호출 직전과 결과 생성 전에 재검사한다. source ACL은 component와
modal에도 적용한다. membership cache가 없으면 fail-closed하고 임의의 network member lookup을 하지 않는다.

공개 결과는 기존과 같이 요청한 channel의 Discord visibility를 따른다. 원본 source와 공개 결과를
게시할 channel의 실제 permission 배치는 staging에서 확인해야 한다. 공개 응답을 private으로 바꾸거나
다른 채널로 자동 전송하는 새 UX를 이번 Phase에서 도입하지 않았다.

application-owned instruction은 Gemini `systemInstruction`, 메시지와 추가 선호는 별도 user JSON이다.
이름·시간·필요한 본문만 해당 scope에서 추출하며 raw user/guild/channel ID, 환경 변수나 capability를
prompt에 넣지 않는다. 기본 시간 표기는 UTC+09:00이다. 사용자 문자열은 system instruction에 보간하지
않고 model에 도구/다른 channel 조회 수단을 제공하지 않는다. 모델이 모든 injection을 완벽히 무시한다는
보장은 하지 않으며 구조적 data-access 격리와 scope minimization을 실행 가능한 보안 경계로 삼는다.

운영 telemetry에는 고정 event/result, opaque correlation과 numeric duration/queue depth만 전달한다.
raw exception/prompt/body/request/response/identifier는 sink 입력 자체에서 제외하고 PHASE 2
`TelemetryEmitter`의 pre-sink sanitizer를 사용한다. UI는 error instance의 임의 safe-message override도
사용하지 않고 typed class의 정해진 문구만 표시한다. Gemini key는 header에만 넣고 URL에는 넣지 않는다.

## Concurrency and deadline

active 1, FIFO waiting 4, 전체 reservation 5다. 여섯째는 즉시 `CapacityError`다. 전용
TaskSupervisor capacity 5/history 32를 쓰며 다른 feature executor/thread를 사용하지 않는다.
task 생성 전에 reservation을 잡고 completion callback이 permit을 회수한다. 실행 전 cancel,
waiter cancel/expiry, provider fail, active cancel 모두 다음 waiter를 진행시키며 admission leak이 없다.

사용자 interaction 시작부터 60초다. validation/defer, queue, ACL/extraction/prompt, provider와
presentation에 하나의 absolute deadline을 전달한다. service 직접 요청도 receipt부터 60초를 쓴다.
후속 단계에서 남은 시간을 다시 계산하고 결과 반환 후 deadline도 검사한다. timeout 뒤 늦은 결과를
cache/send하지 않는다. 외부 coroutine은 cancellation을 전파해야 하는 port 계약이다. 취소를 무시하며
무한 실행하는 비협조적 임의 provider까지 강제로 종료할 수 있다고 주장하지 않는다.

Gemini REST는 aiohttp async transport, total `min(60, remaining)`, connect `min(10, remaining)`,
read `min(30, remaining)`이다. 고정 TLS endpoint, redirect 금지, 요청당 한 번의 호출이며 자동 retry는
0회다. 응답은 최대 512,000 bytes로 읽고 JSON/finish reason/field bounds를 검증한다. schema와 header
형식은 설치된 Google GenAI source와 대조했으며 실제 Gemini 호출은 staging gate에 남는다.

## Failure and shutdown

no-data, authorization, validation, capacity, deadline, transient/permanent provider, malformed,
Discord responder failure, native async cancellation와 typed cancellation UI, shutdown을 구분한다.
원래 interaction 하나에 responder 하나가 ACK/final ownership을 가진다. defer/send 전에 상태를
claim하며 ACK 오류나 불확실한 followup 전달 실패를 두 번째 send로 복구하지 않는다. 각 Discord
호출에도 2초 한도를 둔다. modal/component의 pre-ACK ACL 검사도 2초 이내다.

resource는 request와 background supervisor를 분리한다. background capacity 3/history 16이며
한 cleanup lease와 한 reconciliation, bounded handover만 허용한다. source당 preload 최대 5초,
전체 task 최대 60초다. stop은 listener 제거, task cancel/drain, View/Modal 정리, 원문/result 삭제와
provider close를 소유한다. 취소 시 asyncio control flow는 그대로 전파하며 UI는 가능한 경우 한 번만
private cancellation을 알린다. late ready가 종료된 resource를 다시 시작하지 않는다.

## Verification and rollback

실행 결과와 정확한 test 목록은 [PHASE 5 report](phase-5-report.md)에 있다. 모든 fixture는 synthetic,
history/provider/Discord는 fake다. 실제 보관 DB는 이 Phase에서 read/hash/copy하지 않았다.
production cutover가 없으므로 rollback은 Summary opt-in을 연결하지 않고 기능 commit을 역순 revert하는
것이다. 데이터 복구나 schema downgrade는 필요하지 않다. Watch/Music/운영 gate는 후속 Phase에 남는다.
