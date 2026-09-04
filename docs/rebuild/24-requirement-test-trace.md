# 24. Requirement-to-Test Trace

## Purpose and status vocabulary

이 표는 2026-09-04 PHASE 0에서 V1 코드와 현재 130개 pytest를 직접 대조한 결과다.
`COVERED`는 현재 자동 test가 핵심 사용자 계약을 검증한다는 뜻이고, `PARTIAL`은 helper나
일부 경로만 검증한다는 뜻이다. `GAP`은 사용자 계약 수준의 test가 없으며,
`CORRECT-GAP`은 현재 V1 bug를 golden behavior로 만들지 않고 수정 요구만 고정해야 한다.

각 PHASE 1 characterization test에는 `Feature ID`, `FR ID`, `PRESERVE/CORRECT/DECIDE`를
test name 또는 marker/fixture metadata로 연결한다. 아래 파일명은 `tests/` 기준이다.

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

## Coverage summary

| Status | Feature count | Meaning |
| --- | ---: | --- |
| COVERED | 1 | 핵심 V1 계약이 현재 test로 고정됨; metadata/race 보강은 남음 |
| PARTIAL | 25 | helper/일부 path만 검증되어 golden 또는 failure proof 필요 |
| GAP | 18 | 사용자 계약 수준 test가 없음 |
| CORRECT-GAP | 1 | V1 bug를 복제하지 않는 수정 요구 test가 필요 |

현재 숫자는 line coverage가 아니라 feature-contract trace다. PHASE 1 exit에서는 주요 사용자
계약의 `PARTIAL/GAP`을 characterization 또는 명시적 future-phase proof로 연결하고, autoplay
성공, corrupt/0-byte DB, 핵심 concurrency/failure 계획을 반드시 포함한다.
