# 04. Command and Event Inventory

## Slash command

| 이름 | 목적 / 입력 | 조건·권한·channel | DB/API·side effect | 실패 행동 |
| --- | --- | --- | --- | --- |
| `/요약` | 최근 `hours`시간 요약 | guild, 수집 자료; source channel ACL 검증 없음 | deque read, Gemini, 공개 embed | 자료 없음/AI 오류 메시지; long call은 defer |
| `/재생` | URL 또는 검색어 재생 | 음악 정책에 맞는 voice/channel | yt-dlp, voice connect, queue mutation, 원문/log | route/Cog/metadata/voice 오류 응답 |
| `/시청` | 공동 시청방 개설 | guild | Discord invite 먼저 전송, DB session insert, 관리 알림 | insert 실패 시 이미 응답한 interaction에 재응답 가능 |
| `/내정보` | 본인 또는 `user` XP 조회 | guild | `users` read, ephemeral profile | 사용자 자료 없음/DB 오류 |
| `/랭킹` | guild ranking, `ephemeral` 선택 | guild | `users` ranking query | DB 오류 메시지 |
| `/생일등록` | `user month day` | `MASTER_USER_ID` | `users` upsert | month 1–12/day 1–31만 검사, defer 없음 |
| `/생일삭제` | `user` | master | 생일 column null | 대상/DB 오류, defer 없음 |
| `/생일목록` | guild 목록, `ephemeral` 선택 | guild | birthday read | 없음/DB 오류, defer 없음 |

등록은 `bot.tree.command`와 Cog app command를 섞어 쓰며 startup에 global
`tree.sync()`를 한 번 시도한다. guild-scoped staging sync나 sync 상태 health는 없다.

## Prefix/context/autocomplete/reaction/webhook

- 사용자 정의 prefix command는 없다. `commands.Bot(command_prefix=commands.when_mentioned)`의
  default help command가 남아 있어 mention-prefix `help`가 암묵적으로 존재한다.
- context menu, autocomplete, reaction handler, member/guild/scheduled-event handler,
  Discord webhook은 확인되지 않았다.
- bot은 message content와 members privileged intent를 요청한다. Developer Portal 승인과
  실제 invite permission은 저장소에서 확인할 수 없다.

## Discord event

| event | handler 수 / 목적 | 조건·의존 | side effect와 실패 경계 |
| --- | --- | --- | --- |
| `on_ready` | 6: root presence, log panel, summary preload, music dashboard/restore, leveling voice restore, Watch stale cleanup | reconnect마다 호출 가능 | 중복 실행 guard가 기능마다 다름; 부분 실패를 readiness에 반영하지 않음 |
| `on_message` | 3: summary 수집, text XP, music URL/jukebox cleanup | bot 제외·guild/fixed channel 규칙 | DB write, deque append, metadata task, message delete |
| `on_voice_state_update` | 2: voice XP, music/TTS/empty-channel handling | member/guild/voice state | session state, DB XP, TTS/voice controls |

## Music component callbacks

| UI | 동작 | 조건·권한 | persistence/API·실패/side effect |
| --- | --- | --- | --- |
| main buttons 9종 | pause/resume, skip, loop, autoplay, queue, favorites, search, reconnect/leave 계열 | guild/voice/current state; 별도 Discord role 없음 | voice/queue/UI message 수정; 여러 callback이 같은 `MusicState` 변경 |
| top-song buttons 3종 | 인기 곡 재요청 | row 존재 | DB read 결과 URL을 queue; stale result 가능 |
| queue select | queue item 선택 | 최대 25 option | index를 value로 사용; UI 뒤 queue 변경 시 다른 곡 대상 가능 |
| queue move/remove/shuffle/clear | 선택 곡 편집 또는 전체 편집 | current queue | queue mutation, dashboard edit; clear confirm/cancel 있음 |
| favorites select | 즐겨찾기 선택 | 사용자별 목록 | 전체 목록 load; 25개 초과 Select 생성 실패 가능 |
| select all/deselect/add-delete/toggle | favorite selection/현재 곡 저장 | interaction user | `favorites` write/read; 사용자 전역 |
| music search modal | 검색어 제출 | voice/channel policy | yt-dlp search; interaction deadline 위험 |
| search result select | 곡을 queue에 추가 | 최대 25 option | metadata→queue; 결과 expiry 처리 필요 |

구체적인 사용자 문구, 공개/비공개 여부, emoji, button ordering은 구현 전 golden
snapshot으로 동결한다. 새 설계에서 callback은 item index가 아닌 stable ID를 보낸다.

## Summary component callbacks

| UI | 목적 | 결과 |
| --- | --- | --- |
| refresh button | 같은 조건으로 다시 요약 | 새 Gemini 요청과 공개 message 갱신 |
| advanced button | 고급 modal 열기 | 입력 UI |
| topic select | 선택 topic 상세 | ephemeral 상세 embed |
| advanced modal | 날짜/사용자/추가 요청 적용 | filter 후 Gemini 요약 |

topic 수가 Discord Select의 25 option을 넘는 경우가 코드에서 제한되지 않는다. 원문
channel을 볼 수 없는 사용자가 command 결과를 보는 권한 경계도 명시돼 있지 않다.

## Watch/admin callbacks

| UI | 목적 | 권한·side effect |
| --- | --- | --- |
| Watch link button | browser session 진입 | URL을 아는 사람 누구나; 별도 login/host 없음 |
| session close button | 관리 서버에서 강제 종료 | master only; sockets, invite, session, playlist, timer 정리 |
| restart/update button | 수동 배포·재시작 | master only; 음악 JSON 저장 후 detached shell 실행 |

## HTTP API

| method/path | 입력/출력 | auth·validation | side effect |
| --- | --- | --- | --- |
| `GET /watch?session=` | HTML player | session UUID 존재 | 없음 |
| `GET /api/playlist/{session}` | playlist JSON | session 존재 | 없음 |
| `POST /api/playlist/{session}/add` | video URL, 사용자 → item | URL/session, body·rate 상한 없음 | oEmbed title 조회 후 insert, WS broadcast |
| `POST /api/playlist/{session}/remove` | query URL | session, 참여권 별도 없음 | delete, WS broadcast |

현재 path와 request/response 형식은 호환 계약이다. 새 내부 모델과 별개로 compatibility
adapter를 두고 계약 test로 보호한다.

## WebSocket

endpoint는 `WS /ws/{session}` 하나이며 client message type은 다음 7종이다.

| type | 목적 | 현재 검증/relay |
| --- | --- | --- |
| `join` | username 등록·presence | 이름 sanitize 후 broadcast |
| `chat` | chat 전송 | 이름/content 길이·escape 일부 |
| `state_change` | play/pause 상태 | payload를 peers에 relay |
| `seek` | 재생 위치 변경 | payload relay |
| `sync_request` | 새 client 상태 요청 | peers relay |
| `sync_response` | 상태 응답 | peers relay |
| `playlist_change` | playlist 변경 알림 | HTTP 작업 뒤 broadcast |

WebSocket은 session capability 외 권한, origin 제한, frame schema/size/rate 제한이 없다.
broadcast는 socket별 순차 `await send_text`이고 timeout이나 failed peer 제거가 없어 느린
client 하나가 session과 같은 loop의 Discord 처리를 지연시킬 수 있다.

## 응답 계약상의 공백

- slash command별 defer/followup/error helper 사용이 일관되지 않다.
- 명령/버튼에 `default_permissions`, role, `guild_only` decorator가 없다. 실제 권한은
  fixed ID와 runtime context 조건이다.
- Discord REST rate limit은 library 동작 외 application-level budget이 없다.
- reconnect 시 `on_ready` 재진입, command sync 중복, background task 중복을 전체적으로
  검증하는 contract가 없다.
- 모든 interface의 exact text·ephemeral·delete timing은 기존 코드를 근거로 한
  characterization artifact가 필요하다.
