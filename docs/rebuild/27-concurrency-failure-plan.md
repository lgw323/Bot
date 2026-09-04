# 27. Concurrency and Failure Test Plan

## Test method

모든 scenario는 production data/network 없이 fake clock, deterministic scheduler barrier,
fake repository/provider/voice/WebSocket과 bounded temporary filesystem으로 실행한다. 단순
`sleep` 기반 우연한 순서 검증은 staging E2E를 제외하고 사용하지 않는다. 각 test는 owner,
correlation ID, deadline, cancellation과 종료 후 남은 task/subprocess/file을 검증한다.

| ID | Feature / requirement | Deterministic trigger | Required invariant | Planned phase |
| --- | --- | --- | --- | --- |
| CF-01 | F012/F020/F022, FR-016/017 | play enqueue와 skip을 barrier에서 동시 release | guild owner가 한 순서만 commit; 곡 유실·중복·wrong-target 없음 | 7 |
| CF-02 | F018/F026, FR-015/022 | FFmpeg `after`와 preparation failure를 같은 revision에 전달 | retry 1회, play count 최대 1회, next signal 중복 무해 | 7 |
| CF-03 | F018/F020, FR-015/016 | 3초/8초 retry wait 중 skip/cancel | timer 즉시 취소, retry song 제거, late wakeup이 재생하지 않음 | 7 |
| CF-04 | F024, FR-018/019 | autoplay lookup 중 manual enqueue/toggle off | stale result reject, manual queue order 유지, task/permit 회수 | 7 |
| CF-05 | F027, FR-023 | join TTS, track completion, skip을 barrier에서 교차 | 한 audio owner, resume/skip 결정 1회, play count 중복 없음 | 7 |
| CF-06 | F028, FR-024 | queue mutation 중 checkpoint와 process kill | atomic last-good snapshot, monotonic revision, partial file reject | 7 |
| CF-07 | F001/F005, FR-001/046 | DB busy lock, timeout, cancellation | command deadline 내 typed failure; global event loop와 read path 생존 | 3 |
| CF-08 | F008, FR-030 | Summary 6개 동시 요청, 첫 provider barrier hold | active 1, waiting 4, 여섯째 overload, FIFO/cancel permit 회수 | 5 |
| CF-09 | F008, FR-030 | Gemini connect/read/total timeout과 cancel | 한 요청만 종료, raw content 미로그, Music/XP probe latency 정상 | 5 |
| CF-10 | F039, NFR-015 | 한 WS peer send를 영구 block, 다른 peer 정상 | slow peer timeout/disconnect, 나머지 relay p95와 actor 진행 유지 | 6 |
| CF-11 | F041, FR-042 | 5초 empty deadline 직전 reconnect와 직후 disconnect | reconnect가 old timer cancel; revision이 다른 timer는 session 삭제 불가 | 6 |
| CF-12 | F040/F042, FR-040/043 | playlist add, connect와 master close 동시 | close idempotent, closed session에 item/socket 잔류 없음 | 6 |
| CF-13 | F043, FR-044 | startup stale cleanup과 browser admission barrier 경합 | readiness 전 cleanup 완료; 새 active session 오삭제 없음 | 6 |
| CF-14 | F005, FR-045–047 | continuous DB writes 중 online backup | source/dump integrity, consistent transaction point, writer bounded wait | 3/8 |
| CF-15 | F017/F028, FR-014/024 | disk full/permission/partial media와 snapshot write | last-good 보존, partial cleanup, subprocess terminate/reap, typed UX | 7 |
| CF-16 | F001/F002/F006/F011/F043, FR-008 | `on_ready` 3회와 reconnect storm | handler/task/dashboard/preload/cleanup exactly-once 또는 idempotent | 2/5/6/7 |
| CF-17 | F030, FR-032 | mute↔unmute, move, leave, shutdown 정산을 같은 fake time에 교차 | `(guild,user)` session 1개, 유효 초 중복·누락 없음 | 4 |
| CF-18 | F036, FR-035/037 | KST midnight/year/leap boundary와 duplicate scheduler fire | guild/date idempotency, non-leap Feb-29→Feb-28 exactly once | 4 |
| CF-19 | F003/F008/F037, FR-004/010 | defer 직전/직후 dependency failure | response/defer/followup 중 legal path 정확히 1개 | 2/4–7 |
| CF-20 | all, FR-009 | shutdown 중 queued DB/Gemini/media/WS work | admission stop→bounded drain/cancel→flush→close, 10초 내 orphan 0 | 2–8 |
| CF-21 | F025/F026/F029–F036, FR-006 | 두 guild에 같은 user ID와 동시 writes | guild-scoped data 격리, favorite만 user-global | 3/4/7 |
| CF-22 | F002/F005, NFR-008/024 | log/backup failure storm | bounded buffer/drop metric/dedupe, command loop 비차단, false success 없음 | 2/8 |

## Stage gates

1. Unit/integration gate: fake dependency와 virtual clock으로 동일 seed 100회 반복 시 순서와
   invariant가 같다.
2. Process gate: child process kill, FFmpeg/yt-dlp terminate/reap, corrupt/partial filesystem을
   임시 경로에서 검증한다.
3. Staging gate: 전용 Discord application/guild와 sanitized data로 voice, interaction,
   browser, new Watch tunnel을 검증한다.
4. Clean Pi gate: Raspberry Pi 5, Ubuntu Server 24.04 LTS ARM64, Ethernet/LAN에서 idle,
   peak×2, fault와 최소 24시간 soak를 측정한다. WordPress/CloudPanel은 설치하지 않는다.
5. Production gate: 이 계획만으로 DB migration/cutover 권한이 생기지 않는다. PHASE 10의
   별도 사용자 승인, final verified backup/restore/reconciliation이 필요하다.
