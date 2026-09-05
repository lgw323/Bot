# 12. Functional Requirements

`PRESERVE`는 현 동작을 그대로 보호, `CORRECT`는 현재 결함을 정상 요구로 만들지 않음,
`DECIDE`는 사용자 승인 전 미확정이다.

| ID | requirement | source/acceptance | mode |
| --- | --- | --- | --- |
| FR-001 | DB와 필수 config 검증 후에만 command plane ready가 된다. | F001; corrupt/partial/config fault test | CORRECT |
| FR-002 | 필수 capability별 startup 성공/실패를 표시하고 partial load를 숨기지 않는다. | F001/F002 | CORRECT |
| FR-003 | 8개 slash command의 이름·parameter·기본 공개성을 보존한다. | inventory/golden tests | PRESERVE |
| FR-004 | 모든 interaction은 정확히 한 responder가 response/defer/followup을 관리한다. | delayed/error tests | CORRECT |
| FR-005 | master operation은 `MASTER_USER_ID` exact-match authorization port로 보호한다. | birthday/log/Watch auth tests | PRESERVE |
| FR-006 | 기존 channel/voice 의미를 guild-specific configuration과 guild isolation으로 적용한다. | multi-guild matrix | PRESERVE/CORRECT |
| FR-007 | mention-prefix help는 rollback window 동안 보존한다. | F044 | PRESERVE |
| FR-008 | reconnect 시 ready 초기화가 idempotent하다. | repeated-ready test | CORRECT |
| FR-009 | 정상 종료가 admission 차단, task drain/cancel, state flush, client close를 수행한다. | shutdown test | CORRECT |
| FR-010 | 사용자 오류는 기존 UX에 맞는 공개/ephemeral 메시지로 반환한다. | golden text snapshots | PRESERVE |
| FR-011 | 지정 music channel에 단일 dashboard를 유지하고 일반 message를 정리한다. | F011 | PRESERVE |
| FR-012 | URL, 검색, modal/select, playlist 최대 50곡 요청을 지원한다. | F012–F015 | PRESERVE |
| FR-013 | voice connect/move/reconnect/leave/empty-channel 규칙을 보존한다. | F016/F021 | PRESERVE |
| FR-014 | download playback과 승인된 fallback으로 audio를 재생한다. | F017 | PRESERVE |
| FR-015 | 실패 시 3초·8초 후 재시도하고 세 번째 실패에서 skip한다. | F018 clock test | PRESERVE |
| FR-016 | pause/resume, skip, queue view/move/remove/shuffle/clear를 제공한다. | F019/F020/F022 | PRESERVE |
| FR-017 | queue operation은 stable item ID로 사용자가 본 곡에 적용된다. | concurrent stale UI test | CORRECT |
| FR-018 | loop off/one/all과 autoplay toggle을 guild별 유지한다. | F023/F024 | PRESERVE |
| FR-019 | autoplay는 history/dedup 정책으로 실제 다음 곡을 제공하거나 설명 가능한 실패를 반환한다. | success/failure contract | CORRECT |
| FR-020 | favorite는 Discord 사용자 전역이며 add/delete/select/play를 지원한다. | F025 | PRESERVE |
| FR-021 | Discord UI limit을 넘는 queue/favorite/search 결과는 pagination한다. | >25 test | CORRECT |
| FR-022 | 실제 playback 시작 시 session당 한 번 집계하여 guild 인기 곡을 제공하고 retry/TTS resume은 중복 집계하지 않는다. | F026/retry-resume test | CORRECT |
| FR-023 | join TTS가 enabled일 때 음악과 충돌 없이 재생되고 실패 시 음악을 복구한다. | F027 fault test | PRESERVE/CORRECT |
| FR-024 | music state를 versioned atomic snapshot으로 저장하고 성공 ack 뒤 소비한다. | F028 restart/failure test | CORRECT |
| FR-025 | persisted volume을 호환하고 새 session default를 0.5의 한 경로로 적용한다. | F045 | PRESERVE/CORRECT |
| FR-026 | 지정 channel message를 restart 경계 누락/중복 없이 retention 내 수집한다. | F006/F007 | CORRECT |
| FR-027 | `/요약` hours 조건으로 공개 기본 요약을 제공한다. | F008 | PRESERVE |
| FR-028 | advanced date/user/prompt filtering을 제공하고 입력 범위를 검증한다. | F009 | PRESERVE/CORRECT |
| FR-029 | refresh와 ephemeral topic detail을 제공하며 25개 초과를 pagination한다. | F010 | PRESERVE/CORRECT |
| FR-030 | requester source ACL을 통과한 최소 message만 Gemini에 보내며 raw content를 log/장기 보존하지 않고 timeout/degraded 결과를 알린다. | security/fault tests | CORRECT |
| FR-031 | 승인된 text XP 공식을 guild message에 적용한다. | F029 characterization | PRESERVE |
| FR-032 | voice XP를 guild/user의 연속 voice session에 완료된 분 단위로 적립하고 profile/ranking이 같은 공식을 쓴다. | F030–F032 | PRESERVE/CORRECT |
| FR-033 | `/내정보`와 `/랭킹`의 승인된 출력/ephemeral option을 유지한다. | F031/F032 golden | PRESERVE |
| FR-034 | master가 생일을 등록·삭제할 수 있다. | F033/F034 | PRESERVE |
| FR-035 | 실제 calendar 날짜만 허용하고 2월 29일은 비윤년에 2월 28일 알림을 보낸다. | date matrix | CORRECT |
| FR-036 | guild 생일 목록을 요청 공개성으로 제공한다. | F035 | PRESERVE |
| FR-037 | KST 09:00에 올바른 guild/channel에 한 번 생일 알림을 보낸다. | F036 clock/multi-guild | PRESERVE/CORRECT |
| FR-038 | `/시청`은 durable session 생성 후 호환 URL invite를 한 번 발송한다. | F037 click/failure test | PRESERVE/CORRECT |
| FR-039 | browser player와 기존 HTTP path/request/response를 호환한다. | F038/F040 contract | PRESERVE |
| FR-040 | 기존 7개 WS message type으로 presence/chat/play/seek/sync/playlist를 제공한다. | F039 contract | PRESERVE |
| FR-041 | Watch는 별도 login/host 없이 capability link 참여를 유지한다. | product contract | PRESERVE |
| FR-042 | 30초 creation grace와 5초 empty grace를 보존한다. | fake clock test | PRESERVE |
| FR-043 | master close가 connection/invite/session/playlist/timer를 idempotently 제거한다. | F042 race test | PRESERVE/CORRECT |
| FR-044 | restart stale session을 browser admission 전 정책대로 정리한다. | F043 restart test | CORRECT |
| FR-045 | 새 backup은 전체 dump V2 encryption을 사용하고 legacy backup을 복원한다. | F005 round-trip | PRESERVE |
| FR-046 | DB bootstrap은 valid DB/backup 또는 명시 승인 없이 empty writable DB를 만들지 않는다. | zero-byte/corrupt tests | CORRECT |
| FR-047 | backup은 한 시점의 SQLite snapshot이며 publish 전 semantic validation한다. | concurrent write test | CORRECT |
| FR-048 | 운영 log/panel과 manual update/restart 기능을 권한 내 제공한다. | F002/F003 | PRESERVE |
| FR-049 | 자동 update는 한 실행만 허용하고 immutable release를 검증·전환·rollback한다. | F004 deploy tests | CORRECT |
| FR-050 | 모든 durable 변화와 restore/cutover는 audit 가능한 결과를 남긴다. | operations acceptance | CORRECT |
