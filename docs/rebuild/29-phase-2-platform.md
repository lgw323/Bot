# 29. PHASE 2 Platform Report

## Phase 2 Complete

### Implemented

- Python 3.12 `src` layout과 import-safe `discordbot` V2 package를 추가했다.
- 명시적으로 전달한 environment mapping만 읽는 frozen typed config와 Raspberry Pi 5용
  task/telemetry/metric/executor hard limit을 구현했다.
- safe public message와 internal context를 분리한 cross-context typed error taxonomy, injectable
  clock/ID와 nested correlation context를 구현했다.
- 중앙 redaction, bounded non-blocking event buffer, bounded-cardinality metric registry와
  `live`/`ready`/dependency/capability health registry를 구현했다.
- `TaskSupervisor`가 모든 V2 background task의 name, owner, work ID, correlation, deadline,
  criticality, cancellation, bounded restart와 shutdown phase를 소유하고 terminal exception을
  회수하도록 구현했다.
- running+waiting admission을 제한하는 blocking executor와 startup rollback, admission stop,
  bounded task drain/cancel, reverse resource close를 수행하는 process runtime을 구현했다.
- Discord와 Watch에 독립 composition root를 만들었지만 Discord/FastAPI adapter나 실제 process
  entrypoint는 연결하지 않았다.
- music, summary, engagement, watch, operations의 layer/package boundary만 만들었다. 실제 feature
  domain/application/adapter는 비어 있으며 migration을 시작하지 않았다.

### Tests

- `.venv\\Scripts\\python.exe -m pytest tests\\architecture tests\\unit\\platform -q`
  - `40 passed`
- `.venv\\Scripts\\python.exe -m pytest tests\\characterization -q`
  - `41 passed, 13 xfailed`
- `.venv\\Scripts\\python.exe -m pytest tests\\ -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
  - `211 passed, 13 xfailed`

13개 strict xfail은 PHASE 1에서 확정한 담당 Phase 이전 CORRECT spec이다. PHASE 2 범위 밖
feature를 억지로 XPASS시키지 않았고 skip은 없다. 유일한 일반 warning은 Python 3.12의
discord.py `audioop` 제거 예정 DeprecationWarning이며 RuntimeWarning/unraisable warning은 없다.

### Architecture Check

- AST test가 V2 domain/application/ports/adapters dependency 방향과 cross-context 격리를 강제한다.
- vendor와 `sqlite3`는 adapter 밖에서 import할 수 없고, composition은 feature adapter만 조립할
  수 있다.
- raw `create_task`/`ensure_future`는 `platform/tasks.py`, thread/process executor와 blocking
  dispatch는 `platform/executors.py`만 사용할 수 있다.
- fresh isolated Python process에서 모든 V2 module을 import하며 SQLite connect, socket/server,
  subprocess, thread/task 생성, environment read와 root logging mutation이 없음을 확인했다.
- V1 root module과 `cogs/`, 현재 schema/data format은 architecture rewrite 대상에 넣지 않았다.

### Reliability Check

- invalid/over-limit config가 resource 생성 전 `ConfigurationError`로 fail-fast한다.
- task capacity rejection은 coroutine을 만들지 않으며 success/failure/deadline/transient retry/
  cancellation terminal result와 exception을 모두 observation history에 남긴다.
- task active set, history, telemetry queue, metric series, executor running+waiting slot은 모두 hard
  cap이 있고 overload를 drop counter 또는 typed `CapacityError`로 드러낸다.
- executor awaiter가 취소되어도 실제 worker thread가 끝날 때까지 capacity를 반환하지 않는다.
- required resource startup failure는 readiness=false와 reverse rollback을 만들고, 정상 shutdown은
  admission을 닫은 뒤 task를 drain/cancel/reap하고 resource를 역순으로 닫는다.

### Pi Impact

- 기본값은 supervised task 64, telemetry event 512, metric series 256, blocking worker 2와 waiting
  slot 8이다. config validation 최대값은 각각 256, 8192, 4096, worker 4, waiting 64다.
- 이 수치는 Raspberry Pi 5 clean staging 전의 보수적 hard ceiling이며 acceptance baseline이나
  확정 SLO가 아니다. PHASE 9에서 Ubuntu Server 24.04 LTS ARM64/Ethernet 환경으로 측정한다.
- module import는 worker thread/process/socket/DB를 만들지 않는다. explicit runtime composition도
  실제 work가 admission되기 전 thread를 시작하지 않는다.
- Raspberry Pi 설치, Git clone 운영 설치, systemd, auto-update/backup, Watch tunnel을 실행하거나
  활성화하지 않았다.

### Compatibility

- V1 source, command/component/Watch protocol, SQLite schema/SQL backup, `music_state.json`과 runtime
  route를 변경하지 않았다.
- PHASE 1 PRESERVE suite는 `41 passed`를 유지했고 13개 strict CORRECT xfail도 동일하게 남았다.
- V2 package는 기존 `main_bot.py`에서 import하거나 시작하지 않으므로 현재 production-compatible
  behavior와 data owner는 V1 그대로다.

### Corrected Legacy Bugs

이번 Phase에서는 V1 feature bug를 수정하지 않았다. autoplay, pagination, Summary, Watch ordering,
0-byte DB 등 PHASE 1 strict CORRECT spec은 담당 migration Phase까지 xfail로 유지한다.

### Documentation Updated

- ADR-017에 platform ownership, bounds, process composition과 후속 범위 제한을 기록했다.
- async/task, error, observability, target repository와 migration plan에 실제 PHASE 2 구현 상태를
  반영했다.
- requirement-test trace에 NFR/FR별 platform executable evidence를 추가했다.
- 재구축 README, project README와 CHANGELOG에 V2 skeleton 위치와 미활성 상태를 기록했다.

### Remaining Risks

- 실제 Discord/FastAPI/SQLite/Gemini/media adapter와 feature capability는 아직 없어 health가 실제
  외부 dependency를 probe하지 않는다. health HTTP route와 metric exporter도 미구현이다.
- SQLite는 adapter-only import rule과 context port package만 준비했다. DB worker, repository,
  compatibility reader, migration ledger와 recovery 구현은 PHASE 3 범위다.
- Python thread는 실행 중 강제 중단할 수 없다. shutdown grace를 넘긴 blocking work는 executor
  error/degraded shutdown으로 관찰되지만 해당 함수의 cooperative timeout은 adapter가 제공해야 한다.
- AST import rule은 동적 import/plugin wiring을 모두 증명하지 않으므로 feature adapter가 생길 때
  integration test를 추가해야 한다.
- capacity와 shutdown 시간은 clean Raspberry Pi staging 실측 전 proposal이다.

### Next Phase Gate

PHASE 2 exit 조건인 no-side-effect import, raw background task 차단, invalid config fail-fast,
graceful shutdown과 executable architecture rule을 충족했다.

PHASE 3는 사용자 지시가 있을 때만 시작한다. 진입 시 임시 DB/copy fixture에서 repository
boundary, DB worker/capacity, migration ledger, explicit bootstrap, legacy schema/backup read와
corrupt recovery를 구현한다. production DB migration/cutover, Pi 배포와 운영 service 활성화는
계속 금지한다.
