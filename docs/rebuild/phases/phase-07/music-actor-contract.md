# PHASE 7 MusicActor ownership

2026-09-11. Domain DTO는 immutable이며 Discord/yt-dlp/SQLite type을 포함하지 않는다.

## Authoritative owner

guild당 MusicActor 하나가 queue/current/session/attempt/preparation/retry, loop/autoplay,
pause/elapsed, voice intent, volume, revision과 restore identity를 소유한다. UI는 projection과
stable 선택만 가진다. queue ID, logical session ID, attempt ID, work token은 서로 다른 개념이다.
mailbox 순서가 사용자 요청의 적용 순서이고 provider lookup은 guild별 FIFO다.

mailbox pump는 비어 있으면 종료한다. 긴 media/provider/TTS 작업은 supervised work가 실행하고
결과 command만 반환한다. `TaskSupervisor` 이외의 task 생성 경로는 추가하지 않았다.
cancelled task가 결과를 돌려줘도 token이 다르면 cache lease를 반납한다. Audio adapter는
별도 control lock으로 늦은 process startup과 stop이 새 process를 덮어쓰지 못하게 한다.

## Initial hard ceilings

| 항목 | 상한/기본값 | 거부·처리 |
| --- | ---: | --- |
| MusicActor / configured guild | 4 | admission 거부 |
| public mailbox / guild | 64 | CapacityError |
| 내부 결과/callback/close 여유 | 16 | 전체 mailbox 최대 80; 중복 end coalescing |
| queue / guild | 500 | 원자적으로 초과 enqueue 거부 |
| provider 요청 / guild | 8 | FIFO, 초과 거부 |
| TTS 대기 / guild | 4 | 초과 거부; generation 한 개 |
| Music supervisor | 96 active / 256 observations | 다른 feature supervisor와 분리 |
| selection/modal view | 32 | 180초 expiry, clear 30초 |
| snapshot guild / file | 4 / 4 MiB | 실패한 원본 보존 |
| dashboard/checkpoint pump | process당 1 | guild별 최신 projection coalesce |
| periodic checkpoint | 10초 | 실제 SLO 아님 |

수치는 PHASE 9 Pi 측정 전 보수적인 ceiling이다. 변경 가능한 Bounds도 검증된 최대값을
넘을 수 없다. executor는 Phase 2의 주입된 bounded executor이며 파일의 atomic publish/open/close는
`run_retained`로 결과 소유권을 넘긴 후 정리한다. 보통 executor `run`의 취소 의미는 그대로다.

## Transitions and failure

- preparation → first PCM/voice start → playing. start receipt는 실제 시작 뒤만 기록한다.
  duplicate start/DB 재시도는 `(guild_id, session_id)` receipt로 무해하다.
- retry는 같은 logical session의 새 attempt다. 3초/8초 clock은 fake sleeper로 검증한다.
  중복 failure는 한 번만 반영하며 skip/leave 뒤 timer는 효과가 없다.
- TTS는 기존 음악 위치와 paused intent를 저장하고 audio owner를 잠시 사용한다. 끝나면 같은
  logical session을 재개한다. TTS 중 checkpoint도 paused intent를 별도로 보존한다.
- disconnect는 위치를 저장하고 8초 timer를 시작한다. reconnect는 timer를 취소하고 같은
  session을 준비한다. empty는 2초 뒤 여전히 유효한 timer만 leave를 실행한다.
- close는 admission을 닫고 jobs를 취소하고 audio/process/leases를 정리한다. 늦은 command는
  ShutdownError다. runtime은 actor close 전에 마지막 projection을 checkpoint한다.

## Snapshot protocol

legacy guild record에 `_v2` metadata(version 2, revision, checksum, identity, session ID,
paused)를 추가한다. legacy 8개 field 자체는 변경하지 않는다. checksum은 legacy state와
metadata를 함께 검증한다. temp write → flush/fsync → replace만 publish한다.

restore는 read로 source를 지우지 않는다. guild별 검증·actor ACK·필요한 voice 연결 후
동일 source를 새 checkpoint로 원자 교체한다. 따라서 runtime에는 ACK와 delete 사이의
파일 공백이 없다. 별도 one-shot 소비용 `acknowledge`도 source identity가 바뀌면 거부한다.
실패 guild는 source를 그대로 두고 admission을 막으며 정상 guild의 복원은 진행한다.
새 schema나 실제 데이터 bootstrap을 자동 실행하지 않는다.

## Failure observability and limits

supervisor에는 owner/name/work identity/deadline/cancellation/result가 보인다. actor/runtime
error에는 고정된 reason만 남긴다. URL, 제목, TTS 원문, 사용자 ID를 operation name이나
exception diagnostic log로 출력하지 않는다.

실제 오디오 전송과 SQLite는 하나의 distributed transaction이 아니다. hard kill이 시작/DB
commit 사이에 끼면 시작 여부의 관측 공백이 있을 수 있다. 복원된 logical session을 다시
시작할 때 동일 receipt로 수렴하며 성공 ACK 없는 상태를 성공했다고 보고하지 않는다.
coarse checkpoint 이후의 최종 위치/전이는 전원 장애에서 잃을 수 있다. Pi 전원·filesystem
stall·network Voice soak는 staging/PHASE 9에서 검증해야 한다.
