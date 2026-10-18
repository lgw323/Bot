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

## A2R2 managed termination contract (2026-09-22 candidate)

- `composition.main.main` always enters the Linux synchronous guardian, including
  `deploy/launch.py` and module invocation. The worker requires an inherited
  AF_UNIX sequenced-packet socket whose peer is its parent; no public worker or
  timing flag exists. Worker control descriptors are non-inheritable, and Linux
  parent-death handling is armed before application initialization.
- `TerminationPolicy` centralizes S=60, G=20, H=90 with `0 < 3G < H`:
  application T0+G, loop T0+2G, owned-group kill T0+(H-G), reap ceiling T0+H.
  Repeated signals and cleanup stages do not restart T0. Unit templates retain
  TimeoutStopSec=90 and KillMode=control-group; MainPID is now the guardian and
  HTTP release/readiness identity remains the worker's.
- Lifecycle work has reserved, bounded ownership outside ordinary admission.
  Observation timeout requests cancellation without waiting for acknowledgement.
  Unfinished tasks/futures/resources retain ownership; unsafe dependencies are not
  closed underneath them. A cancelled shutdown caller cannot cancel the single
  runtime cleanup owner. A degraded shutdown remains FAILED on repeated calls.
- Executor close never joins threads on the event loop. Retained atomic-file
  ownership remains unchanged. The explicit loop owner observes task, asyncgen and
  default-executor cleanup to the shared loop deadline. Outstanding work remains
  owned until the independent guardian terminates the worker; no thread killing,
  asyncio internals patch or false interpreter-exit guarantee is used.
- The guardian owns one worker session/group, forwards stop, reaps group children
  as a Linux subreaper, and emits fixed non-secret outcome labels through a
  nonblocking local datagram sink. Sink unavailability never blocks termination.
  Clean completion requires successful worker exit, the completion marker and an
  empty owned group. Timeout, forced kill, unexpected crash and reap failure fail.
- Systemd owns the entire cgroup, including descendants that call setsid and
  cleanup after guardian death. Internal failure can additionally incur the unit
  stop budget, conservatively up to 2H overall. Kernel scheduling and killable
  tasks are assumptions; uninterruptible kernel I/O is never claimed bounded.
- Tests inject a short policy into the same guardian/worker implementation using
  fake assembly, temporary paths and independent transient-unit cleanup deadlines.
  Non-Linux managed startup fails closed; direct async application calls remain
  test seams, not a process-containment guarantee. Optional-start failure semantics
  are unchanged and remain the separate A2-M2 remediation.

## A2R3 optional startup contract (2026-09-22)

- `ManagedResource.required` governs both startup and readiness. Top-level optional
  declarations assert independence: every survivor must operate without that resource.
  No dependency graph exists. Ordered dependencies remain inside mandatory aggregates
  (including `DiscordFeatures`); a nested optional flag does not weaken the aggregate.
- Successful resources remain in reverse-order shutdown ownership. A required failure
  still fails startup and rolls back prior owners using A2R2 lifecycle deadlines.
- An optional exception sets its capability DOWN and emits fixed classification events.
  After proven partial cleanup, startup continues; required capabilities can be ready
  with an optional capability DOWN, without changing the public health representation.
- Failed optional starts default to one runtime-owned stop. Self-cleaning adapters expose
  `startup_cleanup_complete`, initially false and true only after cleanup is proven.
  Watch and Music participate explicitly; cleanup is never repeated after self-cleanup.
  Music conservatively refuses continuation while shared executor work remains admitted.
- Failed/timed-out cleanup retains the partial resource and healthy dependencies for
  existing outer containment, fails startup and cannot report readiness or clean shutdown.
  Cancellation remains cancellation. Cleanup uses the existing LifecycleTasks owner and
  startup/grace budget; no guardian, worker, process-group or 20/40/70/90 change.
- Candidate `7a29a4c9f7038c0fa15406d7021518e16e10874f`: Windows platform 50 PASS,
  directly dependent 77 PASS, collection 1,064, A0 isolation 5 PASS. One strict suite:
  1,037 PASS / 2 FAIL / 25 SKIP (70.22s). Failures are existing A2-N1 document inventory
  and missing Deno executable; no full-suite PASS claim. Linux exact export: 3 selected
  real guardian/systemd cases PASS (22 deselected), platform 50 PASS.
  Rollback: revert the runtime candidate commit; no schema/data/deployment changes.
  A2-M1 and A2-M2 are remediated pending independent A2V; A2 remains FAIL.

## A2R4 nested cleanup propagation (2026-09-22)

A bounded child shutdown returning is not proof of release. Lifecycle consumers use
`require_tasks_stopped(ShutdownReport)` to raise existing `ShutdownError` when remaining
work is nonzero. Private supervisors keep their active task records, and dependent
clients/stores are not closed below that work. Errors from child cleanup propagate.

Resource admission/stopping state is distinct from completed closure. A failed cleanup
attempt remains terminal for that resource; repeat runtime shutdown reuses the owned
report rather than retrying already-closed children. Work completing during the original
bounded observation window can still close cleanly exactly once. After that window,
existing worker/guardian containment remains responsible; no new unbounded wait or retry.

Required self-cleaning resources now expose the existing startup cleanup-completion
marker. A failed required start with incomplete cleanup remains a partial runtime owner.
The Discord aggregate retains a member before start, removes it only after proven cleanup,
and stops reverse traversal on failure, retaining that child and its prerequisites.
The independent optional classification/degradation policy is unchanged.

All directly equivalent private supervisor consumers in Watch, Summary, Engagement and
Music check outcomes. Watch-web/database and gateway/deferred cleanup no longer use a
finally block to close a dependency below failed cleanup. Existing Watch lease/session
reconciliation semantics remain unchanged; this is an ownership propagation repair.
No guardian, worker, process-group, systemd or 20/40/70/90 policy change.

Runtime candidate `dab8e5b9a29e8edd83f90e184851c3e97cafe740`: Windows focused 64 PASS,
dependent 95 PASS, A0 isolation 5 PASS, collection 1,078 plus one later case verified separately. Linux exact-candidate nested
incomplete/optional-degraded/rollback cases: 3 PASS, 23 deselected. At pre-fix HEAD the
initial five discriminating cases produced 3 FAIL / 2 PASS. No new full strict run;
previous 1,037 PASS / 2 FAIL / 25 SKIP remains historical evidence (Deno/A2-N1).
A2-M1-R is remediated pending independent A2V2; A2 remains FAIL. Rollback is local revert
of the two A2R4 implementation commits in reverse order, with no data migration or production operation.

## A2R5 Music reply-deletion ownership (2026-09-22)

A2V2 found that the A2R4 consumer inventory missed MusicController's private deletion
supervisor. Its stop now uses the same require_tasks_stopped validator before MusicResource
can release dependencies or mark completion. Zero-grace observation, task handles and the
existing parent failure/guardian escalation path are preserved. No shared helper, startup,
guardian or user-facing feature behavior changed.

Runtime `3a4058caca4e6b9b4b900c458a0e98a825d13d44`: real-controller regression fails before
the fix; focused 81 PASS, A0 5 PASS, collection 1,085, exact Linux 10 PASS/17 deselected.
One strict suite: 1,056 PASS/2 known FAIL/27 SKIP (A2-N1 and Deno). M1-R remediated pending
independent A2V3; A2 remains FAIL. Production unchanged. Rollback: revert that runtime commit.
