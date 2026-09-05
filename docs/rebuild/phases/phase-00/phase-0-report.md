# PHASE 0 Baseline Report

## Phase 0 Complete

### Implemented

- 현재 `docs/rebuild/baseline/`에 보존된 최초 분석 문서와 당시 00–23 문서를 원문 전체로
  검토했다.
- V1 entrypoint, DB/recovery, Discord command/event, Summary, Music, Watch, engagement와 현재
  pytest 구조를 실제 코드에서 대조했다.
- 마스터 프롬프트의 확정 결정을 `docs/rebuild/current/open-questions.md`, FR mode와
  ADR-001–ADR-015에 반영했다.
- F001–F045 ↔ FR ↔ 현재 test/PHASE 1 proof를
  `docs/rebuild/current/requirement-test-trace.md`로 작성했다.
- 작업 branch를 `codex/rebuild-v2`로 분리했다. PHASE 0에서는 feature source와 V1 code를
  수정하거나 목표 `src/discordbot` skeleton을 조기에 만들지 않았다.

### Tests

환경과 격리를 확인한 뒤 저장소 `.venv`의 Python 3.12.14로 실행했다. 최초 `python` PATH
호출은 interpreter가 없어 시작되지 않았으며 아래 두 실제 실행은 모두 성공했다.

```text
.\.venv\Scripts\python.exe -m pytest tests/
130 passed, 1 warning in 3.51s

.\.venv\Scripts\python.exe -m pytest tests/ \
  -W error::RuntimeWarning \
  -W error::pytest.PytestUnraisableExceptionWarning
130 passed, 1 warning in 3.52s
```

유일한 warning은 discord.py가 import하는 `audioop`의 Python 3.13 제거 예고다. test fixture는
DB와 SQL backup을 pytest 임시 경로로 치환하며 Discord/Gemini/YouTube/Git/systemd 호출은
mock 또는 정적 script 검사다. 실제 `data/bot_database.db`와 실제 backup/log 내용은 읽거나
수정하지 않았다.

### Architecture Check

현재 V1은 목표 architecture를 만족하지 않으며 이것이 재구축 사유다. 코드 대조로 다음을
재확인했다.

- `main_bot.py`가 DB 후 같은 event loop에서 Uvicorn을 raw task로 시작하고 Cog load/sync
  failure 뒤에도 계속 진행한다.
- DB async 함수가 process-global `asyncio.Lock`을 잡은 채 default executor의
  `asyncio.to_thread`를 기다린다.
- Discord handler/UI/voice callback이 `MusicState`의 queue/current/mode/voice를 직접 변경한다.
- Summary/Watch/engagement adapter가 DB/vendor/global config에 직접 결합한다.
- architecture import rule을 검증하는 현재 test는 없다. import 성공 test만 있다.

PHASE 2 전까지 이 경계를 새 V2 feature code에 복제하지 않는다.

### Reliability Check

- 현재 suite는 정상 shutdown task cancel, playback 3초/8초/third-skip, download timeout/cleanup,
  atomic music-state write, encrypted backup round-trip과 Watch cleanup 일부를 검증한다.
- autoplay successful lookup, existing zero-byte/corrupt DB, Gemini timeout/concurrency/ACL,
  real Watch WebSocket/slow peer, DB executor saturation, music callback races, birthday/voice XP,
  live-write backup과 deploy rollback은 검증하지 않는다.
- `MusicState._prefetch_autoplay_song()`은 import되지 않은 `extract_ytdlp_info`를 호출하므로
  V1 autoplay success가 실패한다. 이는 `CORRECT` 대상이며 golden behavior로 만들지 않는다.
- `MusicStateStore.load_once()`는 JSON parse 직후 파일을 삭제해 실제 guild restore ack 전에
  recovery point를 소비한다.

### Pi Impact

PHASE 0 작성 뒤 사용자가 production target을 Raspberry Pi 5, Ubuntu Server 24.04 LTS
ARM64, Ethernet/LAN으로 확정했다. 실제 RAM/storage/filesystem에는 아직 접근하지 않았으며
추측하지 않는다. 과거 WordPress/CloudPanel 포함 host baseline은 폐기하고, 깨끗한 새 Pi의
PHASE 9 staging에서 다음 read-only baseline과 부하 계획을 새로 측정한다.

| Profile | Duration | Measure | Gate/use |
| --- | --- | --- | --- |
| V1 idle | 최소 30분 | process CPU/RSS, threads, FD, disk/log growth, event-loop lag, reconnect | 현재 weekly reboot와 idle cost 기준선 |
| representative commands | 반복 burst | ACK/defer, command phase, DB queue/execute, external latency/error | typed capacity의 초기값 검증 |
| music/summary/Watch busy | peak의 2배 목표 | FFmpeg/yt-dlp process, download active, Gemini queue, WS relay/slow client | workload isolation과 backpressure |
| fault injection | scenario별 | network loss, DB busy, provider timeout, Watch/FFmpeg crash, process kill | readiness/degraded/restart/recovery |
| soak | staging에서 최소 24시간 | RSS/task/thread/FD/cache/log slope와 DB latency | leak 부재와 weekly reboot 재검토 |

OS/process baseline은 `/proc`, `systemctl`, filesystem 통계처럼 Pi에 이미 있는 read-only 수단을
우선하고, application metric은 PHASE 2 telemetry가 제공한다. 수치는 release/environment와 함께
기록하며 SLO proposal을 맞추기 위해 기능을 약화하지 않는다.

### Compatibility

- F001–F045를 inventory에서 제거하지 않았다.
- 8개 slash command, mention help, interaction publicness, button/select/modal 의미, music
  retry/queue/loop/autoplay/favorite/restore, XP/birthday, Watch HTTP/WS와 30초/5초 semantics,
  SQLite/V2+legacy backup/music JSON을 trace에 유지했다.
- favorite는 user-global이고 guild-scoped state/data/config는 `guild_id`로 격리한다.
- V1 code와 schema/data format에는 변경이 없다.

### Corrected Legacy Bugs

PHASE 0에서는 runtime bug를 수정하지 않았다. 다음 결함을 V2 요구사항의 `CORRECT`로 확정했다.

- autoplay unimported-symbol failure
- existing zero-byte/corrupt DB recovery bypass
- Summary source ACL/timeout/capacity 부재
- queue stale index와 multi-owner music race
- retry/TTS resume play-count 중복
- profile/ranking voice XP rounding drift
- invalid birthday 허용과 multi-guild fixed-channel leak
- Watch invite-before-commit, slow-peer broadcast와 close/add/connect race
- snapshot restore ack 전 삭제

### Documentation Updated

- `docs/rebuild/baseline/01-current-system-overview.md`: PHASE 0에서는 Pi model을 미확정으로 두었고, PHASE 1의
  사용자 결정으로 Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet target을 확정
- `docs/rebuild/baseline/12-functional-requirements.md`: 승인된 master/guild/help/play-count/volume/Summary/XP/birthday 결정 반영
- `docs/rebuild/current/open-questions.md`: BLOCKER 8개 closure와 deferred measurement gate 분리
- `docs/rebuild/current/architecture-decision-log.md`: ADR-001–012 ACCEPTED, ADR-013–015 추가
- `docs/rebuild/current/requirement-test-trace.md`: F001–F045 trace와 coverage gap
- `README.md`: PHASE 0 산출물 링크

### Documentation discrepancy

```text
Document: docs/rebuild/baseline/01-current-system-overview.md
Claim: production host는 Raspberry Pi 5다.
Actual code/test: repository는 host hardware를 검증하지 않지만 사용자가 PHASE 1에서 장비와 OS/network target을 확정했다.
Evidence: Raspberry Pi 5, Ubuntu Server 24.04 LTS ARM64, Ethernet/LAN이 승인됐고 RAM/storage/filesystem metric은 아직 없다.
Impact: 장비 identity와 아직 측정하지 않은 capacity를 구분해야 한다.
Resolution: 장비/OS/network는 확정값으로 갱신하고, 나머지 자원과 SLO는 clean Pi staging 측정 전 미확정으로 유지한다.
```

그 외 핵심 감사 주장인 global DB lock/default executor 결합, partial startup, autoplay
`NameError`, Summary ACL/cap 부재, Watch same-loop sequential broadcast와 invite-before-commit은
현재 코드와 일치했다.

### Remaining Risks

- 45개 중 현재 contract test 상태는 `COVERED 1`, `PARTIAL 25`, `GAP 18`, `CORRECT-GAP 1`이다.
- command/embed/button의 exact golden artifact가 아직 없다.
- Raspberry Pi와 staging Discord E2E baseline은 아직 실행하지 않았다.
- backup retention 개수, queue/cache byte cap과 alert threshold는 실측 전 제안값이다.
- current V1 test success는 목표 architecture, concurrency/failure isolation 또는 production
  recovery 성공을 의미하지 않는다.

### Next Phase Gate

**PHASE 1 진입 가능: YES.** 미해결 BLOCKER는 0개이며 branch, decision source와 trace가
준비됐다. PHASE 1은 feature fix가 아니라 다음 순서의 characterization 작업으로 시작한다.

1. 8 slash command와 mention help의 signature/publicness/error golden contract
2. button/select/modal custom ID, ordering, response와 >25 pagination contract
3. music queue/loop/retry/autoplay intended behavior와 snapshot compatibility
4. XP/voice move/profile-ranking/birthday fake-clock contract
5. Watch HTTP/WS 7-type, 30초/5초와 admin-close contract
6. existing 0-byte/corrupt DB와 concurrency/failure test plan

### Decision Required

없음. Production 접근, secret, migration, cutover, key 교체 또는 V1 삭제가 필요한 phase에서만
별도 승인을 요청한다.
