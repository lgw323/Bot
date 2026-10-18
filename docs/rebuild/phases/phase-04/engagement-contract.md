# PHASE 4 Engagement Contract

2026-09-06. 사용자 PHASE 4 지시, current ADR-013/015/017/018/019와 PHASE 1 계약을 따른다.
대상은 F029–F036 / FR-031–037이다. V1 entrypoint, 실제 DB, Discord 로그인과 Pi에는 연결하지
않았다. Summary/Watch/Music/운영 기능은 후속 Phase에 남긴다.

## Boundaries and composition

- `engagement/domain/policy.py`: text/Jamo, completed-minute voice XP, level curve, 실제 날짜와 KST.
- `engagement/ports/`: 기존 membership repository와 transactional event/notification/authorization 계약.
- `engagement/application/service.py`: event, profile/ranking, master mutation과 daily delivery use case.
- `engagement/adapters/`: SQLite event owner, master exact match, Discord presentation/Gateway와 scheduler.
- `composition/engagement.py`: database → engagement 순으로 시작하는 명시적 builder. 반환된 bot에
  로그인하거나 command sync를 실행하지 않는다. V1 `main_bot.py`나 Cog loader를 바꾸지 않는다.

domain/application에는 SQLite/Discord type과 blocking dispatch가 없다. worker connection,
transaction/deadline/admission/cancellation은 PHASE 3 `SqliteDatabase`만 소유한다. Cog에는 XP/voice
session dictionary나 authorization 설정이 없다. 서비스의 admission/fault flag는 lifecycle 상태이고,
voice accrual·receipt·notification 상태는 DB transaction이 소유한다.

Windows의 최초 Discord SDK import는 aiohttp → stdlib platform OS 탐색에서 subprocess를 실행할
수 있었다. 따라서 SDK와 command decorator는 명시적인 adapter 생성 때만 로드한다. V2 package
전체를 import하는 기존 금지 검사(DB/network/task/thread/subprocess/env/root handler)는 유지했다.

## Text XP

완성형 한글 `가`–`힣`은 종성이 없으면 2, 있으면 3 XP다. 그 밖의 non-whitespace code point는
1, 공백은 0이다. 분해 Jamo를 다시 합치지 않는다. guild의 모든 채널에 적용하며 bot/DM은 제외한다.
새 cooldown이나 지급량 상한은 없다. 기존 xp에 증가량을 더하고 stored seconds는 바꾸지 않는다.

Discord message ID와 guild를 key로 receipt INSERT와 XP/level UPDATE를 같은 writer transaction에
묶는다. 동시 중복·재전송·응답 취소 뒤 retry는 한 번만 반영된다. receipt는 본문을 저장하지 않는다.
기본 보관 기간은 event 생성 후 7일(설정 1–30일), 전체 최대 100,000개(설정 최대 1,000,000개)다.
유효 receipt를 capacity 때문에 evict하지 않고 typed overload로 거절한다. 만료 event 재전송은
다시 적립하지 않는다. 5분 이상 미래 timestamp도 거절한다. 장기 historical message backfill은
이 live-event adapter의 범위가 아니다. receipt 만료 정리는 같은 transaction에서 수행한다.

## Voice XP and lifecycle

- key는 `(guild_id,user_id)`다. join/mute/deaf/move/leave를 하나의 DB 상태 전이로 처리한다.
- self/server mute 또는 deaf 중 하나라도 켜지면 유효 시간을 세지 않는다. channel move는 같은
  session이며 move와 함께 바뀐 mute/deaf 상태도 반영한다.
- 관찰된 unmuted 구간을 monotonic clock으로 누적한다. leave/graceful stop에 세션 합계를 정수
  초로 내리고 60초 미만이면 버린다. 59초 체류 두 번을 합쳐 적립하지 않는다. 기존 fractional
  seconds는 그대로 보존한다. 이 정책은 PHASE 1의 short-stay/truncation 계약을 따른다.
- voice XP는 오직 `int(total_vc_seconds // 60) * 5`다. profile, ranking, 레벨 갱신이 같은
  `Progress`/level curve를 사용한다. stored level cache를 낮추지는 않으며 표시는 재계산한다.
- Discord Gateway session의 SHA-256 식별자와 sequence를 사용한다. 같은 stream의 오래된/
  중복 sequence는 무해하다. leave tombstone도 남겨 오래된 join/move가 세션을 부활시키지 못한다.
  transport ID/원문 payload는 로그에 남기지 않는다.
- `on_ready`는 현재 보이는 non-bot voice member를 sequence 0으로 seed한다. 이미 처리한 세션은
  재설정하지 않는다. Gateway RESUME는 같은 stream을 유지한다. 새 Gateway session의 sequence
  reset은 진행 중 세션의 유효 duration을 보존한다.
- process restart는 새 epoch다. 과거 epoch에서 **이미 관찰되어 저장된** 구간만 한 번 정산하고,
  현재 접속자를 새로 seed한다. crash 직전 미관찰 구간과 offline 체류는 추측하지 않는다.
- DB failure/cancellation으로 voice observation이 불확실해지면 해당 서비스의 voice admission을
  fail-closed하고 재시작 reconciliation을 요구한다. 종료 시 마지막 상태를 계속 외삽하지 않고
  이미 관찰된 duration만 정산한다. text/조회 기능까지 별도 lock으로 막지는 않는다.
- shutdown은 listener 제거 → scheduler stop/drain → voice flush → bot close → DB close다.
  service admission을 닫은 뒤 writer lane에서 선행 작업과 정산을 직렬화한다. 늦은 event는 거절한다.

voice row/tombstone은 process epoch당 기본 10,000개, 설정 최대 100,000개다. 새 process에서
이전 epoch를 정리하며 capacity 초과는 명시적 failure다. transport는 Discord.py의 decoded
`socket_raw_receive`를 사용하므로 builder가 `enable_debug_events=True`를 지정한다. raw frame은
2MiB 상한으로 검사하고 보관하지 않는다. 실제 Gateway 연결 검증은 staging에 남아 있다.

## Commands, authorization and presentation

| 명령 | Signature / 공개성 / 의미 |
| --- | --- |
| `/내정보` | `user:Member=None`; 항상 ephemeral defer. master만 타인 조회, 나머지는 조용히 self. 없으면 0 XP/Lv.1. |
| `/랭킹` | `ephemeral:bool=False`; 합산 XP TOP 10. text/voice 선택 옵션을 추가하지 않는다. |
| `/생일등록` | `user,month,day` required; master exact match, 모든 결과 private. |
| `/생일삭제` | `user` required; master exact match, 모든 결과 private. |
| `/생일목록` | `ephemeral:bool=False`; nonempty는 option, empty는 항상 private. |

profile embed field/진행도/표시 시간, ranking medal·TOP 10·empty 문구와 생일 성공/실패 문구를
유지한다. 정상 register/delete는 Discord ACK deadline을 지키도록 private defer 후 followup을
사용한다. 권한/날짜 오류는 ACK 전 private response, DB 오류는 ACK 상태에 맞는 한 responder다.
생일 목록은 private empty 계약 때문에 첫 100행을 최대 2초 안에 읽은 뒤 공개성을 결정한다.
긴 목록은 100행씩 읽고 3,500자 이하 embed로 나눠 동일 공개성의 continuation을 보낸다.
새 button/select UX나 다른 기능의 pagination을 가져오지 않는다.

ranking은 합산 XP 내림차순이고 동점은 user ID 오름차순으로 고정한다. V1 SQL은 tie-breaker를
명시하지 않았으며 PHASE 3 guild index 경로의 동점 순서를 deterministic하게 명시한 것이다.
birthdays는 month/day/user 순이다. 삭제 결과는 V1 SQL rowcount처럼 **member row 존재 여부**다.
따라서 이미 birthday가 NULL인 기존 member의 삭제도 성공이며, member 자체가 없을 때 missing이다.
role/Administrator permission이 master를 대체하지 않는다.

## Birthday delivery

등록은 leap 기준 연도 2000의 실제 달력으로 검사해 Feb 29를 허용하고 Feb 30/31, Apr 31 등을
거절한다. 기존 잘못된 legacy birthday는 자동 수정·삭제하지 않는다. 목록에서는 저장값을 보여주고
알림에서는 유효한 날짜만 고른다. Feb 29는 윤년 Feb 29, 비윤년 Feb 28에 알린다.

guild/channel tuple은 immutable config다. Discord adapter는 실제 TextChannel의 guild까지
대조하며 다른 guild 채널에 보내지 않는다. KST 09:00 전에는 알리지 않고, 시작 시각이 09:00
직전이면 정확한 남은 초만 기다린다. 이후 60초 단위로 확인한다. 09:00 이후 기동은 **그날만**
catch-up하며 지나간 날짜의 알림을 backfill하지 않는다.

조회가 성공한 뒤 `(guild, date)`를 durable claim하고 send를 시작한다. empty day도 처리 완료로
기록한다. 마지막 처리일 이하의 중복/역행 날짜는 다시 보내지 않는다. 정상 send 뒤 `sent`,
전송 오류 뒤 `uncertain`을 기록한다. send/후속 DB ACK가 취소되면 `claimed`가 남을 수 있다.

SQLite commit과 Discord send를 하나의 원자적 transaction으로 묶을 수 없다. 따라서 외부 전송은
**at-most-once attempt**다. claim 이후 crash/timeout/연결 오류/부분 전송은 알림 누락 가능성이
있으며 같은 날 자동 재전송하지 않는다. claim 전 DB 실패는 다음 tick에 안전하게 재시도한다.
동일 날짜의 성공 전송을 crash 뒤 반복하는 것처럼 exactly-once라고 과장하지 않는다.

Scheduler는 PHASE 2 TaskSupervisor 전용 capacity 2/history 8을 사용한다. 일반적으로 task 1개,
1시간 lease 갱신 때 최대 2개다. 각 task deadline은 7,200초이며 같은 on_ready의 중복 start는
무해하다. 반복 실패를 무한 restart하지 않고 typed code/observation에 남긴다. 생성 시 task는 없고
Discord ready 이후 시작하며 stop에 취소·회수한다. send deadline은 config request timeout이다.

## Additive data and rollback

Migration 1/2 정의와 checksum은 바꾸지 않았다. 새 version 3 `engagement-event-ownership`은
`v2_engagement_runtime/events/voice/birthday` 네 metadata table과 expiry index만 추가한다.
six-table legacy schema/SQL envelope/사용자 PK 의미는 유지한다. schema와 ledger는 startup에서
검사만 하며 feature 시작은 version 3인 **명시적으로 준비한 DB 사본**을 요구한다.

PHASE 3 verified-copy migration과 full encrypted backup/restore를 그대로 사용한다. legacy 값과
별도로 metadata checksum도 비교해 dedupe/daily claim/voice state가 snapshot에서 빠지지 않게 한다.
복원 시 populated index를 생성하는 SQLite REINDEX authorization은 네 approved index 이름으로
한정했다. arbitrary function/ATTACH/PRAGMA/unknown table 허용으로 넓히지 않았다.

V1 reader는 추가 table을 무시하고 기존 데이터에 접근한다. PHASE 3 V2 binary 자체는 알 수 없는
version 3을 fail-closed하므로 데이터 rollback reader는 V1이지 옛 V2 validation binary가 아니다.
코드 revert는 Discord wiring → application/persistence 순서다. metadata down-migration이나
원본 data 되돌리기를 자동 수행하지 않는다. production migration/cutover는 여전히 PHASE 10 gate다.

## Evidence and discrepancies

| 관찰 | 문서/예상과의 관계 | 처리 |
| --- | --- | --- |
| 진입 suite 282 passed, 12 xfailed | PHASE 3 보고와 동일 | 차이 없음 |
| `/랭킹`은 공개성 옵션만 존재 | 사용자 예상 목록에 text/voice 선택 검토 포함 | 기존 합산 TOP 10/signature 보존 |
| V1 동점 SQL에 명시적 secondary order 없음 | tie handling 보존 요구 | 기존 guild index의 user-order를 명시하고 synthetic tie test 추가 |
| birthday 삭제는 birthday 유무 아닌 member rowcount | 문구는 등록된 생일 없음처럼 보임 | 기존 반환 의미 보존, test로 고정 |
| SDK import가 Windows OS probe를 실행 | import-side-effect 금지 | lazy explicit SDK construction으로 교정, 기존 검사 유지 |
| populated migration index SQL restore에 REINDEX authorization 필요 | 기존 backup 테스트는 이 조합을 놓침 | 좁은 허용 목록과 실제 metadata roundtrip test 추가 |

자동 증거는 `tests/integration/engagement/`, 전환된 PHASE 4 characterization 3개와 architecture
suite다. CF-17/18/19/20/21을 synthetic DB, fake clock, barrier와 fake Discord send로 검증한다.
실제 보관 DB는 이번 Phase에서 열거나 복사하거나 hash를 읽지 않았다.
