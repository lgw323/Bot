# 16. Error Handling Policy

## Typed error taxonomy

| category | 사용자 표시 | log | retry/alert | command/process 결과 |
| --- | --- | --- | --- | --- |
| `ValidationError` | 기존 형식의 구체적 수정 안내 | INFO | no/no | 해당 요청 종료 |
| `AuthorizationError` | 권한 없음, 민감 detail 없음 | INFO/WARN if suspicious | no, abuse threshold alert | fail closed |
| `NotFoundError` | 곡/session/data 없음 | INFO | no/no | 정상 실패 |
| `ConflictError` | stale UI/이미 종료/상태 변경, 새로고침 안내 | INFO | 자동 mutation retry 없음 | idempotent 현재 상태 반환 |
| `CapacityError` | 잠시 후 재시도/queue full | WARN metric | client retry hint; sustained alert | 빠른 실패, process 정상 |
| `ExternalTemporaryError` | 해당 기능 일시 장애 | WARN | idempotent+budget 안 최대 2; circuit alert | feature degraded |
| `ExternalPermanentError` | 요청/콘텐츠 처리 불가 | INFO/WARN | no; rate만 alert | 해당 요청 종료 |
| `DatabaseUnavailableError` | 저장 기능 일시 이용 불가 | ERROR | 짧은 bounded retry only; alert | write fail closed, readiness policy |
| `DataIntegrityError` | 운영자 확인 필요, detail 숨김 | CRITICAL | automatic destructive recovery no | writes/readiness 차단 가능 |
| `InternalError` | correlation ID 포함 일반 오류 | ERROR | no blind retry; alert by rate | 해당 use case 격리 |
| `ConfigurationError` | 사용자에게 기능 unavailable | ERROR/CRITICAL startup | no; 즉시 alert | 필수면 not ready, 선택이면 degraded |
| `Cancellation` | 취소/종료 상황에 맞는 메시지 | DEBUG/INFO | no/no | rollback/cleanup 후 종료 |

## Boundary rules

1. lower layer는 Discord message를 만들지 않고 typed error와 safe metadata만 반환한다.
2. adapter 한 곳이 response/defer/followup 상태를 소유한다. 이미 ACK된 interaction에
   `response.send_message`를 다시 호출하지 않는다.
3. broad catch는 process boundary/supervisor에서만 허용하며 exception, context, result를
   기록하고 health/state를 갱신한다. `except: pass`는 금지한다.
4. 사용자 메시지에는 stack, SQL, path, URL credential, session capability, vendor raw body를
   넣지 않는다.
5. log는 original exception chain과 typed code를 가지되 중앙 redaction 후 sink로 간다.

PHASE 2는 이 taxonomy를 `src/discordbot/platform/errors.py`의 `AppError`와 typed subclass로
구현했다. 내부 message/context와 사용자에게 노출 가능한 `safe_message`를 분리하고 context는
read-only mapping으로 보관한다. `DeadlineExceededError`, `StartupError`, `ShutdownError`는
platform lifecycle 경계를 명시한다. Discord/HTTP response mapping과 기존 한국어 UX 적용은
각 inbound adapter migration Phase의 책임이며 이번 Phase에는 연결하지 않았다.

## Transaction and idempotency policy

mutation은 `validate → authorize → reserve/admit → transaction/side effect → commit → respond`의
commit point를 문서화한다. Discord와 DB를 한 transaction으로 묶을 수 없으므로 Watch invite
등은 durable intent와 idempotency key, compensation을 가진 saga로 처리한다. 동일 interaction,
WebSocket frame, scheduler date, admin close가 재전달돼도 결과가 한 번만 적용돼야 한다.

## Process termination

사용자/외부/일반 DB 오류는 process를 종료하지 않는다. 필수 config invalid, schema/backup
integrity 위반, application invariant corruption처럼 계속 쓰면 데이터 피해가 커지는 경우만
readiness=false 후 orderly shutdown 또는 read-only fail-closed를 선택한다. supervisor가
unknown fatal exception을 반복하면 restart budget/circuit를 적용해 systemd restart storm을
막는다.
