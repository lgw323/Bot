# 08. Business Rules

## 확정된 제품 규칙

| ID | 규칙 | 출처/비고 |
| --- | --- | --- |
| BR-001 | 기존 command 이름, 응답 문구, 공개/ephemeral 방식과 button 의미를 기본 보존한다. | AGENTS/product contract; exact golden freeze 필요 |
| BR-002 | 음악 channel은 대화방이 아니라 dashboard형 jukebox이며 사용자 message를 정리한다. | product spec + music handlers |
| BR-003 | queue, pause/resume, skip, loop off/one/all, autoplay를 guild별로 제공한다. | active behavior |
| BR-004 | playlist 요청은 최대 50곡을 가져온다. | current validation |
| BR-005 | 재생 실패는 3초, 8초 후 재시도하고 세 번째 실패에서 다음 곡으로 간다. | user-observable recovery |
| BR-006 | 즐겨찾기는 guild별이 아니라 Discord 사용자 전역이다. | explicit product contract |
| BR-007 | 재시작 후 음성 channel, 위치, queue, volume, loop/autoplay를 복원하는 것이 목표다. | product contract |
| BR-008 | summary source와 생일 알림은 현재 같은 main channel이다. | explicit operating intent |
| BR-009 | 기본 summary는 공개, topic 상세는 ephemeral이다. | UI behavior |
| BR-010 | text XP는 현재 한글 구성 기반 공식, voice XP는 완전한 분당 5다. | code; ranking 불일치는 bug 후보 |
| BR-011 | 생일 알림은 KST 09:00이다. | birthday loop |
| BR-012 | 생일 등록/삭제와 운영 panel 작업은 `MASTER_USER_ID`만 허용된다. | exact user-ID check |
| BR-013 | Watch는 신뢰하는 친구가 capability link를 공유하며 별도 login/host 권한을 추가하지 않는다. | explicit product contract |
| BR-014 | Watch URL, HTTP path/payload, WebSocket message type을 전환 중 호환한다. | explicit product contract |
| BR-015 | Watch는 생성 후 30초 접속 유예, 마지막 퇴장 후 5초 유예를 가진다. | explicit product contract |
| BR-016 | 관리 서버의 Watch 종료는 master만 실행하며 socket, invite, session, playlist, timer를 함께 정리한다. | explicit product contract |
| BR-017 | 새 remote backup은 전체 SQL file을 `DB_ENCRYPTION_KEY`로 암호화하고 legacy encrypted backup은 읽는다. | data contract |
| BR-018 | backup remote가 없으면 공개 code origin으로 우회하지 않는다. | security/data contract |
| BR-019 | SQLite schema, SQL backup envelope, music JSON은 승인 없는 breaking change를 하지 않는다. | migration guard |

## PHASE 0에서 해소한 기존 불명확 규칙

| ID | 관찰된 V1 동작 | 확정된 V2 규칙 |
| --- | --- | --- |
| BR-U01 | default mention-prefix `help`가 활성 | rollback window 동안 보존; Phase 11 전 제거 금지 |
| BR-U02 | music volume default가 DB/새 state/restore에서 1.0/0.5/1.0 | persisted 값을 호환하고 새 session default를 0.5로 통일; 새 UI는 추가하지 않음 |
| BR-U03 | 재생 시작 호출마다 count 증가 | 실제 playback start 시 session당 1회; retry/TTS resume 중복 금지 |
| BR-U04 | ranking voice XP가 profile보다 세밀 | 완료된 분 단위 공식을 profile/ranking 모두 적용 |
| BR-U05 | 생일은 month/day 범위만 검사하여 2월 31일 허용 | 실제 날짜만 허용; Feb-29는 비윤년에 Feb-28 알림 |
| BR-U06 | 모든 guild message에 text XP, cooldown/일일 상한 없음 | 재구축 중 현재 XP 지급 의미를 보존하고 anti-abuse 정책을 임의 추가하지 않음 |
| BR-U07 | Watch session에 hard TTL/participant/playlist cap 없음 | 모든 workload를 bounded typed config로 제한; 정확한 값은 Pi 측정으로 조정 |
| BR-U08 | summary 원문·닉네임을 Gemini에 그대로 전송 | requester ACL, minimization, no raw-content logging/long-term storage 적용 |
| BR-U09 | fixed channel ID가 guild별 설정보다 우선 | channel/feature config를 guild별로 표현하고 cross-guild 노출 금지 |
| BR-U10 | direct music backend와 여러 orphan symbol/config | direct는 7일 rollback window 동안 유지; orphan 제거는 Phase 11 승인 대상 |

## 명시적으로 버그를 요구사항으로 만들지 않는 항목

autoplay `NameError`, interaction 이중 응답, source ACL 누락, stale queue index, partial DB
migration, corrupt DB 복구 우회, invite-before-commit, voice session guild 누락, retry/resume
play-count 중복은 현재 구현 결함이다. 기존 사용자에게 의존성이 확인되지 않는 한 새 시스템의
정상 동작으로 복제하지 않는다. behavior change가 관찰 가능한 경우에는 기존/수정 동작과
compatibility plan을 제시하고 승인받는다.
