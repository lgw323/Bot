# PHASE 7 media, subprocess and cache contract

2026-09-11. 자동 test는 synthetic 파일과 `sys.executable -c` local child만 실행했다.
yt-dlp/gTTS/FFmpeg 실제 network 실행과 system package 설치는 하지 않았다.

## Operation budgets

| 작업 | concurrency / waiting | deadline | bytes / retry |
| --- | --- | --- | --- |
| provider child pool | process-global 2 / 4 | lookup 30초 | stdout/stderr 각각 1 MiB; provider retry 1 |
| playlist metadata | 같은 pool; guild FIFO | 30초 | flat metadata 최대 50 entries |
| media download | cache owner 1 / waiting 8 | child 60초, actor acquire 전체 90초 | item 32 MiB; retry/fragment retry 1 |
| gTTS | 같은 cache/pool | 20초 | 입력 200자; 같은 item cap; 자동 재시도 없음 |
| direct compatibility | 같은 pool | lookup 25초 | stream URL validation; 명시적 종료 시각 ≤7일 |
| FFmpeg decoder | 최대 active guild 4 / waiting 0 | 첫 frame 5초, frame read 30초, task 24시간 | PCM queue 100×3,840 bytes/guild; stderr 64 KiB |
| process stop | owner 유지 | terminate 1초 뒤 kill, reap 1초 | 실패하면 typed error, reaped로 허위 처리하지 않음 |

yt-dlp는 import되지 않는 child CLI boundary다. provider-specific JSON은 adapter에서 Track으로
검증·변환한다. parent가 child stdout을 bounded chunk로 받아 한도를 **넘기기 전에** 파일
쓰기를 거부한다. vendor의 filesize 옵션만 신뢰하지 않는다. 실제 audio가 없는 decoder는
VoiceClient.play와 play count 단계로 들어가지 않는다.

direct fallback은 승인된 rollback 기간용 선택 기능이다. constructor에 만료 시각을 명시해야
하며 기본 비활성이다. YouTube input과 HTTPS googlevideo stream을 검증하고 만료 뒤 사용하지
않는다. 운영 cutover 날짜나 환경변수를 이번 Phase에서 활성화하지 않았다.

## Global disk ownership

MusicResource 하나가 media와 TTS를 합쳐 **256 MiB / 128 items / item 32 MiB / TTL 24시간**
budget을 소유한다. guild별로 같은 budget을 중복 생성하지 않는다. 같은 key의 acquisition은
한 writer로 직렬화하고 완성된 파일은 최대 32개의 고유 lease로 공유한다. 중복 release는
다른 재생의 pin을 감소시키지 않는다.

시작 전에 worst-case item bytes를 확보한다. in-use entry는 eviction하지 않는다. LRU/TTL
정리로도 여유가 없으면 거부한다. `.part`는 유효 entry로 보이지 않으며 hash를 포함한 `.blob`
이름으로 fsync/replace한 뒤 index에 등록한다. hit 시 size/checksum을 재검증하고 손상된
unpinned entry는 재취득한다. startup은 이 전용 디렉터리의 알려진 partial만 정리한다.

파일 작업 취소는 한 번의 bounded atomic file operation이 결과를 넘길 때까지 보류한다.
그 결과가 늦게 도착하면 actor token 검증을 통해 lease를 반납한다. 디스크 full/permission,
oversize/empty output, 실패·취소 partial, 동일 key 경합, pinned eviction, publish 중 취소를
synthetic fixture로 확인했다. 다른 feature나 실제 데이터 디렉터리는 사용하지 않는다.

## Cleanup and remaining measurement

decoder/pipe/pool은 supervisor와 process owner가 추적하며 skip/leave/disconnect/shutdown에서
terminate/kill/wait한다. discord.py가 본래 소유하는 AudioPlayer thread만 PCM source를 읽는다.
feature가 thread/executor를 새로 만들지 않는다. cache cleanup과 checkpoint는 bounded runtime
tick으로 관리한다.

위 상한은 Pi 실측 SLO가 아니다. decoder 품질, provider 호환성, 외부 인증/쿠키 정책, 장시간
CPU/RSS/disk 사용, kernel이 kill/wait 또는 filesystem 작업을 완료하지 못하는 장애는
실제 운영 환경에서 추가 확인해야 한다. 이 Phase 결과는 배포/운영 안전성 인증이 아니다.
