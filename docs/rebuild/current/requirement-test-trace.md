# Requirement-to-Test Trace

## Purpose and status vocabulary

기존 F001–F045 표는 2026-09-04 PHASE 0에서 V1 코드와 당시 130개 pytest를 직접
대조한 baseline이다.
`COVERED`는 현재 자동 test가 핵심 사용자 계약을 검증한다는 뜻이고, `PARTIAL`은 helper나
일부 경로만 검증한다는 뜻이다. `GAP`은 사용자 계약 수준의 test가 없으며,
`CORRECT-GAP`은 현재 V1 bug를 golden behavior로 만들지 않고 수정 요구만 고정해야 한다.

PHASE 1에서는 `tests/characterization/`을 추가했다. `CHARACTERIZED`는 V1 실행을 통해
보존 계약이 통과한다는 뜻이고, `CORRECT-SPEC`은 승인된 정상 동작을 test로 표현했다는
뜻이다. 그 test가 V1 결함 때문에 실패하는 경우 strict `xfail`로 표시하며, 향후 구현으로
XPASS가 되면 suite가 실패하므로 marker와 trace를 함께 갱신해야 한다.

각 PHASE 1 characterization test에는 `Feature ID`, `FR ID`, `PRESERVE/CORRECT/DECIDE`를
test name 또는 marker/fixture metadata로 연결한다. 아래 파일명은 `tests/` 기준이다.

## PHASE 1 mandatory-contract overlay

이 표는 PHASE 1 당시 필수 범위의 기록이다. 현재 구현/xfail 상태는 아래 PHASE별 최신 overlay가 우선한다. 세부 동작은
`../phases/phase-01/characterization-contracts.md`, race/fault 후속 test는
`../phases/phase-01/concurrency-failure-plan.md`를 따른다.

| Feature | FR | New executable evidence | PHASE 1 status |
| --- | --- | --- | --- |
| F001 | FR-001,046 | `test_database_recovery_contracts.py`: V1 corrupt 보존/fail, PHASE 3 V2 zero-byte fail-closed 구현 | CHARACTERIZED + CORRECT-IMPLEMENTED (V2) |
| F008 | FR-003,004,010,027,030 | `test_discord_contracts.py`, `test_summary_contracts.py`: signature/publicness/error/success/no-data; V2 ACL/60s/active1/queue4/redaction | CHARACTERIZED + CORRECT-IMPLEMENTED (V2) |
| F009/F010 | FR-028,029 | `test_component_contracts.py`: modal/refresh/topic select; V2 Summary >25 pagination | CHARACTERIZED + CORRECT-IMPLEMENTED (V2) |
| F011/F013 | FR-011,012,021 | exact music player/search select/modal inventory; pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F012 | FR-003,010,012 | `/재생` required string, private defer, unavailable text | CHARACTERIZED |
| F018 | FR-015 | deterministic 3s/8s/third-skip state test | CHARACTERIZED |
| F022/F023 | FR-016–018,021 | queue controls, selection and NONE/SONG/QUEUE transition; stable pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F024 | FR-018,019 | injected provider success and local provider-failure test | CORRECT-SPEC executable success |
| F025 | FR-020,021 | user-global favorite controls; pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F028/F045 | FR-024,025 | exact snapshot shape/restore order/settings; legacy 0.5 default spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F029/F030 | FR-031,032 | text XP table, voice leave/move fake-clock | CHARACTERIZED |
| F031/F032 | FR-003,032,033 | private profile, option-based ranking, completed-minute profile; V2 ranking parity | CHARACTERIZED + CORRECT-IMPLEMENTED (V2) |
| F033–F036 | FR-003,005,010,034–037 | master/register/delete/list, KST/leap fake-clock; V2 valid date/non-leap policy | CHARACTERIZED + CORRECT-IMPLEMENTED (V2) |
| F037 | FR-003,004,010,038 | `/시청` public/unavailable; durable-before-invite/single-responder V2 signed HTTP path | CHARACTERIZED + CORRECT IMPLEMENTED (PHASE 6) |
| F038/F040 | FR-039 | exact HTTP paths/add body plus existing endpoint/CRUD tests | CHARACTERIZED |
| F039 | FR-040,041 | invalid close, join ordering, all 7 client relay types | CHARACTERIZED |
| F041 | FR-042 | exact 30s creation + 5s empty fake-clock and disconnect scheduling | CHARACTERIZED |
| F042 | FR-005,043 | admin button inventory plus existing close/auth/cleanup tests | CHARACTERIZED |
| F044 | FR-007,010 | mention-only default help/public destination settings | CHARACTERIZED |

8개 slash command 전체의 parameter는 하나의 exact matrix test가 검증한다. 공개성은 command
또는 실제 handler를 호출해 검증하며, `/내정보`는 과거 inventory의 “공개” 주장이 아니라
실제 V1의 ephemeral defer를 기준으로 정정했다.

## PHASE 2 platform overlay

이 표는 feature migration 완료가 아니라 후속 구현이 따라야 할 platform contract의 executable
evidence다. 따라서 F001/F002/Watch 등의 사용자 기능 status나 PHASE 1 strict xfail을 완료로
바꾸지 않는다.

| Contract | Requirement | Executable evidence | PHASE 2 result |
| --- | --- | --- | --- |
| typed immutable/fail-fast config | FR-001; NFR-028,033 | `tests/unit/platform/test_config.py` | explicit mapping parse, production release gate, Pi limit validation |
| typed cross-context errors/correlation | NFR-020,023 | `test_errors_context.py`, `test_telemetry.py` | safe/internal 분리, nested context, pre-sink redaction |
| bounded tasks and blocking work | FR-009; NFR-003,005,013 | `test_tasks.py`, `test_executors.py` | metadata/deadline/restart/cancel/exception observation, admission cap |
| liveness/readiness/capability | FR-002; NFR-004,022 | `test_health.py`, `test_runtime.py` | live/ready/dependency 분리, required capability와 startup rollback |
| Discord/Watch process composition | NFR-002 | `test_runtime.py`, `tests/architecture/test_import_rules.py` | 독립 supervisor/capacity/composition, feature 미연결 |
| inward dependency/import safety | NFR-019,025,027,028 | `tests/architecture/test_import_rules.py` | layer/vendor/SQLite/task/executor rule와 fresh-process no-side-effect import |

PHASE 2 시점에는 빈 `ports/adapters` package와 SQLite adapter-only rule만 있었다. PHASE 3의
현재 구현 증거는 다음 overlay에 있으며 engagement/Summary/Watch/Music 기능은 각 PHASE
4/5/6/7에 남아 있다.

## PHASE 3 data overlay

모든 자동 test는 `tests/integration/data/`의 synthetic/임시 DB만 사용한다. 별도 actual DB
working-copy rehearsal은 [보고서](../phases/phase-03/migration-rehearsal.md)에 기록한다.

| Contract | Requirement / scenario | Executable evidence | Result / remaining owner |
| --- | --- | --- | --- |
| SQLite repository boundary | FR-006/020; NFR-019/025/027 | `test_repositories.py`, architecture import rules | IMPLEMENTED; immutable DTO, guild scope와 user-global favorite |
| bounded DB ownership/deadline/cancel | NFR-003/005/011/013; CF-07/20 | `test_concurrency.py`, `test_lifecycle.py` | IMPLEMENTED; read/write 독립 cap, cooperative rollback, bounded observation |
| legacy schema/semantic compatibility | FR-006/031/032/045; CF-21 | `test_schema_contract.py`, `test_failure_validation.py`, `test_repositories.py` | IMPLEMENTED; global rows/소수 초/잘못된 legacy 생일/URL/history 보존 |
| expand-only ledger/idempotent resume | ADR-010; FR-050 | `test_migration_ledger.py`, `test_migrations.py` | IMPLEMENTED; version/identity/checksum/time, step rollback/restart, old reader |
| explicit bootstrap/fail-closed startup | FR-001/046; F001 | `test_recovery.py`, `test_lifecycle.py`, zero-byte characterization | CORRECT-IMPLEMENTED for V2; V1 runtime 미변경 |
| encrypted V2 + legacy backup | FR-045/046; F005 | `test_recovery.py`, `test_failure_validation.py` | IMPLEMENTED data primitives; remote transport/key rotation/retention PHASE 8 |
| point-in-time validated backup | FR-047; CF-14 | `test_concurrency.py::test_snapshot_during_atomic_cross_table_write_is_one_point_in_time` | IMPLEMENTED data side; scheduling/RPO/RTO/real Pi fault PHASE 8/9 |
| actual copy reconciliation/rollback reader | ADR-010/014; user PHASE 3 | `scripts/rehearse_v2_data.py` | PASS; 원본 unchanged, six-table counts/semantic equality |

Strict xfail은 13 → 12다. PHASE 3 소유 zero-byte spec만 V1 호출에서 구현된 V2 startup gate로
전환했다. 단순 marker 제거가 아니며 bytes 보존과 closed executor도 확인한다. 기존 V1 corrupt
test는 계속 통과한다. PHASE 1의 PRESERVE test는 변경하지 않았다.

PHASE 1의 `legacy snapshot 0.5/default/version/ACK` 공동 owner 표기(3/7)는 이번 사용자 지시의
정확한 SQLite 범위에 따라 PHASE 7로 남긴다. 해당 marker와 나머지 PHASE 4–7 strict xfail은
유지한다. 이 overlay는 F001/F005 전체 운영 기능 또는 engagement/Watch/Music migration 완료를
뜻하지 않는다.

## PHASE 4 engagement overlay

아래 증거는 `tests/integration/engagement/`와 변경된 PHASE 4 CORRECT characterization에 있다.
이전 Phase의 역사적 상태를 소급 수정하지 않는다.

| Contract | Requirement / scenario | Executable evidence | Result |
| --- | --- | --- | --- |
| text formula/event dedupe | FR-031; CF-21 | `test_policy.py`, `test_events.py`, `test_failures.py` | IMPLEMENTED; all Hangul/Jamo, bot/DM, receipt+XP atomicity, replay/cancel |
| voice session/rounding | FR-032; CF-17/20/21 | `test_events.py`, `test_failures.py`, `test_discord.py` | IMPLEMENTED; move/mute/deaf/leave/restart, guild/user ownership, observed-only failure recovery |
| profile/ranking contract | FR-003/033; CF-19 | `test_discord.py`, `test_events.py`, ranking characterization | IMPLEMENTED; private/master-other, top ten, same completed-minute formula |
| master/calendar CRUD | FR-034–036 | `test_birthday.py`, `test_policy.py`, `test_discord.py`, calendar characterization | IMPLEMENTED; exact master, valid date, deletion rowcount, scope/list bounds |
| daily birthday | FR-037; CF-18 | `test_birthday.py`, `test_failures.py`, Feb-29 characterization | IMPLEMENTED; KST, durable daily claim, supervised lifecycle, uncertain-send no duplicate |
| additive metadata/rollback | ADR-010/018/019 | `test_compatibility.py`, PHASE 3 data suite | IMPLEMENTED; copy-only expansion, old reader, metadata-encrypted-backup parity |
| explicit Discord wiring | NFR-019/025/027; CF-19/20 | `test_discord.py`, architecture rules | IMPLEMENTED; five command signatures, lazy SDK, startup fail-closed, no login |

PHASE 4에서 strict xfail은 12 → **9**다. ranking completed-minute, invalid calendar와 non-leap
Feb-29 세 spec을 V2 repository/application/adapter 호출로 전환했다. V1 PRESERVE tests는 변경하지
않았다. birthday fallback은 Feb 29만 대체 조회하는 것이 아니라 Feb 28과 함께 같은 daily claim으로
보내는 것을 검증한다. PHASE 5 Summary, PHASE 6 Watch와 PHASE 7 Music 소유 marker는 유지한다.

## PHASE 5 Summary overlay

최신 Summary 증거는 `tests/integration/summary/`, V2로 전환한 Summary characterization과
[PHASE 5 report](../phases/phase-05/phase-5-report.md)에 있다. 아래의 PHASE 0 표는 역사적 비교다.

| Contract | Requirement / scenario | Executable evidence | Result |
| --- | --- | --- | --- |
| capture/preload/reconnect | FR-026; CF-16 | `test_capture.py`, `test_lifecycle.py` | IMPLEMENTED; message-ID cursor, live merge, dedupe, retry, ready/resumed coalescing |
| retention and isolation | FR-026; Q-H11 | `test_capture.py`, `test_requests.py` | IMPLEMENTED; age/count/config bounds, disabled idle, per-source readiness |
| basic/advanced Summary | FR-027/028; CF-19 | `test_discord.py`, `test_requests.py` | IMPLEMENTED; signature/public/private, filter/range, modal and prompt separation |
| refresh/topic/pagination | FR-029; Q-M04 | `test_discord.py`, `test_lifecycle.py`, Summary component characterization | IMPLEMENTED; 26th topic accessible, stable IDs, stale/context validation, bounded views/modal |
| ACL/privacy/Gemini | FR-030; CF-09 | `test_requests.py`, `test_gemini.py`, `test_discord.py` | IMPLEMENTED; pre-extraction ACL, no raw sink data, safe typed provider/parse failures |
| concurrency/deadline/cancel | FR-030; CF-08/09/19/20 | `test_requests.py`, `test_discord.py` | IMPLEMENTED; active 1/queue 4/sixth overload, FIFO recovery, queue-inclusive 60s, handoff cancel |
| explicit lifecycle/architecture | NFR-019/025/027; CF-16/20 | `test_lifecycle.py`, architecture import rules | IMPLEMENTED; supervised bounded work, lazy vendors, clean stop, no production wiring |

PHASE 5에서 strict xfail은 9 → **4**다. Summary 소유 ACL/60s/concurrency/queue/redaction
5개를 실제 V2 경로로 전환했고 PRESERVE 본문은 유지했다. 공동 component xfail의 Music 본문과
marker는 그대로 두고 Summary pagination을 별도 V2 callback spec으로 구현했다.
PHASE 5 종료 당시 남은 owner는 PHASE 6 Watch 2개, PHASE 7 Music 2개였다. 실제 Discord/Gemini/Pi 검증은 staging gate다.

## PHASE 6 Watch overlay

현재 Watch 구현 증거는 `tests/integration/watch/`와
[PHASE 6 report](../phases/phase-06/phase-6-report.md)에 있다. 아래 PHASE 0 표는 역사적 비교다.

| Feature / contract | V2 executable evidence | Current status |
| --- | --- | --- |
| F037 / FR-003,004,010,038 | `test_discord.py`, `characterization/test_watch_contracts.py`: durable intent, public invite, one responder, failure/cancel/duplicate compensation | IMPLEMENTED; Watch CORRECT 2 pass |
| F038 / FR-039,041 | `test_transports.py`: preserved routes, HTML 404, CSP/Origin/CSRF/body/schema/terminal | IMPLEMENTED; real browser staging remains |
| F039 / FR-040,041 / CF-10 | `test_runtime.py`, `test_transports.py`: all seven types, ASGI handshake, revisions, malformed/rate/slow peer | IMPLEMENTED |
| F040 / FR-039,040 / CF-12 | `test_data.py`, `test_runtime.py`, `test_metadata_security.py`, `test_lifecycle.py`: ordering/duplicates, add/remove/close, bounded oEmbed | IMPLEMENTED |
| F041 / FR-042 / CF-11 | `test_lifecycle.py`, `test_runtime.py`: 30+5 grace, reconnect boundary, absolute expiry, cancellation | IMPLEMENTED |
| F042 / FR-005,043 | `test_discord.py`: master-only/duplicate close, signed abort, invite/admin cleanup receipt | IMPLEMENTED |
| F043 / FR-044 / CF-13,16 | `test_lifecycle.py`, `test_processes.py`: lease ownership, stale cleanup barrier, old-owner rejection, idempotent maintenance | IMPLEMENTED |
| Process/security/shutdown / CF-19,20 | `test_processes.py`, `test_metadata_security.py`, `test_discord.py`: transitive import isolation, separate health, replay, capacity, bounded stop | IMPLEMENTED; actual OS process/proxy/Pi staging remains |

Strict xfail은 4 → **2**다. 남은 두 개는 PHASE 7 Music 소유다. Watch PRESERVE 함수 7개의
AST(파라미터화 포함)는 PHASE 5 기준선과 동일하다. migration 4는 additive metadata이며 기존
1–3 checksum과 V1 reader를 보존한다. 원본 DB, 운영 entrypoint, Gateway/API/Pi에는 연결하지 않았다.

## PHASE 7 Music implementation overlay (2026-09-11)

PHASE 6 baseline `504 passed, 2 xfailed`를 확인했다. 남은 Music CORRECT 두 개는 실제 V2
actor restore와 paginated UI 경로로 전환되어 xfail이 0이다. PRESERVE 32개 함수 AST와
migration 1–4 정의는 동일하다. 최신 전체/반복 검증은
[PHASE 7 report](../phases/phase-07/phase-7-report.md)를 참조한다.

| 요구사항/feature | 실행 근거 (`tests/integration/music/`) | 상태 |
| --- | --- | --- |
| F011–F016 / FR-003,011–013,021 | `test_discord.py`, `test_lifecycle.py`, playlist `test_resources.py` | IMPLEMENTED; commands, channel, voice, pagination, FIFO/50 cap |
| F017–F023 / FR-014–018 | `test_actor.py`, `test_resources.py`, `test_lifecycle.py`, `test_failures.py` | IMPLEMENTED; bounded ownership, PCM, retries, pause, skip, queue, loop |
| F024 / FR-019 | `test_actor.py`, `test_failures.py` | IMPLEMENTED; successful recommendations and stale/failure isolation |
| F025/F026 / FR-020–022 | `test_discord.py`, `test_data.py` | IMPLEMENTED; user-global favorites, guild/session receipt/count and encrypted recovery |
| F027/F028/F045 / FR-023–025 | `test_actor.py`, `test_failures.py`, `test_resources.py`, `test_lifecycle.py` | IMPLEMENTED; TTS, atomic ACK/legacy restore and persisted/default volume |
| CF-01–06,15,16,19–21 | report concurrency matrix and repeat results | EXECUTABLE; fake clock/barrier/local child, no production services |

상한은 Pi 실측 SLO가 아니다. 실제 Discord/Voice/provider와 Pi 검증, Operations, deployment,
production DB/cutover는 후속 gate에 남긴다. V1 route와 frozen baseline은 유지한다.

## F001–F045 trace

| Feature | FR | Mode | Current automated evidence | Status | PHASE 1 characterization / planned proof |
| --- | --- | --- | --- | --- | --- |
| F001 startup/DB recovery/shutdown | FR-001, FR-002, FR-009, FR-046 | CORRECT | `test_main_bot.py::test_setup_hook_*`; `test_database_manager.py::test_init_db_*` | PARTIAL | startup capability/readiness matrix; existing 0-byte/corrupt/wrong-schema DB; bounded shutdown |
| F002 logs/admin panel | FR-002, FR-048, FR-050 | PRESERVE/CORRECT | `test_log_agent.py::test_discord_log_*`, `test_setup_logging_*`, reconnect handler test | PARTIAL | exact panel/buttons/publicness, bounded storm/drop, audit/correlation |
| F003 manual update/restart | FR-009, FR-048, FR-049 | PRESERVE/CORRECT | updater shell assertions and snapshot unload tests are separate | PARTIAL | master denial/approval, checkpoint-before-update, one invocation, failure UX |
| F004 automatic update | FR-049 | CORRECT | `test_auto_update_script.py::*` checks current script text | PARTIAL | executable temp-release test for lock, timeout, readiness, code+venv rollback |
| F005 encrypted backup/recovery | FR-045, FR-046, FR-047, FR-050 | PRESERVE/CORRECT | 17 DB tests include V2 round-trip, wrong key, legacy restore, atomic preservation; backup script assertions | PARTIAL | point-in-time concurrent-write snapshot, semantic validation, corrupt local→good remote, restore rehearsal |
| F006 Summary capture/preload | FR-026 | CORRECT | `test_summary_listeners.py::test_on_message_adds_to_log` | PARTIAL | preload/live message-ID cursor with no gap/duplicate and reconnect isolation |
| F007 Summary retention/prune | FR-026 | PRESERVE/CORRECT | prune and Cog lifecycle tests | PARTIAL | fake-clock count/time bounds, queue cap, disabled idle behavior |
| F008 basic `/요약` | FR-003, FR-010, FR-027, FR-030 | PRESERVE/CORRECT | slash routing/defer, no-data result, Gemini happy path | PARTIAL | command signature/public result/golden embed, ACL, timeout/error mapping |
| F009 advanced Summary | FR-003, FR-010, FR-028, FR-030 | PRESERVE/CORRECT | none at user-contract level | GAP | modal fields, filtering/range validation, public result, prompt separation |
| F010 Summary refresh/topic | FR-010, FR-029 | PRESERVE/CORRECT | none at callback-contract level | GAP | refresh semantics, ephemeral detail, stale/invalid selection, >25 pagination |
| F011 music dashboard/channel cleanup | FR-011 | PRESERVE | `integration/music/test_discord.py / test_lifecycle.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F012 URL play request | FR-003, FR-012, FR-013, FR-014 | PRESERVE | `integration/music/test_discord.py / test_actor.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F013 search/select | FR-012, FR-021 | PRESERVE/CORRECT | `integration/music/test_discord.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F014 playlist expansion | FR-012 | PRESERVE | `integration/music/test_resources.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F015 music-channel URL/delete | FR-011, FR-012 | PRESERVE | `integration/music/test_discord.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F016 voice connection/move/master policy | FR-005, FR-006, FR-013 | PRESERVE/CORRECT | `integration/music/test_discord.py / test_actor.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F017 audio acquire/play/cache | FR-014 | PRESERVE/CORRECT | `integration/music/test_resources.py / test_lifecycle.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F018 playback retry/skip | FR-015 | PRESERVE | `integration/music/test_actor.py / test_failures.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F019 pause/resume | FR-016 | PRESERVE | `integration/music/test_actor.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F020 skip/cancel | FR-016 | PRESERVE/CORRECT | `integration/music/test_actor.py / test_failures.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F021 leave/reconnect/empty leave | FR-013 | PRESERVE/CORRECT | `integration/music/test_actor.py / test_lifecycle.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F022 queue view/edit | FR-016, FR-017, FR-021 | PRESERVE/CORRECT | `integration/music/test_actor.py / test_discord.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F023 loop modes | FR-018 | PRESERVE | `integration/music/test_actor.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F024 autoplay | FR-018, FR-019 | CORRECT | `integration/music/test_actor.py / test_failures.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F025 global favorites | FR-020, FR-021 | PRESERVE/CORRECT | `integration/music/test_discord.py / test_data.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F026 popular songs/play count | FR-022 | CORRECT | `integration/music/test_data.py / test_lifecycle.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F027 join TTS | FR-023 | PRESERVE/CORRECT | `integration/music/test_actor.py / test_failures.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F028 music snapshot/restore | FR-024 | PRESERVE/CORRECT | `integration/music/test_resources.py / test_lifecycle.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |
| F029 text XP | FR-031 | PRESERVE | jamo formula and one `on_message` path; repository CRUD | PARTIAL | complete character table, bot/DM/guild cases, duplicate event and multi-guild isolation |
| F030 voice XP | FR-032 | PRESERVE/CORRECT | repository seconds math only | GAP | join/mute/move/leave/restart fake clock, completed-minute formula, guild/user key |
| F031 `/내정보` | FR-003, FR-010, FR-033 | PRESERVE | no command contract test | GAP | signature, self/master-other behavior, embed/publicness and formula parity |
| F032 `/랭킹` | FR-003, FR-010, FR-032, FR-033 | PRESERVE/CORRECT | repository ranking query only | PARTIAL | command option/publicness/golden embed, completed-minute parity, guild isolation |
| F033 birthday register | FR-003, FR-005, FR-010, FR-034, FR-035 | PRESERVE/CORRECT | none | GAP | master auth, response contract, full calendar matrix including leap years |
| F034 birthday delete | FR-003, FR-005, FR-010, FR-034 | PRESERVE | none | GAP | master auth, existing/missing target, guild isolation and response contract |
| F035 birthday list | FR-003, FR-010, FR-036 | PRESERVE | none | GAP | empty/non-empty, ephemeral option, ordering, cross-guild isolation |
| F036 daily birthday alert | FR-006, FR-037 | PRESERVE/CORRECT | none | GAP | KST 09:00 fake clock, once-per-date, per-guild channel, Feb-29→Feb-28 |
| F037 Watch create/invite/admin notice | FR-003, FR-005, FR-038 | PRESERVE/CORRECT | `test_watch_creation_sends_private_admin_control` | PARTIAL | durable-intent-before-invite, click/send/DB failure compensation, publicness/golden embed |
| F038 Watch browser page | FR-039, FR-041 | PRESERVE | `/watch` 404/200 endpoint test and DOM safety assertion | PARTIAL | capability expiry/revocation, exact HTML compatibility and terminal close behavior |
| F039 Watch presence/chat/playback WS | FR-040, FR-041 | PRESERVE/CORRECT | no actual WebSocket handshake/message test | GAP | all 7 client types, emitted compatibility messages, ordering/revision, malformed/rate/slow peer |
| F040 Watch playlist/oEmbed | FR-039, FR-040 | PRESERVE/CORRECT | DB CRUD, GET/add API, invalid YouTube URL | PARTIAL | remove HTTP contract, add/close race, body limits, oEmbed timeout/failure/cache, auth/CSRF |
| F041 Watch grace/expiry | FR-042 | PRESERVE | inactive/active self-destruct with creation grace bypassed | PARTIAL | exact 30s creation and 5s empty fake-clock races, reconnect cancellation |
| F042 Watch master close | FR-005, FR-043 | PRESERVE/CORRECT | websocket/state/DB cleanup and non-master/master button tests | PARTIAL | duplicate/racing close idempotency, invite-delete failure compensation, loopback auth |
| F043 stale Watch cleanup | FR-044 | CORRECT | startup cleanup once and active-session preservation test | PARTIAL | readiness admission barrier and old-browser reconnect race |
| F044 mention-prefix help | FR-007 | PRESERVE | none | GAP | mention-only prefix, help response and message-content intent contract |
| F045 persisted volume | FR-025 | PRESERVE/CORRECT | `integration/music/test_actor.py / test_failures.py` | IMPLEMENTED | PHASE 7 overlay; real Discord/provider/Pi verification remains staged |

## PHASE 0 coverage summary (historical)

| Status | Feature count | Meaning |
| --- | ---: | --- |
| COVERED | 1 | 핵심 V1 계약이 현재 test로 고정됨; metadata/race 보강은 남음 |
| PARTIAL | 25 | helper/일부 path만 검증되어 golden 또는 failure proof 필요 |
| GAP | 18 | 사용자 계약 수준 test가 없음 |
| CORRECT-GAP | 1 | V1 bug를 복제하지 않는 수정 요구 test가 필요 |

이 숫자는 PHASE 0 당시 line coverage가 아니라 feature-contract trace다. PHASE 1 overlay는
필수 `PARTIAL/GAP`을 실행 가능한 characterization 또는 strict corrective spec에 연결했다.
autoplay success, corrupt/0-byte DB와 핵심 concurrency/failure 계획도 포함한다. 전체 F001–F045의
모든 fault/race 구현 증명은 overlay와
`../phases/phase-01/concurrency-failure-plan.md`의 담당 Phase에서 계속
추적하며, `CORRECT-SPEC`을 구현 완료로 오해하지 않는다.

## PHASE 8 operations implementation overlay

Earlier rows are historical coverage snapshots. This overlay implements the operations scope;
it does not claim live host/Discord administration-panel migration or production deployment.

| Scope | Executable evidence under tests/integration/operations/ | Status and staging limit |
| --- | --- | --- |
| F001 startup; F003–F005 master/control boundary | test_runtime.py, test_assets.py; existing characterization | Config/login gate, signals, checkpoint, one ephemeral response; live admin panel unwired |
| F002 logs/observability | test_runtime.py; existing platform telemetry tests | JSON journald/local health/metrics; live Discord log UI migration not claimed |
| FR-045–FR-050 operations/recovery scope | test_deployment.py, test_pipeline.py, test_recovery.py, test_assets.py | Update, backup, restore and timers; actual host actions gated |
| Atomic activation, rollback, two-process identity | test_deployment.py, test_filesystem.py, test_pipeline.py, test_runtime.py | Failure/cancel/recovery; Linux symlink/fsync pending |
| Lock/timer overlap, audit, cleanup | test_filesystem.py, test_runtime.py, test_retention.py, test_deployment.py | Kernel lock/repeated races, stale metadata, protected cleanup, audit failure |
| Dependency identity | test_build.py, test_assets.py | Pins, fake sealed wheels, full identity collision rejection; ARM64 artifacts not downloaded |
| Backup/data integrity | test_recovery.py; existing storage integration tests | Synthetic snapshot/key/corruption/schema/semantic/fallback/promotion; real DB excluded |
| Architecture | tests/architecture/ | Inward imports, task/executor/import safety; feature/domain/schema unchanged |

Exact results, corrected failures and host limits are in the
[PHASE 8 report](../phases/phase-08/phase-8-report.md). Contracts:
[deployment](../phases/phase-08/deployment-contract.md),
[backup/restore](../phases/phase-08/backup-restore-contract.md),
[operations](../phases/phase-08/operations-contract.md).

## PHASE 9 actual ARM64 staging overlay

Historical rows above remain unchanged. Actual host evidence and its limits are recorded in the
[PHASE 9 report](../phases/phase-09/phase-9-report.md).

| Scope | Actual evidence | Limit |
| --- | --- | --- |
| ARM64 dependency/release | 59 exact wheels, offline hashes/pip check, real immutable builds | Exercised ABI, no live Voice/provider proof |
| Linux permissions | symlink/fsync/setgid/WAL/flock probe; runtime manifest and systemd ACL fixes | No power-loss simulation |
| Pair lifecycle/deploy | real Watch + explicit synthetic peer; normal deploy, smoke-fault rollback, stop/start, reboot | Actual Discord assembly/Gateway remains blocked |
| Backup/restore | installed oneshot, encrypted online snapshot, retention, isolated newest/fallback/rejection, stopped synthetic promotion | Small synthetic DB, local-only recovery |
| Capacity/concurrency | 69 actual Pi tests: Summary, Watch caps, DB atomic snapshot under writes, Music multi-guild lifecycle | Fake providers, no live workload throughput |
| Regression | Windows strict 688 passed; mode, ACL and isolated-entrypoint regressions | Pending observations remain explicit in report |

## PHASE 10A readiness overlay

| Scope | Evidence | Limit |
| --- | --- | --- |
| Copy-only production migration | `test_production_candidate.py`; actual count/checksum/old-reader rehearsal | No canonical promotion; tests use synthetic tmp DB only |
| Recovery | Actual PC schema 0/5 encrypted restore; Pi schema 5 decrypt/rebackup/restore/runtime UID open-close; actual Bot-Data upload/download/isolated decrypt | Isolated paths only; production timer cadence and sustained remote RPO remain unverified |
| Production startup gate | `test_production_configuration.py` | Placeholder/basic format only; no live token/resource authentication |
| Direct operator config/secrets | `test_production_setup.py`, `test_production_tools.py`; operator input and Pi three-scope no-network mount/owner/mode probe PASS | Basic format/scope only; no API login or guild/channel permission validation |
| ARM64 candidate | `test_candidate_verification.py`; approved63 offline build/tests/manifest/credential scopes PASS; actual synthetic pair activation PASS | Production login/activation not authorized |
| Off-host opt-in | `test_git_backup.py`, `test_offhost_wiring.py`; exact Bot-Data/db-backup, no force push, verified read-back, failure preserves previous latest | `d54ff36` ARM64 runtime backup/upload/download/decrypt/semantic PASS; production still inactive; Git history is retained, not physically pruned |
| Longer observation | `test_staging_observation.py`; actual 24h/1,438 samples, restarts/RPO exceeded 0 | DB failures +12/+17, health missing 1, disk free -955,363,328 bytes with high periodic-task journal volume; all 1,438 throttling samples zero; synthetic workload only |
| Production transition | `test_stopped_activation.py`; stopped/identity/lock guards; exact [final command sheet](../phases/phase-10/final-command-sheet.md); `test_install_sheet_preparation.py`; actual isolated config prepared | 10A COMPLETE; 10B approval and live smoke required; canonical still synthetic |
| Operational telemetry follow-up | `test_operational_telemetry.py`, `test_final_readiness_tools.py`; Pi63 actual300.171s/31 samples, routine lifecycle0, failure/cancel/deadline/retry/code injection preserved | Short synthetic observation only; historical DB failure cause unresolved |
| Watch current route | `test_cloudflare_route_review.py`; current connector config event shows localhost:8000, no internal-port ingress | Read-only; origin9000 change requires10B approval |
