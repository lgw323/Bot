# 24. Requirement-to-Test Trace

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

이 표가 PHASE 1 필수 범위의 현재 상태에 대한 우선 근거다. 세부 동작은
`26-characterization-contracts.md`, race/fault 후속 test는
`27-concurrency-failure-plan.md`를 따른다.

| Feature | FR | New executable evidence | PHASE 1 status |
| --- | --- | --- | --- |
| F001 | FR-001,046 | `test_database_recovery_contracts.py`: corrupt 보존/fail, zero-byte fail-closed spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F008 | FR-003,004,010,027,030 | `test_discord_contracts.py`, `test_summary_contracts.py`: signature/publicness/error/success/no-data; ACL/60s/active1/queue4/redaction specs | CHARACTERIZED + CORRECT-SPEC xfail |
| F009/F010 | FR-028,029 | `test_component_contracts.py`: modal/refresh/topic select; >25 pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F011/F013 | FR-011,012,021 | exact music player/search select/modal inventory; pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F012 | FR-003,010,012 | `/재생` required string, private defer, unavailable text | CHARACTERIZED |
| F018 | FR-015 | deterministic 3s/8s/third-skip state test | CHARACTERIZED |
| F022/F023 | FR-016–018,021 | queue controls, selection and NONE/SONG/QUEUE transition; stable pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F024 | FR-018,019 | injected provider success and local provider-failure test | CORRECT-SPEC executable success |
| F025 | FR-020,021 | user-global favorite controls; pagination spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F028/F045 | FR-024,025 | exact snapshot shape/restore order/settings; legacy 0.5 default spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F029/F030 | FR-031,032 | text XP table, voice leave/move fake-clock | CHARACTERIZED |
| F031/F032 | FR-003,032,033 | private profile, option-based ranking, completed-minute profile; ranking parity spec | CHARACTERIZED + CORRECT-SPEC xfail |
| F033–F036 | FR-003,005,010,034–037 | master/register/delete/list, KST/leap fake-clock; valid date/non-leap policy specs | CHARACTERIZED + CORRECT-SPEC xfail |
| F037 | FR-003,004,010,038 | `/시청` public/unavailable; durable-before-invite/single-responder specs | CHARACTERIZED + CORRECT-SPEC xfail |
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

SQLite repository 구현과 data compatibility는 PHASE 3, engagement/Summary/Watch/Music 기능은
각 PHASE 4/5/6/7에 남아 있다. 현재 `ports/adapters` package와 SQLite adapter-only rule만
repository boundary를 준비한다.

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
| F011 music dashboard/channel cleanup | FR-011 | PRESERVE | `test_music_ui.py::test_music_player_view_initialization` | PARTIAL | single dashboard across reconnect, message delete exceptions/timing, exact controls |
| F012 URL play request | FR-003, FR-012, FR-013, FR-014 | PRESERVE | slash routing, URL regex, prepared backend playback | PARTIAL | command/message paths, voice/channel policy, response text/publicness, ordering |
| F013 search/select | FR-012, FR-021 | PRESERVE/CORRECT | `test_music_ui.py::test_search_select_initialization` | PARTIAL | modal/select custom IDs, result expiry, stable selection, pagination |
| F014 playlist expansion | FR-012 | PRESERVE | yt-dlp option contains `playlistend=50`, no contract test | GAP | 0/1/50/>50/malformed entries and request-order preservation |
| F015 music-channel URL/delete | FR-011, FR-012 | PRESERVE | none | GAP | designated channel only, message deletion/failure, public cleanup timing |
| F016 voice connection/move/master policy | FR-005, FR-006, FR-013 | PRESERVE/CORRECT | restore connect timeout only | GAP | requester/master matrix, connect/move/reconnect, cross-guild denial |
| F017 audio acquire/play/cache | FR-014 | PRESERVE/CORRECT | `test_music_playback.py::*` and prepared-media playback test | PARTIAL | partial/oversize/disk-full/timeout/kill-reap/global-cap and cache corruption |
| F018 playback retry/skip | FR-015 | PRESERVE | 3s/8s/third-failure and cancel tests in `test_music_core.py` | COVERED | add Feature/FR/mode metadata and deterministic callback-race coverage |
| F019 pause/resume | FR-016 | PRESERVE | none | GAP | button response, elapsed/paused duration, invalid/stale state |
| F020 skip/cancel | FR-016 | PRESERVE/CORRECT | pending-retry and active-preparation skip tests | PARTIAL | normal FFmpeg skip, simultaneous skip/after, response contract |
| F021 leave/reconnect/empty leave | FR-013 | PRESERVE/CORRECT | none at policy level | GAP | button leave, 8s reconnect, empty-channel check, move semantics, cleanup |
| F022 queue view/edit | FR-016, FR-017, FR-021 | PRESERVE/CORRECT | view construction only | GAP | stable item IDs, move/remove/shuffle/clear, confirm/cancel, stale UI, pagination |
| F023 loop modes | FR-018 | PRESERVE | enum values only | GAP | off→one→all button cycle and queue/song end-state transitions |
| F024 autoplay | FR-018, FR-019 | CORRECT | cancellation tests only; V1 success path references an unimported symbol | CORRECT-GAP | successful recommendation, dedupe, provider failure, cancel/retry race; do not golden `NameError` |
| F025 global favorites | FR-020, FR-021 | PRESERVE/CORRECT | DB cross-guild sharing and limited agent cancellation tests | PARTIAL | all UI actions, >25 pagination, stable IDs, concurrent add/delete |
| F026 popular songs/play count | FR-022 | CORRECT | DB counter/top query tests | PARTIAL | playback-session start exactly once; no retry/TTS/resume duplicate; guild isolation |
| F027 join TTS | FR-023 | PRESERVE/CORRECT | path/cache helper initialization only | GAP | enabled/disabled, timeout/failure recovery, simultaneous join and track-complete races |
| F028 music snapshot/restore | FR-024 | PRESERVE/CORRECT | atomic-write preservation, JSON contract, invalid JSON, full restore tests | PARTIAL | version/revision/checksum, restore-ack-before-consume, partial guild failure, process-crash/coarse checkpoint |
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
| F045 persisted volume | FR-025 | PRESERVE/CORRECT | DB volume CRUD, snapshot/restore values, MusicState explicit initialization | PARTIAL | one 0.5 default path, persisted value precedence, legacy snapshot missing-field behavior |

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
모든 fault/race 구현 증명은 overlay와 `27-concurrency-failure-plan.md`의 담당 Phase에서 계속
추적하며, `CORRECT-SPEC`을 구현 완료로 오해하지 않는다.
