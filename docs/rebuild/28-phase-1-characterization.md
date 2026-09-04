# 28. PHASE 1 Characterization Report

## Phase 1 Complete

### Implemented

- `tests/characterization/`에 8개 slash command와 mention help, component, music,
  engagement, Summary, Watch, DB recovery 계약을 추가했다.
- 각 test는 Feature ID, FR ID와 `PRESERVE`/`CORRECT` metadata를 가지며 이를 검사하는
  meta-test를 추가했다.
- V1을 직접 실행하는 보존 test와 승인된 교정 동작의 strict expected-failure를 분리했다.
- V1 feature code, V2 source/package/architecture, SQLite schema/backup/music JSON 형식은
  변경하지 않았다.
- production DB migration/cutover, host 설치, tunnel 변경은 실행하지 않았다.

### Tests

- `.venv\\Scripts\\python.exe -m pytest tests\\characterization -q`
  - `41 passed, 13 xfailed`
- `.venv\\Scripts\\python.exe -m pytest tests\\`
  - `171 passed, 13 xfailed`
- `.venv\\Scripts\\python.exe -m pytest tests\\ -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
  - `171 passed, 13 xfailed`

13개 strict xfail은 PHASE 1에서 고치지 않은 승인 결함이다: pagination, zero-byte DB,
ranking 완료분 parity, calendar validation, Feb-29 fallback, legacy volume 0.5, Summary
ACL/timeout/active limit/queue capacity/raw redaction, Watch durable ordering/single responder.
skip은 없으며 unexpected pass도 없다.

유일한 warning은 Python 3.12에서 discord.py가 import하는 stdlib `audioop`의 Python 3.13
제거 예정 DeprecationWarning이다. RuntimeWarning과 unraisable coroutine/resource warning은 없다.

### Architecture Check

production code와 목표 architecture 구현을 시작하지 않았으므로 새 dependency 방향 위반은
없다. Test는 V1 public adapter/state를 호출하거나 fake dependency를 주입하며 domain package,
port, actor, process skeleton을 만들지 않았다. 기존 same-process Watch, global DB lock과 mutable
MusicState를 승인 architecture로 추인하지 않는다.

### Reliability Check

- retry clock, autoplay provider failure, voice/birthday fake clock, Summary stall/concurrency,
  Watch protocol/30초·5초 clock과 corrupt DB failure를 deterministic하게 실행했다.
- DB는 공통 isolated fixture와 per-test `tmp_path`만 사용했다.
- 외부 Discord/Gemini/YouTube/oEmbed/network/subprocess를 모두 fake/mock 처리했다.
- strict warning 실행으로 미정리 coroutine/unraisable exception이 없음을 확인했다.
- 더 큰 race/fault/load 항목은 `27-concurrency-failure-plan.md`에 trigger, invariant와 담당
  Phase를 기록했다.

### Pi Impact

Runtime 변경이 없어 production CPU/RAM/disk/subprocess 영향은 0이다. Production Pi나 DB에
접속하지 않았다. Target은 Raspberry Pi 5, Ubuntu Server 24.04 LTS ARM64, Ethernet/LAN의
clean bot-only host로 갱신했다. WordPress/CloudPanel과 이전 Cloudflare Tunnel/DNS baseline은
폐기하며, 실제 capacity/SLO는 새 Watch tunnel을 포함한 PHASE 9 staging에서 측정한다.

### Compatibility

- 8개 slash name/type/required/default, public/ephemeral와 unavailable/error shell을 고정했다.
- mention-only default help, player/queue/favorite/search/Summary/Watch/admin component를 고정했다.
- queue/loop, 3초·8초·세 번째 skip, autoplay 성공/실패, legacy snapshot shape/restore를 고정했다.
- text/voice XP, profile/ranking, master birthday CRUD/list/KST clock을 고정했다.
- Watch HTTP path/body, WS 7개 input type과 emitted join/leave ordering, invalid close code,
  30초/5초 lifecycle을 고정했다.
- `/내정보`는 실제 V1처럼 ephemeral임을 확인해 기존 inventory의 “공개” 표기를 정정했다.

### Corrected Legacy Bugs

PHASE 1에서는 runtime bug를 수정하지 않았다. 대신 다음을 golden behavior로 복제하지 않도록
정상 계약으로 고정했다.

- autoplay missing `extract_ytdlp_info` NameError 대신 실제 recommendation enqueue 성공
- 0-byte DB 자동 schema 승격 대신 fail-closed
- Summary ACL, 60초 timeout, active 1/waiting 4, raw parse output redaction
- queue/favorite/search/topic pagination과 stable identity
- profile/ranking의 완료된 voice minute parity
- 실제 calendar 날짜와 비윤년 Feb-29→Feb-28
- legacy snapshot volume의 단일 0.5 default와 restore ACK 이후 consume
- Watch durable session-before-invite와 post-ACK single responder

### Documentation Updated

- `docs/operations.md`: clean Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet 운영 범위
- `01`, `02`, `07`, `13`, `20`, `22`, `25`: 새 production/tunnel/baseline/migration 가정
- `23-decision-log.md`: ADR-016 accepted
- `24-requirement-test-trace.md`: PHASE 1 mandatory overlay와 executable evidence
- `26-characterization-contracts.md`: 기능별 golden/corrective contract
- `27-concurrency-failure-plan.md`: 22개 deterministic concurrency/failure scenario
- `README.md`, `CHANGELOG.md`: 산출물 링크와 변경 기록

### Remaining Risks

- 13개 `CORRECT` strict xfail은 의도적으로 V1에서 아직 충족되지 않는다. 담당 Phase 구현 전
  production behavior가 바뀌지 않았다는 뜻이며, 구현 완료로 계산하지 않는다.
- 실제 Discord permission/interaction deadline, voice/FFmpeg, browser, tunnel과 Pi load/soak는
  unit fake만으로 증명할 수 없어 staging gate가 남아 있다.
- snapshot version/checksum/restore ACK, Summary bounded worker, Watch slow peer isolation,
  DB explicit bootstrap은 후속 Phase의 구현·fault test가 필요하다.
- production RAM/storage/filesystem, tunnel/firewall/service account와 SLO 수치는 미측정이다.

### Next Phase Gate

PHASE 1 exit 조건인 주요 사용자 계약 coverage, autoplay success path, corrupt/zero-byte DB test,
concurrency/failure plan을 충족했다. PHASE 2 entry 시에는 이 characterization suite를 변경 전
baseline으로 실행하고, runtime package 추가 전에 no-side-effect import와 dependency rule을
검증해야 한다.

PHASE 2는 자동으로 시작하지 않는다. 사용자 지시가 있을 때만 진입한다. Production DB
migration/cutover는 계속 금지된다.
