# 15. Async and Concurrency Design

## Handler budget

Discord handler는 synchronous validation/authz와 use-case admission만 수행한다. cache hit 등
800ms 안에 완료가 확실한 경우만 initial response로 끝내며, 그 외에는 handler 시작 후
800ms 이내 defer한다. 3초는 목표가 아니라 절대 상한이다. handler가 직접 file, SQLite,
subprocess, blocking SDK를 호출하지 않는다.

## Work classes and initial limits

| work | execution | proposed capacity/deadline | overload behavior |
| --- | --- | --- | --- |
| Discord response | event loop | ACK 2s p99 | 즉시 defer 또는 typed busy |
| DB write | dedicated serialized worker | queue+execution command deadline 내 | bounded queue, retry-after UX |
| DB read | bounded DB executor/connection | 2 workers, query 1s hard max 제안 | fail fast/degraded |
| Gemini summary | async client worker | active 1, waiting 4, total 60s | queue full 메시지, no hidden task |
| yt-dlp metadata/search | dedicated thread/process pool | active 2, total 20s | cancel result, worker health metric |
| audio download | subprocess supervisor | Pi global active 1 initially, attempt 180s | queue cap, user cancellation |
| FFmpeg playback | guild actor + subprocess | track lifecycle | kill/reap on cancel/shutdown |
| gTTS | dedicated blocking pool | active 1, total 15s 제안 | skip TTS, resume music |
| Watch session | per-session actor | bounded mailbox 100 제안 | rate-limit/drop noncritical/close abuser |
| WS send | per-client bounded queue | send 2s 제안 | slow client close |
| telemetry | bounded nonblocking queue | fixed memory budget | sample/drop + counter, never block Gateway |

수치는 load test 전 proposal이며 config와 metric으로 조정한다.

## Ownership model

- `MusicActor[guild_id]`만 queue/current/voice/mode/retry/snapshot revision을 변경한다.
  command, voice callback, FFmpeg completion은 message를 보낼 뿐이다.
- `WatchSessionActor[session_id]`만 participant/playlist/state/expiry revision을 변경한다.
- actor message는 stable ID, expected revision, correlation/deadline을 가진다. mailbox는
  bounded FIFO이고 priority control message(close/cancel)가 starvation되지 않는다.
- cross-actor operation은 shared mutable object가 아닌 event/result로 조정한다.

## TaskSupervisor contract

raw `asyncio.create_task`를 feature code에서 금지한다. supervisor registration에는
`name`, owner(guild/session/job), correlation ID, deadline, criticality, restart policy,
shutdown phase를 요구한다. exception을 즉시 수집하고 active/age/result metric을 남긴다.
fire-and-forget은 “응답을 기다리지 않음”일 뿐 owner 없는 task를 뜻하지 않는다.

### PHASE 2 구현 상태

`src/discordbot/platform/tasks.py`가 V2의 유일한 task 생성 지점이다. 등록 시 `name`, `owner`,
guild/session/job을 나타내는 `work_id`, correlation ID, 최대 24시간의 deadline, criticality,
cancellation behavior, 최대 3회의 typed transient restart, shutdown phase를 immutable spec으로
요구한다. active task와 observation history는 각각 config capacity와 그 4배로 제한하며,
완료·예외·deadline·취소 결과를 done callback에서 회수한다.

`BoundedExecutor`는 실행 worker와 waiting slot 합계를 admission cap으로 사용한다. awaiter가
취소되어도 실제 thread 함수가 끝나기 전에는 slot을 반환하지 않는다. Python thread는 강제
종료할 수 없으므로 shutdown grace 뒤에도 남는 blocking work는 숨기지 않고 degraded shutdown
결과로 보고한다. 기능별 queue/actor/subprocess 정책은 담당 Phase에서 이 platform contract
위에 추가한다.

## Timeout and cancellation

- interaction의 end-to-end deadline을 하위 call에 남은 시간으로 전파한다.
- timeout은 `connect/read/total`을 구분하되 retry를 포함한 total budget을 넘지 않는다.
- cancellation 시 subprocess에 terminate→grace→kill, HTTP body/session close, DB transaction
  rollback, temp partial file 삭제를 수행한다.
- state transition은 cancellation-safe commit point 전/후를 구분한다. commit 후 response
  실패는 재실행하지 않고 idempotent lookup/followup을 한다.
- shutdown은 admission stop → control task → in-flight grace → cancel/reap → durable flush 순이다.

## Retry and circuit breaker

validation/auth/DB constraint/permanent provider error는 retry하지 않는다. timeout, 429,
selected 5xx/network reset만 idempotent 조건에서 최대 2회(기능별 기존 playback 3회 규칙은
별도) jittered exponential backoff한다. 동일 total deadline과 concurrency slot을 점유하지
않도록 retry scheduling을 계측한다. circuit는 dependency/operation별이며 half-open probe 한
개만 허용한다.

## Backpressure and rate limiting

- admission 전에 queue capacity를 검사해 사용자가 이해할 busy 응답을 준다.
- Discord user/guild별 expensive command token bucket, Watch IP/session별 HTTP·WS bucket을 둔다.
- coalescible dashboard/status update는 최신 revision 하나로 합친다.
- queue/favorites/playlist는 storage pagination과 Discord 25-option pagination을 분리한다.
- slow consumer 때문에 producer/다른 session이 기다리지 않게 per-client send queue를 둔다.

## Race invariants to test

동시 play/skip, queue move/remove와 stale UI, TTS와 track completion, retry와 cancel, snapshot과
mutation, Watch join과 30초 expiry, last disconnect와 reconnect, add oEmbed와 close, duplicate
admin close, shutdown과 play-count commit을 deterministic scheduler/fake clock으로 검사한다.
