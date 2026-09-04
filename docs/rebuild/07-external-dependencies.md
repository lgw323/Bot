# 07. External Dependencies

| dependency | 기능·설정 | 현재 timeout/recovery | target policy |
| --- | --- | --- | --- |
| Discord Gateway/REST/voice | 모든 command/event/UI/voice; token/intents | library reconnect, readiness 없음 | adapter 격리, ACK budget, REST error 분류, ready/gateway metric |
| Google Gemini | summary; API key/model/token/temp | timeout/retry/semaphore/circuit 없음 | 60s total, transient 최대 2회, concurrency 1/queue 4 제안, circuit breaker |
| yt-dlp/YouTube | search/metadata/download/autoplay | metadata timeout 없음; download 180s×clients/retries | 전용 executor, metadata 20s, global bounded download, provider fallback metric |
| FFmpeg | Discord audio/TTS transcode | PATH startup check 없음 | startup capability probe, subprocess deadline/kill/reap |
| gTTS | voice join speech | timeout 없음, 실패 일부 silent | 별도 pool, deadline, optional degraded mode |
| YouTube oEmbed | Watch title | aiohttp 5s, fallback title | shared session, 5s budget, bounded retry/cache |
| YouTube IFrame/CDN | browser player | browser network 의존 | client-visible degraded state, CSP/origin policy |
| FastAPI/Uvicorn/WebSocket | Watch internet surface | same loop/task, 0.0.0.0:8000 | separate process, health, frame/rate/cap/backpressure |
| SQLite | 모든 durable feature | new connection/global lock/WAL | repository, short transactions, online snapshot, latency/lock metric |
| Git code origin | 5분 auto-update | timeout/lock/test gate 없음 | immutable release fetch/build/smoke/atomic switch |
| private backup Git | encrypted latest backup | force-push latest, local archives | immutable/object history 또는 protected retention, age alert/restore drill |
| Fernet key | backup confidentiality/integrity | single key, rotation metadata 없음 | secret store/file permission, key ID/rotation/old-key policy |
| Deno/npm/PO provider | YouTube challenge | fixed provider 1.3.1, live install | release artifact에서 pin/probe/rollback |
| systemd/cron/sudo/bash | process/schedule | docs-only config, overlapping jobs | tracked units/timers, restricted user, `flock`, deadlines |
| Cloudflare Tunnel | Watch public URL 추정 | repo에 config/health 없음 | exposure/auth/TLS/firewall decision + managed health |

## Dependency policy

- domain과 application use case는 위 SDK를 import하지 않는다. port를 구현하는 adapter만
  vendor type을 안다.
- 모든 remote call은 total deadline, retry eligibility/budget, concurrency budget,
  correlation ID, latency/result metric이 있어야 한다.
- retry는 idempotent하거나 idempotency key가 있는 작업에만 jittered exponential backoff로
  수행한다. Discord/HTTP response를 중복 전송하지 않는다.
- dependency failure는 feature-scoped degraded state가 되며 Discord gateway process 종료로
  전파하지 않는다. 필수 startup dependency 실패만 readiness를 내린다.
- aiohttp/client/executor는 request마다 만들지 않고 lifecycle owner가 생성·종료한다.
- version은 lock/release manifest로 재현하고, yt-dlp 긴급 갱신은 별도 canary/rollback 경로를 둔다.

## Environment/configuration gaps

`DEBUG_MODE`는 소비되지 않고, `YTDLP_POT_PROVIDER_DIR`은 template에 없다. 숫자 설정은
import 시 변환되어 잘못된 값 하나가 Cog load failure가 되며, summary retention/load 기본값은
코드와 template가 다르다. target은 시작 시 한 번 typed config로 전부 검증하고 secret 값은
출력하지 않은 채 모든 오류를 함께 보고한다.
