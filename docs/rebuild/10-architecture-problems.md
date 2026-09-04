# 10. Architecture Problems

| smell | 구체적 dependency/실행 흐름 | 결과 | target boundary |
| --- | --- | --- | --- |
| God Module | `database_manager.py`가 connection, recovery, schema, crypto, Git, 6 table CRUD를 모두 소유 | 모든 기능과 운영 변경이 한 module 위험으로 결합 | context별 repository + migration/backup service |
| God Object | `MusicState`가 domain state, Discord object, playback, retry, UI, DB 통계를 소유 | callback 간 invariant와 lifecycle 검증 곤란 | pure music domain + guild actor + outbound ports |
| Hidden Dependency | string `get_cog`, `bot.log`, `app.state.bot`, UI의 `Any` callback | load order/runtime에서만 실패, static test 어려움 | composition root의 명시 constructor dependency |
| Tight Coupling | Discord handler가 yt-dlp/DB/voice/UI를 직접 orchestration | interaction deadline과 vendor failure가 use case에 누수 | thin inbound adapter → application command |
| Shared Mutable Global | DB lock, Gemini client, Watch manager, state dict, summary deque | unrelated guild/feature failure가 전파 | lifecycle-scoped services; actor/partition owner |
| Business Logic in Handler | XP/date/master/voice/channel rule이 event/command 안에 산재 | 동일 규칙이 profile/rank에서 달라짐 | testable domain policy/value objects |
| Infrastructure Leakage | domain-ish music core가 Discord/FFmpeg/DB wrapper를 앎 | simulator/unit test가 실제 SDK shape에 종속 | ports and DTOs, domain stdlib only |
| Configuration Scatter | env가 module import 곳곳에서 parse, default 불일치 | 한 오타가 extension만 조용히 누락 | typed immutable config, startup validation |
| Magic Value | 30/5초, 3/8초, 50곡, cache sizes, KST 9 등이 local literal/config 혼재 | 정책 의도·변경 영향 불명 | named policy config + contract tests |
| Error Swallowing | broad `except`, autoplay/TTS/load failure log-only | broken feature가 online으로 보이고 task error 소실 | typed error, supervisor, readiness/degraded registry |
| Missing Timeout | Gemini, metadata, gTTS, Git/pip 등 | resource 고착·retry overlap | dependency별 end-to-end deadline |
| Missing Boundary | Watch public web and Discord share process/loop/storage functions | external traffic가 Gateway health에 영향 | separate Watch process + authenticated loopback API |
| Duplicate/Drifted Logic | XP formula, volume defaults, response helper가 경로별 다름 | 동일 상태의 사용자 결과 불일치 | one policy/use case and golden contract |
| Missing Validation | dates, WS frames, queue/favorite size, config, DB health | invalid/unbounded state가 깊은 layer까지 진입 | boundary schemas + domain invariants |
| Uncontrolled Background Work | raw `create_task`, logging futures, WS reconnect | owner/cancellation/error/capacity 불명 | TaskSupervisor with name/owner/deadline/capacity |
| Persistence Coupling | SQLite row shape와 backup/recovery가 business call에 직접 노출 | schema 변경과 rollback 위험 증가 | compatibility repository, versioned migrations |
| Deployment Environment Dependency | hardcoded `/home/os/bot`, live venv, docs-only unit/cron | 재현·atomic rollback 불가 | tracked release manifest/unit/timer and immutable dirs |

정적 import cycle 자체는 확인하지 않았지만 runtime lookup cycle이 같은 효과를 낸다. 새
구조는 현재 directory를 정리하는 수준이 아니라 dependency 방향을 compile/import test로
강제해야 한다.

## Architecture constraints

1. Discord/FastAPI adapter는 repository나 vendor client를 직접 호출하지 않는다.
2. domain은 `discord`, `fastapi`, SQLite, Gemini, yt-dlp type을 import하지 않는다.
3. use case는 port만 의존하고 adapter object를 반환하지 않는다.
4. background task는 supervisor 밖에서 생성하지 않는다.
5. mutable guild/session state에는 정확히 한 owner가 있어야 한다.
6. external call, subprocess, queue에는 deadline과 capacity가 있어야 한다.
7. partial startup은 readiness에 반영하고 사용자/운영자에게 degraded capability를 노출한다.
8. compatibility format 변경은 versioned adapter와 rollback proof 없이는 배포하지 않는다.
