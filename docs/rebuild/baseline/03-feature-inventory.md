# 03. Feature Inventory

## 분류 기준

기능은 사용자가 독립적으로 인식하거나 운영자가 독립적으로 켜고 검증할 수 있는
capability를 하나의 단위로 잡았다. 이 경계에서 **45개**이며, 내부 helper 수를 센 값이
아니다. `MUST KEEP`은 현 제품 계약, `SHOULD KEEP`은 결과는 유지하되 구현은 교체 가능,
`LEGACY`와 `UNKNOWN`은 최초 조사 당시 사용자 결정 전 제거할 수 없다는 뜻이었다. PHASE 0
결정 closure 뒤 F044/F045도 전환기 보존 대상으로 확정했다.

## 사용자 기능과 규칙

| ID | 기능 / 사용자 | trigger와 입력 | 출력 / 핵심 규칙 | 검증·권한 | 처분 |
| --- | --- | --- | --- | --- | --- |
| F001 | 기동·DB 복구·종료 / 운영자 | process start/stop | DB 준비 후 Cog·웹 시작; 정상 종료 때 cleanup | token 필수; DB 무결성 검증은 불충분 | MUST KEEP |
| F002 | 운영 로그·관리 panel / 운영자 | log record, ready | 파일/console/Discord 경고·오류, restart button | log channel; button은 master만 | SHOULD KEEP |
| F003 | 수동 update/restart / master | 관리 panel button | 음악 snapshot 후 updater 실행 | `MASTER_USER_ID` exact match | SHOULD KEEP |
| F004 | 자동 code/dependency update / 운영자 | cron 5분/일 1회 | `origin/main`, yt-dlp/provider 갱신과 restart/rollback | OS 권한·network; 동시 실행 방지 없음 | SHOULD KEEP |
| F005 | 암호화 backup/복구 / 운영자 | cron 6시간, DB 부재 startup | V2 전체 dump 암호화, local archive, private branch | Fernet key·private URL; legacy restore 호환 | MUST KEEP |
| F006 | 요약 message preload/live 수집 / 일반 사용자 | ready, `on_message` | 지정 channel 원문을 memory deque에 유지 | bot 제외, fixed channel | MUST KEEP |
| F007 | 요약 retention/prune / 운영자 | background loop | 시간과 최대 건수로 원문 제거 | 코드/템플릿 default 불일치 | MUST KEEP |
| F008 | 기본 대화 요약 / 일반 사용자 | `/요약 hours` | 공개 summary embed + 상세 controls | guild/자료 존재; source ACL 확인 없음 | MUST KEEP |
| F009 | 고급 요약 / 일반 사용자 | 고급 button/modal | 날짜·참여자·추가 prompt로 Gemini 요약 | 날짜 형식 외 범위 제한 미흡 | MUST KEEP |
| F010 | topic 상세·새로고침 / 일반 사용자 | topic select/refresh | topic은 ephemeral, refresh는 새 summary | Select 최대 25 topic 한계 | MUST KEEP |
| F011 | 음악 dashboard·channel 정리 / 청취자 | ready, channel message | 고정 jukebox dashboard 유지, 대화 message 삭제 | `MUSIC_CHANNEL_ID` | MUST KEEP |
| F012 | 단일 URL 재생 요청 / 청취자 | `/재생` 또는 URL message | metadata 후 queue/재생 | YouTube URL, voice 접속 정책 | MUST KEEP |
| F013 | 검색 후 곡 선택 / 청취자 | 검색어/modal | 최대 검색 결과 select → queue | yt-dlp 결과; Select 제한 | MUST KEEP |
| F014 | playlist URL 전개 / 청취자 | playlist URL | 앞에서 최대 50곡 queue | 최대 50은 현재 안전 경계 | MUST KEEP |
| F015 | 음악 channel URL 수신·삭제 / 청취자 | `on_message` | 요청 처리 후 원문 삭제 | 지정 channel only | MUST KEEP |
| F016 | 음성 연결·이동·master 정책 / 청취자 | 재생/voice controls | 요청자 channel로 connect/move | master 예외 포함 현 정책 freeze 필요 | MUST KEEP |
| F017 | 실제 audio 획득·재생/cache / 청취자 | play loop | download 우선, direct rollback backend, FFmpeg | 100MiB track, guild별 512MiB cache default | MUST KEEP |
| F018 | playback 실패 retry/skip / 청취자 | FFmpeg/download 오류 | 3초, 8초 후 재시도; 세 번째 실패 skip | 사용자 관찰 동작 유지 | MUST KEEP |
| F019 | pause/resume / 청취자 | dashboard button | current stream pause/resume | voice/current song 필요 | MUST KEEP |
| F020 | skip/cancel / 청취자 | skip button | 현재 곡 종료 후 다음 곡 | voice/current song 필요 | MUST KEEP |
| F021 | leave/reconnect/empty auto-leave / 청취자 | button, voice event | disconnect, 비어 있으면 자동 정리 | guild voice 상태 | MUST KEEP |
| F022 | queue 조회·이동·삭제·shuffle·clear / 청취자 | queue UI | queue 편집과 dashboard 반영 | stale index race 존재; confirm 일부 | MUST KEEP |
| F023 | 반복 모드 / 청취자 | loop button | off → one → all 순환 | guild별 state | MUST KEEP |
| F024 | 자동 추천재생 / 청취자 | autoplay toggle, empty queue | history 기반 YouTube 추천 | 현재 success path는 `NameError` | MUST KEEP |
| F025 | 사용자 전역 즐겨찾기 / 청취자 | favorite UI | add/delete/select all/deselect/play | guild와 무관; 25개 초과 UI 위험 | MUST KEEP |
| F026 | 인기 곡 표시 / 청취자 | dashboard top songs | guild별 play count 상위 3 | 재시도/resume 중복 집계 가능 | SHOULD KEEP |
| F027 | 음성 입장 TTS / 청취자 | voice join | 이름 안내 후 음악 재개 | gTTS 조건부; timeout 없음 | SHOULD KEEP |
| F028 | 음악 재시작 snapshot/복원 / 청취자 | unload/update/next ready | channel, 위치, queue, loop/autoplay 복원 | JSON을 restore 확인 전 소비 | MUST KEEP |
| F029 | text XP / 일반 사용자 | guild `on_message` | 한글 구성 기반 XP 적립 | bot 제외; cooldown/max 없음 | MUST KEEP |
| F030 | voice XP / 일반 사용자 | voice join/leave | 완전한 분당 5 XP 적립 | hard crash 손실; key가 user only | MUST KEEP |
| F031 | 내 정보 / 일반 사용자 | `/내정보 [user]` | XP, level, voice 정보 | guild context | MUST KEEP |
| F032 | 랭킹 / 일반 사용자 | `/랭킹 [ephemeral]` | guild 상위 사용자 | voice XP rounding이 profile과 다름 | MUST KEEP |
| F033 | 생일 등록 / master | `/생일등록 user month day` | user/guild 생일 upsert | master only; 실제 calendar 검증 없음 | MUST KEEP |
| F034 | 생일 삭제 / master | `/생일삭제 user` | 생일 null 처리 | master only | MUST KEEP |
| F035 | 생일 목록 / 일반 사용자 | `/생일목록 [ephemeral]` | guild 등록 목록 | guild context | MUST KEEP |
| F036 | 일일 생일 알림 / 일반 사용자 | KST 09:00 loop | 당일 생일 mention | fixed summary channel, multi-guild 위험 | MUST KEEP |
| F037 | Watch session 생성·초대·관리 알림 / 사용자·운영자 | `/시청` | capability URL, 관리 서버 종료 button | guild context; DB commit보다 invite가 빠름 | MUST KEEP |
| F038 | Watch browser player / 초대받은 사용자 | `GET /watch?session=` | YouTube player, playlist, chat UI | session 존재 여부 | MUST KEEP |
| F039 | Watch presence/chat/playback sync / 참여자 | WebSocket messages | join/chat/state/seek/sync relay | login/host 없음; schema/rate limit 없음 | MUST KEEP |
| F040 | Watch playlist CRUD/oEmbed / 참여자 | HTTP add/remove/get | shared playlist와 title | session UUID; add/close race | MUST KEEP |
| F041 | Watch grace/empty expiry / 참여자 | create/disconnect | 개설 30초, 빈 방 5초 뒤 종료 | 기존 timing 계약 | MUST KEEP |
| F042 | Watch master 강제 종료 / master | 관리 button | 접속자·초대·session·playlist 정리 | master exact match | MUST KEEP |
| F043 | stale Watch cleanup / 운영자 | ready | 재시작 전 session 정리 | browser 재연결과 race | MUST KEEP |
| F044 | 기본 mention-prefix help / 사용자 | bot mention + `help` | discord.py default help | rollback window 동안 보존, Phase 11 전 삭제 금지 | MUST KEEP |
| F045 | 저장된 음악 volume 읽기 / 청취자 | state 생성/restore | persisted volume 적용 | persisted 값 호환, 새 session default 0.5, 새 UI는 추가하지 않음 | MUST KEEP |

## 기술 의존성과 위험

| 범위 | persistence | 외부/Discord 의존 | background·timeout | concurrency와 기능 결합 |
| --- | --- | --- | --- | --- |
| F001–F005 | SQLite, 암호화 SQL, archive, marker files | Git, pip, Deno, systemd, Discord | startup/cron/subprocess; Git·pip timeout 없음 | process-local DB lock은 cron과 비공유; updater 중복 가능 |
| F006–F010 | process deque only | Discord history, Gemini | preload/prune/Gemini; Gemini deadline 없음 | global client와 원문 buffer, 동시 summary 무제한 |
| F011–F028 | SQLite settings/count/favorites, JSON, temp cache | Discord voice/UI, yt-dlp, YouTube, gTTS, FFmpeg | play/UI/autoplay/download/TTS tasks | guild state 공동 변경; default executor와 DB 공유; queue/cache 일부 무제한 |
| F029–F036 | `users` | Discord message/voice/scheduler | birthday loop, voice session | DB global lock; voice session user-only; fixed channel |
| F037–F043 | Watch tables + process dict/browser state | Discord, FastAPI/WS, YouTube oEmbed/IFrame | self-destruct/reconnect | 외부 traffic와 Discord가 같은 loop; session actor/lock/cap 없음 |
| F044–F045 | volume row only | discord.py default command | 없음 | 제품 의도 불명 |

## 구현 위치와 교차 의존성

| 기능군 | 현재 핵심 파일 | 교차 의존성 |
| --- | --- | --- |
| lifecycle/data/ops | `main_bot.py`, `database_manager.py`, `scripts/*` | 모든 Cog가 한 DB module과 process lifecycle 공유 |
| summary | `application_commands.py`, `summary/*` | fixed channel, Discord history, Gemini |
| music | `music_agent.py`, `music_core.py`, `music_playback.py`, `music_ui.py`, state store/restorer | DB compatibility exports, logging update, Discord voice/UI |
| engagement | `leveling_core.py`, `birthday_core.py` | 같은 `users` table과 global channel config |
| Watch | `watch_agent.py`, `watch_server.py`, `player.html` | global FastAPI app, DB, Discord bot injected in `app.state` |
| logging/admin | `log_agent.py` | root logger, shell updater, music snapshot, Watch manager |

## Legacy removal inventory

F044와 F045는 전환기에 보존한다. direct playback backend도 7일 rollback window 동안
유지한다. orphan `TopSongButton`, `Song.to_embed`, `FFMPEG_OPTIONS`, runtime 미사용
`load_music_states`, `DEBUG_MODE`는 구현 표면이지 독립 사용자 기능으로 세지 않았으며,
Phase 11에서 별도 사용자 승인 전 삭제하지 않는다.
