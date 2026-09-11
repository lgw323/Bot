# PHASE 7 Music contract

2026-09-11. F011–F028/F045. Source priority는 사용자 PHASE 7 지시, current 결정,
승인된 FR/BR, PHASE 1 계약 순이다. V1 운영 경로는 그대로 유지한다.

## PRESERVE

- `/재생 검색어:string`은 required다. private defer 뒤 지정 음악 채널을 확인한다.
  URL은 바로 추가하고 검색어는 `ytsearch3:` 결과 선택으로 연결한다. 원래 명령 설명,
  모달 제목·입력 label, player 버튼 순서와 `q_move_top`/`q_remove`를 보존한다.
- 음악 채널 URL 메시지는 조회 전에 삭제를 시도한다. 삭제 실패 횟수를 관찰하며 요청은
  계속 처리한다. 메시지 경로의 결과는 공개, slash/modal 결과는 비공개다.
- 일반 사용자는 음성 채널에 있어야 하며 자신이 들어간 같은 guild의 채널로 봇을 이동시킬 수
  있다. master는 봇이 이미 연결된 경우에만 음성 참여 없이 요청할 수 있다. 다른 guild의
  채널로 이동할 수 없다. 별도 방장/role 조건을 추가하지 않는다.
- playlist는 원래 순서의 최대 50개 entry를 처리한다. null/malformed entry는 건너뛴다.
  50개 이후를 무제한 확장하지 않는다. empty/provider failure는 기존 안내 계열로 응답한다.
- 실패 시 첫 3초, 두 번째 8초 후 다시 준비하고 세 번째 실패에서 다음 곡으로 이동한다.
  pause는 elapsed를 고정하고 resume는 같은 세션의 재생 시간을 이어간다.
- loop enum은 `NONE=0 → SONG=1 → QUEUE=2 → NONE`다. 정상 완료 시 SONG은 같은 곡을,
  QUEUE는 끝에 돌려놓은 곡까지 이어 재생한다. 수동 skip은 현재 attempt를 무효화한다.
  QUEUE에서 실제 재생/일시정지 중 skip한 곡은 순환 목록 끝에 남는다.
- 연결 단절 후 8초 재접속 유예, 빈 채널 2초 재확인을 유지한다. 새 멤버/이동/재접속은
  오래된 timer를 취소한다. 봇 입장 TTS는 1.5초 뒤, 멤버 이름은 10자 이후 `...`로 줄인다.
- favorites는 user-global이고 popular songs/count는 guild별이다. 순위는 count 내림차순,
  동률은 URL 순이다. 새 volume UI는 없고 저장 값 우선, 누락 시 0.5다.
- snapshot의 legacy 8개 field와 song 6개 field, nullable thumbnail을 보존한다.
  V2가 작성한 파일을 실제 V1 restorer가 current→queue 순서로 읽는 synthetic test가 있다.

## CORRECT

queue/current/attempt를 수정하는 writer는 guild MusicActor 하나다. Voice callback, provider 결과,
retry와 TTS는 mailbox로 돌아오며 취소만 믿지 않고 work token/session/attempt를 확인한다.
동시 skip·중복 callback이 다음 곡을 또 건너뛰지 않는다. preparation/빈 FFmpeg 출력은
play count를 증가시키지 않는다. 첫 PCM frame 확인 뒤 VoiceClient가 재생을 받아들인 논리적
session의 start receipt와 count를 한 DB transaction으로 기록한다. retry/TTS/reconnect/복원은
같은 session ID를 유지한다.

검색·queue·favorites의 25-option 제한은 stable item ID와 이전/다음 페이지로 처리한다.
사용자/guild/만료 검증 뒤 선택한 곡에만 적용하며 queue index를 identity로 사용하지 않는다.
즐겨찾기 추가 batch는 전체 60초 이내에 성공한 entry를 순서대로 반영하고 개별 provider 실패는 건너뛴다.
취소된 lookup 결과는 뒤늦게 enqueue하지 않는다. 검색 선택은 한 번 소비한다. clear confirmation은 30초와 revision을 확인한다.
favorites 한 view의 hard ceiling은 1,000개, 한 추가/삭제 요청은 50개다. 초과는 명시적으로
거부하며 기존 데이터를 삭제하거나 첫 25개만 접근 가능하게 만들지 않는다.

autoplay는 uploader 또는 30%의 featured artist 검색, 정규화한 최근 title 20개와 URL 중복
필터, 90초 초과·600초 미만 조건을 사용한다. 성공 후보에서 선택하며 provider 실패는
Music capability 안에서 끝난다. 수동 요청/toggle/leave 후 늦은 결과는 폐기한다.

## Discord lifecycle

`MusicResource`는 DB repository, cache/snapshot 경로와 guild→channel 설정을 명시적으로 받는다.
DB 준비가 끝난 resource 뒤에서 시작해야 한다. constructor/import는 Gateway나 DB를 열지 않는다.
Discord composition의 optional `music` 인자로 연결할 수 있으며 `main_bot.py`에는 연결하지 않았다.

dashboard는 projection이다. reconnect/ready storm은 하나의 actor와 guild별 dashboard로
수렴한다. 250ms coalescing과 10초 periodic checkpoint/refresh를 사용한다. 음악 시작 때의
채널 정리와 초기 bot 메시지 정리를 구분하며 elapsed refresh마다 purge하지 않는다.
실패는 payload 없이 고정된 health reason과 supervisor observation으로 남긴다.

## Evidence and staging

`tests/integration/music/test_actor.py`, `test_discord.py`, `test_lifecycle.py`, `test_data.py`,
`test_failures.py`, `test_resources.py`와 PHASE 1 PRESERVE/CORRECT tests를 참조한다.
실제 Discord 권한/Voice 품질, provider 응답 변화, Pi CPU/RSS/disk와 장시간 soak는 아직
실행하지 않았다. [Actor contract](music-actor-contract.md), [cache contract](media-cache-contract.md),
[report](phase-7-report.md)에 구현 한계와 실행 증거를 기록한다.
