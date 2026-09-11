# PHASE 7 report

작성: 2026-09-11. 작업 branch: `codex/rebuild-v2`. 범위: Music migration only.

## Phase 7 Complete

Music F011–F028/F045 구현과 PHASE 7 CORRECT 두 항목을 실제 V2 경로로 이전했다.
전체 strict test와 Music CORRECT/호환성 검증을 완료했다. V1 운영 runtime은 유지한다.

## Implemented

guild MusicActor, typed ports, SQLite start receipts, lazy Discord UI/runtime, bounded child
process/media/TTS cache, legacy-compatible atomic checkpoint와 partial guild restore를 추가했다.
[Music contract](music-contract.md), [Actor contract](music-actor-contract.md),
[Media/cache contract](media-cache-contract.md)가 구현 경계와 상한을 정의한다.

## Tests

- 진입 기준선: **504 passed, 2 xfailed**, 21.16초. PHASE 6 완료 기준과 일치했다.
- 중간 전체 strict 검증: **588 passed, 0 xfailed**, 23.04초.
- 최종 전체 strict 검증: **592 passed, 0 xfailed**, 22.05초.
- 최신 Music 전용 검증: **85 passed**, 2.25초.
- 주요 actor/cache/snapshot/Discord lifecycle/local FFmpeg **17개 × 100회 = 1700 passed**,
  149.76초. barrier/fake clock/event와 실제 local child를 사용했다.
- paused TTS checkpoint 보강 뒤 관련 **4개 × 100회 = 400 passed**, 57.87초.
- favorite partial/cancel 관련 **2개 × 100회 = 200 passed**, 76.69초.
  세 반복 실행의 합계는 **2300 passed**다. 이는 일반 suite의 test 수와 별도로 집계했다.
- Characterization PRESERVE **32개 함수의 AST 동일**. migration 1–4 AST와 Engagement/Watch
  DDL 정의 동일. 변경한 CORRECT spec 두 개는 V2 actor restore와 V2 paginated UI를 호출한다.

명령은 `.venv\Scripts\python.exe -m pytest tests/ -q -W error::RuntimeWarning
-W error::pytest.PytestUnraisableExceptionWarning`이며 `PYTHON_DOTENV_DISABLED=1`을 사용했다.
반복은 선택한 node ID를 같은 strict 옵션으로 100회 실행했다. 실제 `.env`, production DB,
music_state.json이나 외부 API를 사용하지 않았다. 기존 discord.py `audioop` deprecation 외
RuntimeWarning/PytestUnraisableExceptionWarning는 허용하지 않았다.

## Architecture Check

별도 architecture suite: **14 passed**, 0.78초.

layer/vendor/SQLite boundary, TaskSupervisor 이외 raw task 금지, BoundedExecutor 이외 dispatch
금지, fresh-process import side-effect 금지와 Watch process isolation 검사를 유지했다.
composition은 Music adapter만 참조한다. 파일 publish 결과 소유권을 위한 executor의
`run_retained`만 추가했고 기존 `run`의 cancellation test도 통과했다.

## MusicActor / Ownership

guild별 queue/current/session/attempt/preparation/retry/loop/autoplay/volume/voice intent와
revision을 한 mailbox가 변경한다. 기본 public 64 + internal reserve 16, queue 500,
lookup 8, TTS queue 4, actor 최대 4다. stale work/selection/callback은 identity로 거부한다.

## Commands / Dashboard

required `/재생 검색어`, private defer, designated music channel과 public URL-message 경로를
연결했다. 25-option pagination은 모든 보관 item을 stable ID로 접근하게 한다. player/search/
queue/favorite controls, guild/user/expiry, clear confirmation과 단일 responder를 검증했다.
ready storm은 coalesce하며 deleted dashboard는 재생성한다. refresh 실패는 Music health reason이다.

## Voice Lifecycle

requester/master와 cross-guild denial, 같은 guild requester 채널 이동, 8초 reconnect와 2초
empty grace를 보존했다. pause elapsed와 reconnect/TTS 후 같은 logical session을 유지한다.
Discord 실제 권한·네트워크 복귀 품질은 staging에 남긴다.

## Media Acquisition / FFmpeg

yt-dlp metadata/download와 gTTS는 child adapter에 격리했다. process pool 2+4, metadata 1 MiB,
playlist 50, 첫 PCM 확인, PCM buffer, timeout과 terminate/kill/reap을 구현했다. 정상/비정상 exit,
hang/cancel/즉시 stop/start failure/empty audio를 local fake child로 검증했다. direct rollback
fallback은 명시적 만료 시각이 있는 경우에만 최대 7일 제공한다.

## Queue / Playback / Loop

stable ID move/remove/shuffle/clear, stale revision, duplicate title, simultaneous skip/after,
preparation skip과 pending retry 취소를 검증했다. NONE/SONG/QUEUE cycle과 track-end,
3초/8초/세 번째 실패 skip, pause/resume elapsed를 유지했다.

## Autoplay

uploader/featured artist 조회, title normalization/history 20, duration/dedup과 후보 선택을
구현했다. 성공과 provider failure/capacity/timeout, manual enqueue/toggle/leave 뒤 stale result를
actor token으로 처리한다. V1의 provider symbol 실패나 unbounded retry를 복제하지 않았다.

## Favorites / Play Count

favorites는 user-global repository이고 play count는 guild별이다. 첫 PCM 이후 시작한 session의
receipt+legacy counter가 atomic하다. retry/TTS/resume/reconnect/중복 callback/restart의 같은
session ID는 중복 count되지 않는다. temporary SQLite 동시 start와 encrypted backup/restore를 검증했다.

## Join TTS

enabled/disabled, generation 실패/timeout, 1.5초 bot join delay, 재생 중 interrupt/resume와
skip/track-complete 경합을 검증했다. TTS도 같은 cache budget과 하나의 audio owner를 사용한다.
일시정지 중 TTS 또는 reconnect를 checkpoint해도 paused intent가 보존된다.

## Cache

process-global 256 MiB/128 items/32 MiB item/24시간 TTL, in-use lease, atomic publish와 checksum을
적용했다. oversize는 write 전에 거부한다. disk-full/permission/partial/cancel/same-key race와
취소 중 publish 결과 회수는 synthetic 테스트다. Pi 실측값 또는 확정 SLO로 표현하지 않는다.

## Snapshot / Restore

legacy 8개 field와 song field를 유지하며 `_v2` version/revision/checksum/session/paused를
추가했다. 실제 V1 restorer의 rollback reading test가 있다. read로 source를 지우지 않으며
actor ACK 후 원자 checkpoint로 교체한다. malformed/changed/stale source와 partial guild failure는
원본을 유지한다. 저장된 volume 우선, 누락 0.5와 nullable thumbnail도 검증했다.

## Concurrency / Failure Check

| PHASE 1 scenario | 실행 근거 (`tests/integration/music/`) |
| --- | --- |
| CF-01 play/enqueue/skip | `test_actor.py`: FIFO request, preparation skip, duplicate skip |
| CF-02 callback/failure/count | `test_actor.py`, `test_lifecycle.py`: attempt dedupe, PCM startup, old callback |
| CF-03 retry/cancel | `test_actor.py`, `test_failures.py`: 3/8 clock, skip/leave/close |
| CF-04 autoplay/manual | `test_actor.py`, `test_failures.py`: late result, local failure/capacity |
| CF-05 TTS/end/skip | `test_actor.py`, `test_failures.py`: same session and paused checkpoint |
| CF-06 snapshot mutation/crash | `test_resources.py`, `test_failures.py`: atomic replace, revision, ACK |
| CF-15 disk/process failure | `test_resources.py`, `test_failures.py`, `test_lifecycle.py`: bounded bytes, cleanup/reap |
| CF-16 ready/reconnect | `test_lifecycle.py`: actor/dashboard coalescing, deleted message |
| CF-19 responder | `test_discord.py`: pre/post-defer dependency failure, concurrent response |
| CF-20 shutdown | `test_lifecycle.py`, `test_failures.py`: pending work, local children, leases |
| CF-21 guild/global data | `test_data.py`, `test_actor.py`: isolated runtime/count and user-global favorites |

## Data Compatibility

additive migration **5**의 `v2_music_starts`만 추가했다. 기존 six-table schema와 migration 1–4
checksum 정의는 그대로다. backup validation에 새 metadata를 포함했다. 새 DB 생성은 기존
explicit recovery/bootstrap 경계 밖에서 실행하지 않는다. 모든 DB/SQL test는 temporary path다.

## Pi Impact

Pi 접근·측정·systemd/cron/서비스 재시작·deployment/Cloudflare 변경 없음.
`docs/rebuild/bot_database.db`와 실제 music_state.json을 open/read/hash/copy/modify하지 않았다.
실제 Discord/Voice/YouTube/Gemini/gTTS network 실행이나 package 설치·upgrade도 없다.

## Compatibility

V1 runtime 및 PHASE 0–6 산출물은 유지했다. F011–F028/F045의 PRESERVE는 기존 tests와
추가 V2 tests로 확인했다. cosmetic dashboard rendering은 current Q-H01의 best-effort 범위이며
control 의미/visibility와 저장 호환성을 우선했다.

## Corrected Legacy Bugs

다중 writer와 stale callback에 의한 advance, retry/TTS count 중복, 불능 autoplay,
25개 이후 selection 유실, missing-volume 1.0 경로, ACK 전 snapshot 소비,
unbounded cache/process와 interruption 중 paused intent 유실을 교정했다.

## Documentation Updated

PHASE 7의 네 contract/report, current plan/trace/ADR, rebuild index, README와 CHANGELOG를 갱신했다.
frozen baseline과 과거 Phase 보고서는 수정하지 않았다.

## Remaining Risks

실제 provider/Discord Voice·권한, Pi CPU/RSS/disk/장시간 soak는 미검증이다. hard kill이 audio
start와 DB commit 사이에 끼는 관측 공백 및 coarse checkpoint 이후의 최종 위치/전이는
원자적 외부 transaction으로 보장할 수 없다. 같은 session으로 재개하면 receipt가 수렴한다.
kernel/filesystem이 정리 자체를 완료하지 않는 장애에서는 process/file owner를 숨기지 않고
실패로 남긴다. cache/queue/UI ceiling과 실제 shutdown latency는 PHASE 9에서 측정해야 한다.

## Next Phase Gate

PHASE 7 완료 뒤 **PHASE 8은 자동 시작하지 않는다**. 사용자 지시를 기다린다.
운영 데이터 migration/cutover는 PHASE 10의 별도 승인 gate다. push/PR/deploy는 수행하지 않았다.

## Decision Required

이번 Music migration을 위한 새 결정 요청은 없다. staging/cutover 시 direct fallback 종료 시각,
실제 configured guild/channel과 Pi ceiling을 별도로 확인한다. 이번 Phase에서 운영값을 적용하지 않았다.

## Commit / rollback

| Commit | 책임 |
| --- | --- |
| `15b6ed9` | atomic filesystem 결과 소유권과 executor test |
| `5a0a86e` | migration 5와 idempotent start receipts/data compatibility |
| `f9cf9c8` | single-owner MusicActor와 상태/복원 계약 |
| `a06c4a0` | media/cache/process/snapshot adapters와 실패 test |
| `10dce6e` | Discord commands/UI/composition/lifecycle |
| `7250979` | interruption checkpoint의 paused intent 보강 |
| `b7e6922` | favorite partial batch 전체 deadline과 cancelled result 거부 |

문서 완료 commit은 `docs: complete V2 phase 7 Music migration`이다. 모든 commit 전 staged diff와
`git diff --cached --check`를 확인했다. rollback은 UI wiring부터 의존성 역순으로 revert하고
변경하지 않은 V1 runtime을 사용한다. migration 5를 적용한 운영 DB를 자동 down-migrate하지
않는다. 이전 V2 validator가 필요하면 승인된 사전 사본 복구 절차를 사용해야 하며 V1 reader는
추가 metadata를 무시할 수 있다. 실제 데이터 rollback 실행은 이번 Phase에 없다.
