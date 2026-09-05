# PHASE 2 Platform Contract

이 문서는 PHASE 2에서 baseline 설계에 대응해 구현한 platform contract를 보존한다. Baseline
문서는 이 구조 정리 이후 수정하지 않는다.

## TaskSupervisor and bounded executor

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

## Typed errors

Baseline taxonomy를 `src/discordbot/platform/errors.py`의 `AppError`와 typed subclass로 구현했다.
내부 message/context와 사용자에게 노출 가능한 `safe_message`를 분리하고 context는 read-only
mapping으로 보관한다. `DeadlineExceededError`, `StartupError`, `ShutdownError`는 platform
lifecycle 경계를 명시한다. Discord/HTTP response mapping과 기존 한국어 UX 적용은 각 inbound
adapter migration Phase의 책임이며 PHASE 2에는 연결하지 않았다.

## Telemetry and health

- `TelemetryBuffer`는 기본 512, config 최대 8192 event의 non-blocking FIFO이며 overflow를
  `dropped_count`로 남긴다. JSON handler는 explicit factory 호출로만 생성되고 root logger를
  import 시 변경하지 않는다.
- `MetricRegistry`는 기본 256, 최대 4096 label series만 허용하며 새 cardinality 초과를
  `CapacityError`와 drop counter로 표시한다. exporter/HTTP endpoint는 아직 연결하지 않았다.
- `HealthRegistry`는 composition 시 선언된 capability만 받아 동적 cardinality를 막는다.
  liveness, admission/readiness, `ok/degraded/down/unknown` dependency payload를 분리한다. 실제
  `/live`, `/ready`, `/dependencies` HTTP adapter는 Watch migration/Operations Phase에서 붙인다.
- telemetry field는 sink 전 key/inline secret redaction을 거친다. raw 사용자 ID나 URL을
  metric label로 사용하지 않으며 feature별 pseudonymization은 adapter 구현 시 추가한다.

## Repository and executable boundaries

PHASE 2에서 `pyproject.toml`, `src/discordbot/{composition,platform}`과 각 bounded context의 빈
layer boundary를 만들었다. Feature context package는 의도적으로 `__init__.py` 외 실제 use
case/domain/adapter 구현이 없다. `migrations/`, `deploy/`와 실제 persistence adapter는 각각
후속 Data compatibility/Operations Phase 전까지 만들거나 활성화하지 않는다.

Executable rule은 `tests/architecture/test_import_rules.py`에 있다. V2 source만 대상으로 layer
역방향·cross-context import, adapter 밖 vendor/SQLite, supervisor 밖 task 생성, bounded executor
밖 blocking dispatch와 Discord/Watch composition 결합을 거부한다. 같은 test가 fresh Python
process에서 모든 V2 module을 import해 DB/network/server/subprocess/thread/logging side effect가
없는지도 확인한다.
