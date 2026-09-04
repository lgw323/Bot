# 19. Testing Strategy

## 현재 기준선

2026-09-04 로컬 venv에서 `pytest tests/ -q`를 실행해 **130 passed, 1 warning,
3.74s**를 확인했다. `tests/conftest.py`는 DB와 backup path를 `tmp_path`로 치환하고 주요
Discord/외부 API를 mock한다. 경고는 Python 3.13에서 제거 예정인 `audioop` 관련이다.

통과는 현재 suite 범위만 의미한다. birthday, 실제 WebSocket, autoplay 성공, executor
포화, zero-byte/corrupt DB, live-write backup, migration partial state, deployment rollback,
Pi 성능은 충분히 검증하지 않는다. shell test는 대부분 script 문자열 검증이다.

## Test pyramid and contracts

| 계층 | 대상 | 원칙/도구 |
| --- | --- | --- |
| domain unit | XP/date/music/session state machine, retry/backoff | no Discord/DB/network; fake clock/ID; exhaustive state table |
| application unit | authz, use-case orchestration, idempotency, error mapping | fake ports; deterministic scheduler |
| repository integration | schema/migration/CRUD/backup/restore/concurrency | temp SQLite only; wrong key/corruption/partial migration |
| adapter contract | 8 slash, UI, HTTP 4, WS types 7 | captured golden payload/text/ephemeral/permission |
| external adapter | Gemini/yt-dlp/oEmbed/Discord/FFmpeg | recorded schema or fake server/subprocess; no live CI dependency |
| concurrency/failure | actor races, queue pressure, slow peer, executor saturation | barriers/fake sockets/fault injection, bounded time |
| restart/deploy | snapshot, stale Watch, voice XP, release/rollback | temp release dirs/fake systemd; staging Pi rehearsal |
| end-to-end staging | actual Discord test guild/voice/browser | dedicated token/guild, no production data |

## Characterization before migration

각 F001–F045에 requirement/test ID를 연결한다. 우선 8 slash command의 이름, parameter,
message text, embed field, ephemeral/public, defer/followup, button/select/modal custom ID와 순서,
music loop/retry/timing, XP formula, birthday time, Watch path/payload/close code를 golden artifact로
고정한다. 현재 버그를 golden으로 만들지 않도록 `PRESERVE/CORRECT/DECIDE`를 함께 기록한다.

## Mandatory scenarios

### Music

- concurrent URL/search completion에도 request ordering invariant를 검증한다.
- simultaneous skip/after/retry/TTS, stale queue/favorite UI, actor mailbox full을 검사한다.
- autoplay recommendation 성공과 provider failure, 3초/8초/third-skip fake clock을 검사한다.
- cache hit/miss/partial/oversize/eviction/disk full, subprocess timeout/kill/reap을 검사한다.
- snapshot mutation 중 capture, malformed/version mismatch, guild 일부 restore failure, ack 이후
  consume와 crash/restart를 검사한다.

### Summary/engagement

- preload/live boundary message ID의 no-gap/no-duplicate, retention, reconnect idempotency를 검사한다.
- source ACL, prompt injection payload separation, Gemini timeout/429/5xx/circuit/queue-full을 검사한다.
- text XP character table, voice join/move/leave/crash checkpoint, profile/ranking 동일 공식을 검사한다.
- real calendar/Feb29, KST clock, duplicate daily run, multi-guild channel isolation을 결정 후 검사한다.

### Watch

- actual ASGI HTTP+WebSocket handshake, 7 message schema, malformed/oversize/rate limit을 검사한다.
- slow/disconnected client가 다른 peer를 막지 않음, ordering/revision, bounded queue를 검사한다.
- join vs 30초 expiry, disconnect/reconnect vs 5초 expiry, add/oEmbed vs close, duplicate master
  close, restart stale cleanup, terminal browser reconnect 중단을 race test한다.
- session commit 전에 invite가 공개되지 않고 Discord send 실패 시 compensation되는지 검사한다.

### Data/operations

- missing/zero-byte/corrupt/wrong-schema DB, local corrupt+remote good, wrong key/tamper/legacy/V2를 검사한다.
- live concurrent writes 중 snapshot의 referential/semantic consistency와 atomic publish를 검사한다.
- ordered migration checksum/idempotent resume/partial failure/old reader compatibility/rollback을 검사한다.
- updater lock, overlapping timer/manual call, network hang, bad dependency, readiness failure,
  release+venv rollback, disk full을 temp sandbox에서 검사한다.

## Non-functional verification

Pi staging에서 normal/burst/soak/fault profile을 실행하고 ACK, command phases, event-loop lag,
executor/actor queue, DB wait/execute, RSS/CPU/disk/FD, WS relay를 측정한다. capacity는 실제 친구
서버 peak의 최소 2배 또는 승인된 수치로 시험한다. 24시간 soak에서 unbounded memory/task/file
증가가 없어야 한다.

## CI and gates

PR마다 format/lint/type/import-boundary, unit, repository, adapter contract를 실행한다. merge
후 integration/failure/security를, release 전 Pi smoke/restore/migration/rollback을 실행한다.
network 없는 test가 기본이며 실제 `.env`, DB, SQL, log/cache는 절대 읽거나 생성·commit하지
않는다. flaky test는 재시도로 숨기지 않고 격리/owner/기한을 둔다.
