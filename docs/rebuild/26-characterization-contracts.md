# 26. PHASE 1 Characterization Contracts

## Scope and evidence rule

PHASE 1은 V1 feature나 V2 architecture를 구현하지 않는다. `tests/characterization/`은
현재 관찰 가능한 사용자 계약을 실행 가능한 test로 고정한다. 각 test name과 docstring은
Feature ID, FR ID, `PRESERVE`/`CORRECT`를 포함한다.

- `PRESERVE`: V1을 직접 실행해 통과해야 하는 golden contract
- `CORRECT`: 승인된 정상 동작을 strict expected-failure로 실행한다. 현재 V1 결함이
  성공 기준이 되지 않으며, 구현 후 XPASS가 suite를 실패시켜 marker 제거를 요구한다.
- `DECIDE`: 이번 필수 범위에는 새 blocker가 없다.

모든 DB test는 pytest의 격리된 임시 DB 또는 `tmp_path`만 사용한다. Discord, Gemini,
YouTube, oEmbed, WebSocket peer와 production host/network에는 실제 접속하지 않는다.

## Discord command contract

| Feature / FR | Slash signature | success visibility | validation/unavailable/error | Mode |
| --- | --- | --- | --- | --- |
| F008 / FR-003,027 | `/요약 hours:number=6.0` | defer/public result | unavailable, no data, provider failure는 ephemeral; parse failure raw 공개는 CORRECT | PRESERVE/CORRECT |
| F012 / FR-003,012 | `/재생 검색어:string` required | handler가 ephemeral defer/result | Cog unavailable도 ephemeral | PRESERVE |
| F037 / FR-003,038 | `/시청` | public invite | Cog unavailable는 ephemeral; DB failure의 second response는 CORRECT | PRESERVE/CORRECT |
| F031 / FR-003,033 | `/내정보 user:user=None` | **ephemeral** profile | non-master의 타인 인자는 조용히 무시; failure는 ephemeral | PRESERVE |
| F032 / FR-003,033 | `/랭킹 ephemeral:boolean=False` | option 값을 따름 | defer 전 failure는 ephemeral; defer 뒤 error visibility 불일치는 CORRECT | PRESERVE/CORRECT |
| F033 / FR-003,034,035 | `/생일등록 user month day` required | 모든 결과 ephemeral | master exact match; 실제 calendar validation은 CORRECT | PRESERVE/CORRECT |
| F034 / FR-003,034 | `/생일삭제 user` required | 모든 결과 ephemeral | master denial, missing/existing 결과 문구 고정 | PRESERVE |
| F035 / FR-003,036 | `/생일목록 ephemeral:boolean=False` | non-empty는 option을 따름 | empty는 V1과 같이 항상 ephemeral | PRESERVE |

공통 command router error는 ACK 전 `response.send_message`, ACK 뒤 `followup.send`를 정확히
한 번 사용하고 안전한 동일 문구를 ephemeral로 보낸다. 개별 Cog의 불일치는 V2 handler의
`FR-004` 교정 대상이다.

Mention help는 `commands.when_mentioned`만 prefix로 사용하고 discord.py default `help`를
rollback window 동안 유지한다. `dm_help=False`, `verify_checks=True`이므로 guild 호출의
기본 destination은 호출 channel이며 hidden/failed-check command를 임의 노출하지 않는다.

## Component and pagination contract

| Feature / FR | Frozen component behavior | Mode |
| --- | --- | --- |
| F011/F023 / FR-011,018 | player row 0은 pause/skip/leave/favorite/queue, row 1은 loop/autoplay/favorites/search, 인기 곡 최대 3개 | PRESERVE |
| F013 / FR-012 | search modal 1개 text input, search result select는 title/index/duration 설명을 유지 | PRESERVE |
| F022 / FR-016 | queue select와 `맨 위로`, `삭제`, `섞기`, `전체삭제`; clear는 `확인`/`취소` | PRESERVE |
| F025 / FR-020 | user-global favorites select, 전체/해제, add/delete mode와 action | PRESERVE |
| F009/F010 / FR-028,029 | advanced modal 3개 input, refresh/advanced button, topic detail select와 ephemeral detail | PRESERVE |
| F002/F037/F042 / FR-005,038,043 | Watch link, master close와 restart custom ID/label/timeout | PRESERVE |
| F010/F013/F022/F025 / FR-021,029 | 25개를 넘는 queue/favorite/search/topic은 stable ID pagination하며 저장 데이터를 truncate/delete하지 않음 | CORRECT |

V1의 queue index와 25-item slice는 관찰 사실일 뿐 golden contract가 아니다. pagination과
stable ID를 요구하는 test는 현재 strict xfail이다.

## Music behavior and state compatibility

| Feature / FR | Contract | Evidence / Mode |
| --- | --- | --- |
| F022/F023 / FR-016,018 | NONE은 queue head를 소비, SONG은 current를 재선택, QUEUE는 head를 소비한 뒤 완료 곡을 tail로 순환 | direct state tests / PRESERVE |
| F018 / FR-015 | 첫 실패 3초, 둘째 8초, 셋째 실패는 current/retry를 지우고 다음 곡으로 진행 | deterministic clock/state test / PRESERVE |
| F024 / FR-018,019 | autoplay는 이전 제목 history/dedup과 90초 초과·600초 미만 후보를 적용해 다음 곡을 enqueue; provider failure는 해당 lookup만 종료 | injected provider success/failure / CORRECT |
| F028 / FR-024 | legacy JSON key와 song field, current-before-queue, loop/autoplay/elapsed/channel 의미를 읽음 | exact shape + restore test / PRESERVE |
| F028/F045 / FR-024,025 | atomic/version/checksum과 restore ACK 뒤 consume, legacy missing volume은 단일 0.5 default | future adapter strict specs / CORRECT |

Autoplay test는 missing symbol로 실패하는 V1 경로를 기대하지 않는다. 추출 의존성을 test에
주입해 recommendation success를 요구하므로 V1의 `NameError`는 golden behavior가 아니다.

## Engagement contract

- F029 / FR-031 `PRESERVE`: 공백은 0, 완성형 한글은 종성 없음 2/종성 있음 3,
  그 밖의 non-whitespace code point는 1 XP다. bot/DM은 제외하고 guild message에 적용한다.
- F030 / FR-032 `PRESERVE/CORRECT`: fake clock으로 unmuted duration을 초 단위 저장하고
  60초 미만 leave는 적립하지 않는다. channel move는 같은 session을 유지한다. V2 key는
  `(guild_id, user_id)`이고 mute/deaf/restart/leave/cancel race를 단일 정산한다.
- F031/F032 / FR-032,033: profile과 ranking은 `(total_vc_seconds // 60) * 5`의 완료분
  voice XP를 사용한다. profile은 현재 이를 만족하지만 V1 ranking의 fractional SQL은 strict xfail이다.
- F033–F036 / FR-034–037: master register/delete, guild list, KST 09:00 schedule을 유지한다.
  `datetime` fake clock이 2월 29일 조회를 검증한다. 실제 calendar validation과 비윤년
  2월 28일의 Feb-29 추가 조회는 strict xfail `CORRECT` 계약이다.

## Summary contract

F008–F010 / FR-026–030은 다음을 요구한다.

- 기본/고급/refresh 결과 shell은 public, topic detail과 사용자 오류는 ephemeral이다.
- source channel에 `view_channel`과 `read_message_history` 권한이 없는 requester는 Gemini
  호출 전에 거절한다.
- Gemini는 사용자 요청 때만 사용하며 total timeout 60초, active 1, waiting queue 4다.
  다섯 자리를 모두 사용 중이면 bounded overload 결과를 반환한다.
- timeout/cancel/provider/parse failure는 해당 요청에만 영향을 주며 raw message나 raw
  provider output을 public response 또는 log에 남기지 않는다.
- V1 success/no-data/provider failure shell은 통과하고 ACL, timeout, concurrency와 raw parse
  redaction은 현재 strict xfail이다.

## Watch compatibility contract

- F038/F040 / FR-039: `GET /watch?session=`, `GET /api/playlist/{session_id}`,
  `POST /api/playlist/{session_id}/add`, `POST /api/playlist/{session_id}/remove`와 add body
  `video_url`/`added_by`를 보존한다.
- F039 / FR-040,041: `WS /ws/{session_id}`와 client type `join`, `chat`, `state_change`,
  `seek`, `sync_request`, `sync_response`, `playlist_change`를 보존한다. invalid session은
  accept 전 code 4003으로 닫는다. join은 `user_joined`, `user_list`, `sync_request` 순으로
  발생하고 disconnect는 `user_left`, `user_list`를 발생시킨다.
- F041 / FR-042: 생성 직후 30초 creation grace가 끝난 다음 empty check 전 5초 grace를
  적용하며 마지막 disconnect가 5초 timer를 예약한다. fake clock/sleep으로 고정했다.
- F037/F042 / FR-004,038,043: public invite와 master control은 유지하되 durable session이
  invite보다 먼저 commit되어야 하고 post-ACK 실패는 followup 하나로 끝나야 한다.
  이 두 ordering/responder 교정은 strict xfail이다.

## Database recovery contract

F001 / FR-001,046 `CORRECT`:

- 기존 corrupt SQLite는 startup을 실패시키고 원본 bytes를 덮어쓰지 않는다. 이 경로는
  temp DB test가 통과한다.
- 기존 0-byte 파일은 정상 DB로 schema-create하지 않는다. valid backup 복구 또는 명시적인
  bootstrap operation 없이는 fail-closed한다. V1이 schema를 자동 생성하므로 strict xfail이다.
- PHASE 1은 실제 `data/bot_database.db`, SQL backup, remote backup, production migration이나
  cutover를 읽거나 수정하지 않는다.

## Strict expected failures owned by later phases

| Contract | Owner phase |
| --- | --- |
| Summary ACL/60s timeout/active 1 + queue 4/raw redaction | 5 |
| UI pagination and stable IDs | 5/7 |
| ranking completed-minute parity, calendar dates, Feb-29 fallback | 4 |
| legacy snapshot 0.5 default, restore ACK/version/checksum | 3/7 |
| durable Watch creation and single responder | 6 |
| existing zero-byte DB fail-closed | 3 |

Strict xfail은 미구현을 숨기는 skip이 아니다. 이후 Phase가 해당 동작을 구현하면 XPASS가
failure가 되며, 구현 test로 전환하고 이 표와 trace를 동시에 갱신해야 한다.
