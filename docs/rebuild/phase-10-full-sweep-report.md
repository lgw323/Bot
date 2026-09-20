# PHASE 10B Full-Sweep Report

이 문서는 bounded full-sweep 정책·검증·실행·실패·수정·재시도의 상세 근거를 관리하는 기준 보고서다.
[PHASE 10 부모 보고서](phases/phase-10/phase-10-report.md)는 10A 준비·migration/cutover·기존 10B 이력과
전체 PHASE 10 상태를 관리한다. PHASE 10 작업을 재개할 때 두 보고서와
[current plan](current/current-plan.md)을 함께 읽으며, 각 문서의 책임 범위에서는 최상단 최신 continuation이 우선한다.
아래 두 continuation은 기존 부모 보고서에서 이동했다. 당시 판정·승인 경계·수치를 변경하지 않았다.
과거 본문의 이전 보존 이력 참조는 부모 보고서에 남아 있다. 이후 상세 full-sweep 근거는 이 파일에만 추가한다.
문서 분리는 production 상태 변경이나 새로운 runtime 활성화 승인이 아니다.

## Continuation — 실제 Chrome warm refresh FAIL → PASS / 최소 Watch 수정 (2026-09-20)

**PHASE 10B INCOMPLETE — Stage A/B 완료. 실제 설치 Chrome + 실제 YouTube iframe에서 기존 코드 FAIL,
수정 코드 PASS. Production 미활성화; 최종 Pi candidate는 아직 검증 전이다.**
사용자의 변경된 실행 전략에 따라 추가30-gate sweep 없이 로컬 synthetic Watch session으로 원인을 재현했다.
실제 독립 browser context2개 검증과 실제 TCP disconnect/reconnect도 PASS했다. Stage C Windows 최종1회
**1009 PASS /0 skip**. Pi release capacity16/16 때문에 새로운 cold archive 대상 승인이 필요하다.

### Browser fidelity / established cause

- Chrome **153.0.8010.50**, 기존 bundled Playwright/CDP 사용. 설치·runtime dependency 변경0.
  Loopback의 실제 Watch HTTP/WebSocket/actor/SQLite adapter + 임시 synthetic DB + 공개 YouTube 예제 영상.
  운영 DB/config/사용자 invite/profile을 쓰지 않았다. 외부 iframe은 mock하지 않았다.
- Exact de3 HTML로 이미 재생 중인 방을 만든 뒤 같은 context에서 warm refresh.
  **80ms `api_callback_lookup_before_registration` → 81ms WS 생성 → 84ms open/join →
  92ms authoritative playing snapshot 수신**. 이후 deadline까지 iframe0/player-ready=false;
  WebSocket OPEN, 영상/재생 상태 snapshot은 존재했다. 사용자 증상과 같은 검은 placeholder/controls 부재.
- 원인: blocking external `iframe_api`가 inline 앱의 ready callback 등록보다 먼저 실행되는 cached-load race.
  API 자체와 `YT.Player` constructor는 로드됐지만 callback을 놓쳐 **iframe을 생성하지 못했다**.
  [YouTube 공식 API 문서](https://developers.google.com/youtube/iframe_api_reference)의 ready callback 계약과
  실제 Chrome callback lookup trace를 함께 확인했다. 이 재현에서 stale revision/새 이름/session identity 손실,
  snapshot discard, YouTube error/153, CSP 차단 또는 autoplay는 최초 iframe 부재의 원인이 아니었다.
- 별도 실제 초기 선택에서 `loadVideoById` 직후 `getVideoData()`가 잠시 undefined가 되는 것도 확인했다.
  기존 harness는 항상 object를 반환해 해당 TypeError와 acknowledgement 중단을 놓쳤다.
  Runtime3곳을 optional metadata 접근으로 바꾸고 harness도 iframe acknowledgement 전 undefined를 반환한다.
- 최소 수정: API script의 **`defer`**로 앱 callback 등록을 먼저 완료; 위 metadata guard3곳.
  안전한 **`X-Watch-Client-Revision`** header에 UTF-8 template SHA256을 노출해 served asset 비교를 지원한다.
  명령/endpoint/WS schema/권한/DB schema/dependency/CSP/referrer/30s·5s grace 정책 변경0.
  Music A1·Gemini provider/model/config·writer guard는 변경하지 않았다.

### Asset identity and cache limits

| Asset | Before de3 | Fixed |
| --- | --- | --- |
| normalized HTML/template SHA256 | `77ef3491fe9d53778de6434ad7b5e1fd2f2cb6ab4976400a2154b01eed0c8a69` | `c1f1e05edc49b0a7a0563b613b62b245e01e7853bd28111ea25fee00a463949e` |
| inline application JS SHA256 | `bfbba8a23bf34c4a5328e23a5cf3a438428f3024f203aebeb55d22d048135cd1` | `e1ea7ac0e5d35f763ecf338ce240c6c8e7a86bc8d493562f06e80cd9028c8265` |

첫 접속/refresh 응답 모두 각 source hash와 일치했다. `Cache-Control: no-store`, ETag 없음,
service-worker controller 없음; app JS는 HTML inline이며 별도 static URL cache가 아니다.
새 revision header는 CSP nonce 치환 전 digest여서 nonce 변화와 구분할 수 있다.
진단용 old-template fixture도 header를 제공하지만 **기존 production de3가 이 header를 제공했다는 뜻은 아니다**.
API 외부 resource의 warm cache는 그대로 유지했다. Playwright response routing으로 cache를 끈 중간 진단은
WebSocket까지 교란해 decisive evidence에서 제외했다.
운영은 정지했으므로 **현재 Cloudflare public response/cache의 exact asset identity는 미검증**이다.
향후 승인된 public-path 시험에서 candidate hash/header와 실제 응답을 비교해야 한다.

### Real browser regression and independent participants

- 동일 already-playing-room warm refresh regression: **before FAIL → after PASS**, JS errors0.
  수정 후 실제 iframe 생성/ready/영상 확인/playing/position 복원이 완료됐다.
  별도 실제 playing-refresh sample은 client55.259s/server55.374s로 근접했다.
- 최종 집중 matrix는 playing refresh, paused refresh 및 그 위치에서 resume, 서로 독립된 Chrome context2개,
  **server unique peer2개**, 같은 영상/playing, pause/resume/seek 전파를 검증했다.
- Read-only Playwright evaluate가 user gesture를 부여해 autoplay failure를 가리는 fidelity gap도 제거했다.
  상태 관찰은 CDP `Runtime.evaluate(userGesture=false)`로 바꿨다.
  그 뒤 실제 두 번째 client autoplay-blocked를 관찰하고 server/첫 client playing authority 불변,
  사용자의 **재생 이어가기** 동작에 해당하는 explicit click으로 복구되는 것을 확인했다.
- Chrome DevTools Offline/Online은 이 환경에서 열린 WS를 끊지 않았다(OPEN/client2 유지).
  그 결과는 **RECONNECT_NOT_REPRODUCED**로 보존했으며 PASS로 세지 않았다.
- 대체로 loopback HTTP/CONNECT proxy가 두 번째 context의 **실제 TCP socket을 끊었다**.
  client2→1→2, unique peer2, 최신 playing 및 paused hydration, terminal close 이후 client0/no reconnect PASS.
  첫 context가 방을 유지해 기존5s empty-room expiry와 구분했다. JS close-event 합성은 사용하지 않았다.
- 최종 공개 경로 절차: 일반 Chrome + Incognito/독립 profile을 두 participant로 쓸 수 있다.
  서버 peer count2를 확인하고 한쪽 실제 네트워크만 잠시 차단해 playing/paused 재접속을 검사한다.
  이 세션의 proxy는 synthetic loopback 전용이다. Public용 relay가 필요하면 host 제한·TLS 비복호화·
  credential 비기록을 별도 검토해야 한다. DevTools Offline을 무조건 충분한 단절로 간주하지 않는다.
- 계측은 callback lookup/WS categories/iframe 존재와 readiness/state/position checkpoints를 제공한다.
  YouTube 내부 전체 event timeline을 모두 계측했다고 주장하지 않는다. 판정 근거는 실제 iframe/상태와
  서버 authoritative state 비교이며 production 사용자 청취 또는 public-path PASS를 대체하지 않는다.

### Verification cadence / exact source

- 집중 Watch/server 및 stopped-verifier 회귀 **119 PASS** (9.34s); RuntimeWarning/unraisable strict.
  경로를 잘못 지정한 두 명령은 test0으로 종료했으며 PASS count에 포함하지 않았다.
- Source responsibility: `6c6cde0` 이전 live 결과 docs; `e327bea` 최소 Watch 수정·회귀·opt-in browser 도구;
  **`8e9018d4b8061cde6006eee47fa4103522f77718`** 최신 canonical860f/10th preservation 검증 기준 갱신.
  최종 runtime source는8e9018d이며 이후 report/current-plan만 변경한다.
  Source ZIP SHA256 **`f58327f1ac36f8722f5fe1b5650b521e1c586cdf727699681c8a08746d995f70`**.
- Stage A/B 동안 full Windows/Pi0, production sweep0. 실제 browser PASS 이후 exact Git export에서
  Stage C Windows full strict **1009 PASS /0 skip /0 fail /0 error, 69.64s**, 정확히1회 실행했다.
  기존 Python3.12 `audioop` DeprecationWarning1은 별도 기록하며 RuntimeWarning/unraisable strict PASS.
  Pi Node-less closed skip inventory30개에 대응하는 동일 Windows testcase30개 모두 이번 XML에서 PASS 확인.
  Pi build/full strict/credential/manifest는 슬롯 승인 전 미실행.
  Candidate를 아직 `verified_not_activated`라고 부르지 않는다.
- Local runtime range26da4c2→8e9018d: 3commit/14newblob, 전 commit tree·message 및 secret/binary/운영 artifact
  audit finding0. 실제 코드/fixture 검토에서도 credential은 synthetic fixture뿐이며 운영 데이터 추가0.
  최종 report/current-plan docs-only tail을 포함한 exact HEAD 결과는 `watch-final-git-audit.json`에 기록한다.
  Remote rebuild26da4c2/main8432fdef… read-back 불변, push0. 사용자 `gpt_handoff` 파일들은 추적하지 않았다.

### Fresh stopped-host / capacity boundary

- Read-only 검사 **verified_readonly**: production/staging/ops inactive/MainPID0, boot/timers disabled,
  Python/media writer0/runtime listener0. 현재 de3 pin과 canonical860f/config41ed/10preservation,
  data/state/cache/backups/audit/config의 전체 hash·metadata가 검사 전후 불변.
- Online release16/capacity16. 현재 de3와 최신4개(de3, ECD,1014,H1-92c)는 보호된다.
  Current pointer hash `3c567010f25b7bdc91da84d33661e98a9099a718d6c16030a70719ab2a4d5e0b`;
  previous/rollback/activation pointer 및 activation.json/rollback.json 없음.
- 다음 archive 제안은 **`r-787b3178908c08ff-3dac82a792fad576`** 하나.
  현재·activation·rollback·최신4개 보호 대상 아님을 확인했고 destination 미존재/same filesystem PASS.
  Destination `/opt/discordbot/retained/releases/r-787b3178908c08ff-3dac82a792fad576`.
  Manifest `906c8bcad00c5e78f54a42dd67d2b56fc0c5022d6430c058c70dd4f1786314ad`;
  전체 byte/권한/owner/xattr/mtime/inode inventory **`1cdbe56da7cac167d2fca9e911bd794381859553cbe838279adb2aef2fc01f01`**,
  19016entries/17411files/377119764bytes. 아직 이동/삭제0.
- 이전 사용자의 cold archive 승인은 **c724라는 특정 release 하나**만 허용했다.
  이번 787의 same-filesystem atomic rename은 별도 좁은 승인 경계다. Capacity/retention 정책을 변경하거나
  무단 삭제하지 않는다. 승인 뒤에도 직전 보호 참조·inventory를 재검증하고 이동 전후 불변을 대조한다.
  해당 exact787만 rename하는 도구를 로컬에 준비·검토했으며 아직 Pi에 전송/실행하지 않았다.
  새 보관본뿐 아니라 기존 retained c724 전체 inventory도 이동 전후 대조한다.
- 새 pin activation/push/30-gate/finalization 승인 요청은 **Pi 후보 검증까지 끝난 뒤**로 남긴다.
  그때 actual public asset identity와 PC Chrome 검사도 포함해야 한다. Stage C를 반복해서 돌리지 않는다.
  운영 활성 중 auxiliary Python poll 금지; 이미 승인된 observer output을 cat/SCP로만 읽는다.
  Canonical old restore/replay/migration0, production start0, Gemini retry0; boot/backup/update OFF 유지.

Safe local evidence: `watch-chrome-prefixed.json`, `watch-chrome-trace-before.json`,
`watch-regression-before-final.json`, `watch-regression-after-final.json`,
`watch-real-browser-matrix.json`, `watch-real-browser-no-gesture.json`,
`watch-capacity-inspection-20260920.json`. 재현 절차/도구는 `tests/browser/README.md` 참조.
Local fixture 종료와 browser 종료를 확인했다. 실제 콘텐츠·URL·capability·credential은 evidence에 기록하지 않았다.
PHASE11/Audit0–10/Integrated Audit/V1삭제/legacy cleanup 미착수.

## Continuation — 승인된 de3aae sweep / 기능 실패 및 writer guard 정지·보존 검증 (2026-09-20)

**PHASE 10B INCOMPLETE — 21 PASS /3 FAIL /6 NOT TESTED. Services stopped; tenth preservation verified.**
사용자가 exact HEAD/pin의 단일 bounded30-gate 실행과, 전 필수 gate PASS 뒤에만 actual backup/restore →
boot/4h timer → bounded final observation을 통합 승인했다. Summary SOFT FAIL 뒤 독립 Music/TTS/Watch 검사를
계속했으나 `unexpected_python_writer` safety 조건이 발생해 guard가 두 서비스를 정지했다.
현재 승인된 단일 실행은 종료했다. 재시작·재시도·runtime 수정·guard 완화·추가 push/pin을 하지 않는다.

### Publication / activation / unchanged scope

- Push 직전6commit/22newblob 및 각 commit tree/message 검사 finding0. Runtime
  `de3aae30a82828433666c872b6789abfbb19648b` 이후2commit은 이 보고서/current plan만 변경.
  `99d80c6b5fc9aeddaf5ebd416539dfe7aa5a1ceb` → **`26da4c210792b8c0ee2aec17e12b9551bc5f3a9c`**
  정상 FF push/read-back 완료. Main `8432fdef40cddc131176fa875e350660dc897e12` 불변.
- Exact current pin **`r-de3aae30a8282843-3dac82a792fad576`**. Manifest
  `e70649a2607c642b08cd11399c1a081de05250560abbd5101be3e231d55a4c57`,17419files/schema[5,5],
  dependency `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6` 불변.
- Fresh stopped preflight: canonicalE566/config41ed/schema5, 기존9preservation 및 retained c724,
  current/rollback pointers, credential3scope/root observer, services/timers disabled, public9000 route PASS.
  Protected metadata aggregate `69b09b7272c5e05ce90df357f33da9193aed5e7999043ec0f1928f98826b0dfa` 일치.
  DB/config/release compatibility 검증 후 pointer-only activation1회, production start1회.
- Start `2026-09-20T01:40:45.328719Z`; ready `2026-09-20T01:41:11.029043Z`:
  **25.693s /70s PASS**. Run `batch-full-sweep-20260920-01`; expiry02:09:25.227418Z 이전 safety stop.
  Windows1009PASS/Pi979PASS+30intentional skip의 기존 exact-release 검증을 재사용했고 dependency 변경0.
- Operator orchestration만 별도 scratch/WORK 경로에 준비했다. Finalization 도구에는 approved actual canonical
  schema/count/data/metadata before/after 및 isolated restore 대조를 준비했으나 조건 불충족으로 실행하지 않았다.

### Current exact-run gate matrix

과거 ECD PASS를 승계하지 않는다. 실제 사용자가 확인한 결과와 미확인 경계를 분리했다.

| # | Gate | Result | Current-run evidence / limit |
| --- | --- | --- | --- |
| 1 | 70s startup | PASS | 25.693s /70s |
| 2 | Gateway | PASS | same-release ready |
| 3 | Command sync | PASS | readiness command sync |
| 4 | /내정보 | PASS | user confirmed |
| 5 | /랭킹 | PASS | user confirmed |
| 6 | /요약 | FAIL | external_temporary/http_server_error/503, one request |
| 7 | 보관함 | PASS | user confirmed |
| 8 | Volume display | PASS | display-only contract; user confirmed |
| 9 | Music URL | PASS | fresh request after stopping restored track |
| 10 | Music search | PASS | user confirmed search and actual audio |
| 11 | Selection | PASS | user confirmed |
| 12 | Queue | PASS | user confirmed |
| 13 | Human-audible Music | PASS | user heard actual audio |
| 14 | Normal stop | PASS | user confirmed |
| 15 | Voice disconnect | PASS | user confirmed |
| 16 | Human-audible join TTS | PASS | user heard entry announcement |
| 17 | TTS not overwritten | PASS | music yielded while TTS audible |
| 18 | Music after TTS | PASS | user confirmed resumed audio from previously-playing case |
| 19 | Paused intent / consecutive TTS | NOT TESTED | user explicitly cannot recall previously-paused case |
| 20 | Chrome Watch create | PASS | actual PC Chrome, video addition initially worked |
| 21 | Watch connect | PASS | actual public invite opened |
| 22 | Presence | PASS | single participant label visible; multi-client not verified |
| 23 | Refresh | FAIL | black player after refresh, controls absent |
| 24 | Network reconnect | NOT TESTED | actual network drop not performed |
| 25 | Tab return | NOT TESTED | no fresh confirmation before safety stop |
| 26 | Playback hydration | FAIL | video/position not restored; black player |
| 27 | Multi-participant sync | NOT TESTED | friends unavailable; >=2 participants not tested |
| 28 | Normal Watch close | NOT TESTED | safety stop interrupted completion; no independent PASS |
| 29 | Private admin close | NOT TESTED | new /시청 nonresponse overlapped stopped pair; blocked |
| 30 | Actual public Chrome path | PASS | actual watch.lgw323.com browser route accessed |

추가 필수/관찰 항목:
- **Music 한 클릭 pause/resume PASS**: 첫 클릭에 실제 음성이 멈추고, 다음 클릭에 재개됨을 사용자 확인.
  재생 중 `⏸️`는 누르면 수행할 일시정지 동작을 뜻한다. 이번 보고된 동작은 이 계약과 일치한다.
- 시작 직후 전날 트랙의 자동복원 관찰 후 사용자가 정상 퇴장시키고 새 URL·검색 경로를 각각 시험했다.
  재시작 복원은 유지 계약이지만, 전날 정지 시점과 저장 상태까지 정상이라고 추가 단정하지 않는다.
- 혼자 다른 voice channel로 빠르게 이동했다 돌아왔을 때 jukebox thumbnail 소실 관찰.
  Safe telemetry에 `empty` work 시작이 있으나 정확한 UI/actor 시점과 원인은 입증되지 않았다.
- TTS 실제 청취·재생 중 TTS 이후 음악 재개는 확인했다. 사용자는 후속 질문에서 **미리 pause한 상태는
  불확실**하다고 명시했으므로 pause intent PASS로 계산하지 않는다.
- Watch playing/refresh black failure 확인. Paused refresh, 실제 network disconnect/reconnect,
  >=2 참여자 play/pause/seek는 미검증. `유저_숫자`는 페이지당 random display name 생성 코드와 일치하지만
  이 사실을 black-player 원인으로 취급하지 않는다. CSP/iframe/player-ready/browser/provider 원인은 아직 미확정.
- 사용자 후속 `/시청` 무응답 당시 pair inactive/MainPID0를 확인했다. 해당 요청의 정확한 시각이 없어
  별도의 Discord command 결함으로 확정하거나 정상 종료/admin close PASS로 취급하지 않는다.

### Safety stop and operator observation conflict

- Final guard status **`guard_stopped_pair`**, trigger `safety_invariant_failed`, safe reason
  **`unexpected_python_writer`**. `pair_stopped/newest_state_preserved/inventory_verified=true`.
  Guard 실행 관찰 **520.003s**,25poll records (매 record가 독립 fresh sample인 것은 아님).
  마지막 fresh sample `2026-09-20T01:49:28.815300+00:00` 당시 두 서비스는
  ready/NRestarts0였고 DB probes 정상, integrity/schema5 PASS였다. 이후 guard stop 및 preservation 완료.
- **이번 agent의 관찰 도구 선택 문제**: safe JSON을 짧은 별도 SSH Python 프로세스
  `batch-poll.py`로 읽었다. 이 도구는 start/summary JSON만 읽으며 DB·credential 읽기/쓰기나 서비스 변경을 하지
  않지만, service/observer descendant가 아닌 Python을 모두 거부하는 기존 writer 규칙에 해당한다.
  이 감시 조건을 사전에 고려하지 않은 운영 도구 선택은 부적절했다. 이후 원격 확인은 `cat`/SCP로 수행했다.
- Production에 재현 요청하지 않고 exact `owned()` + rejection predicate AST를 가짜 process table로 검증:
  service/observer만 PASS, owned media child PASS, 별도 readonly Python은 같은 error 발생,
  cat/SCP는 발생하지 않음 — **4/4 expected results**. Runtime 수정0/production calls0.
  Stop 시점 offending PID/comm/parent가 기록되지 않으므로 **해당 poll이 실제 감지 대상이었다는 확정은 불가**.
  실제 무단 writer가 있었다거나 credential-security 위반이었다는 증거도 없다.
  Guard 규칙의 deterministic 충돌 가능성과 실제 PID attribution 한계를 함께 기록한다.
- 실제 H1 credential_permission 오류는 이번 run에 없었다. Credential 범위·readonly/권한 검사는 직전까지 PASS.
  Guard를 우회/완화하거나 같은 승인으로 두 번째 activation을 하지 않았다. 안전 원인이 해소됐다고 선언하지 않는다.

### Stop preservation / canonical identity

- **`verified_stopped_preserved_integrity`**. Current pin de3aae 유지, production/staging/ops 및 guard
  inactive/MainPID0, NRestarts0. Boot/backup/update/manual timers disabled/inactive; auto-update/manual polling OFF.
- New tenth preservation:
  `/var/lib/discordbot/phase10-retry-de3aae30a8282843-live-smoke-batch-full-sweep-20260920-01-guard-preservation`.
  Whole file inventory SHA256 **`2933e76fe7e07ea57e8183132949462476298961890aa3d2c23f33223250121a`**.
  Data/state/cache/backups/audit 및 config canonical/copy inventory 모두 일치, fsync PASS.
  기존9preservation와 config 불변, overwrite0.
- Newest canonical AND copy SHA256 **`860f5fcc96ae25322c392bffc65930923a7634229dc4c6294662c54d0529b647`**,
  schema5/integrity PASS; favorites40/owners3/play_counts53/settings1/users15/Watch0/0.
  Data checksum `c52382d5edf3c80d2e06dfbaa27a850bf04aaae6f77a73942fc8dc7a7937d386`,
  metadata checksum `f20317d783d9a168f84bdbdfc96152c3a7e3f6e6f6cae5fb81b516fe5d77cb63`.
  WAL/SHM/journal 양쪽 미존재. 이전E566 DB로 restore/replay하지 않는다.
- Config SHA256 `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 불변.
  Credential source metadata root:root0600/regular/no symlink, runtime credential mounts 정지 후 사라짐.
  Cloudflare route1개 `watch.lgw323.com → http://127.0.0.1:9000`, internal-port route0.

### Partial live observations / finalization boundary

- First→last fresh samples: Discord RSS83652→94868KiB, FD16→11, threads10→7;
  Watch RSS68496→70304KiB, FD10→11, threads4→5. 양쪽 NRestarts0, 마지막 successful DB probe counter100.
  마지막 music_processes0/cache6624319bytes, Watch sessions1/clients1; 안전 정지 후 persisted Watch0/0.
- Cache7files/6624319bytes, backups0, audit160files/33508bytes (stop 전 sample).
  Disk free103573794816→103573635072bytes; temperature67.2→64.45°C; throttling0→0.
  Sample read errors0, backup_age=-1/backup_rpo_exceeded=1은 actual production backup 미실행 상태다.
  First/last 값을 전체 기간 min/max나 production 안정성 완료 근거로 과장하지 않는다.
- **Actual production backup/Bot-Data publication/read-back/download/decrypt/restore0**;
  **boot/4h timer enable0; bounded final production observation0**.
  Partial live520.003s는 finalization 완료 후 observation이 아니다. Journal 용량 최종 확인은 미실행.
- 새 runtime code/test 변경0. Final approval 조건 불충족으로 COMPLETE 선언 금지.
  PHASE11/Audit0–10/Integrated Audit/V1 삭제/legacy cleanup 미착수.
  추가 production retry는 현재 종료한 단일 실행의 승인을 재사용하지 않고 정확한 다음 범위를 승인받는다.

Safe evidence: `batch-approved-preflight.json`, `batch-approved-start.json`, `batch-approved-push.json`,
`batch-git-audit-26da4c210792.json`, `batch-approved-gates.json`, `batch-final-summary.json`,
`batch-approved-stop-inspection.json`, `batch-poll-policy-reproduction.json`.
상세 원문 DB/사용자 ID/메시지/음악 제목·URL/credential 값은 조회·보고에 포함하지 않았다.

## Continuation — 승인된 cold archive 완료 / exact immutable candidate 검증 (2026-09-20)

**PHASE 10B INCOMPLETE — candidate `verified_not_activated`, 단일 통합 push/pin 승인 대기.**
사용자가 c724 하나의 cold archive와 후속 exact candidate 검증을 승인했다. 승인된 atomic 이동 뒤 멈추지 않고
새 release build → 새 venv full strict → credential/root observer → 실제 immutable runtime 경로 full strict →
protected-state 재검증을 완료했다. 이번 작업의 production activation/push는0회다.
과거 ECD의26PASS/3FAIL/1NOTTESTED를 새 후보의 live PASS로 승계하지 않는다.

### 승인된 retention 예외: 삭제 없는 단일 atomic 이동

- 상태 **`cold_archived_retention_exception`**. 정확한 원본
  `/opt/discordbot/releases/r-c72428e7db42e6ab-3dac82a792fad576` →
  `/opt/discordbot/retained/releases/r-c72428e7db42e6ab-3dac82a792fad576`.
- 직전 실제 online release16개 identity/manifest, current 및 activation/rollback 참조,
  newest-four 보호 집합을 재계산했다. 보호 집합은 ECD/1014a085/92c25546/787b317이며 c724는 미포함.
  Operations lock 아래 대상 inventory/보호 상태를 이동 직전에 다시 비교했다.
  Destination 미존재·source/parent 동일 filesystem·보호된 root 소유 parent 권한 확인 후 atomic rename,
  양쪽 parent fsync. 다른 release 이동/삭제·retention 기간 변경·capacity16 확대는 하지 않았다.
- c724 manifest SHA256 **`0a4d1d22e7c2561fcaab7c5906e92188e4bf6a309020773f21e9fee7e2ab6d2c`** 불변.
  Manifest payload17410files, manifest 자체를 포함한 전체 **17411files/19016entries/377118991bytes**.
  **이동 전=이동 후=build 후** 전체 inventory+metadata SHA256
  **`545f768741216ff9618d5406828ecaf05d9d1c59db0b96e475927426eb2f4aeb`**.
  상대경로·file type·byte hash·mode·uid/gid·ACL/xattr hash·mtime·inode/device/link count를 전부 대조했다.
  읽기에 따른 atime과 rename에 따른 root ctime은 불변 비교 대상에서 제외했으며 권한/내용 변화로 숨기지 않았다.
- Online count **16 →15 →16**: c724 이동으로 한 슬롯 확보, 새 de3aae3 후보 하나 생성.
  나머지15개 online identity/manifest는 그대로다. Cold archive의 실행 파일/venv는 실행하지 않았다.
  되돌릴 때는 원래 경로의 미점유·보호 상태를 재검토하고 같은 경로로 복귀·검증해야 한다.
- 이전 capacity 실패 work는 `/var/lib/discordbot/phase10-retry-build-de3aae30a828-capacity-failed`,
  실패 JSON은 `retry-build-de3aae30a828-capacity-failed.json`으로 byte/metadata를 보존했다.
  기존 failed evidence를 덮어쓰거나 DB/preservation 경로를 옮기지 않았다.
  Operator 도구의 합성 inventory/rename·reference/newest 보호·exact source 검사3개 PASS.

### Exact immutable candidate

| 항목 | 실제 검증 결과 |
|---|---|
| Runtime source | **`de3aae30a82828433666c872b6789abfbb19648b`** |
| Source archive SHA256 | `5e14d8a0a30680831e8825186ea4f21233ae95bedb4c0fb3f59ab0d712903ab7` |
| Immutable release | **`r-de3aae30a8282843-3dac82a792fad576`** |
| Dependency SHA256 | `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6` |
| Manifest SHA256 | **`e70649a2607c642b08cd11399c1a081de05250560abbd5101be3e231d55a4c57`** |
| Manifest files / schema range | **17419 / [5, 5]** |
| Final Windows exact archive full strict | **1009 PASS /0skip/0xfail/0fail/0error**,71.16초; 기존 audioop warning1 |
| 새 release venv build/full strict/immutable | **979 PASS /30 intentional skip/0fail/0error/0xfail**, build 전체 167.776초 |
| 새 release venv + immutable runtime 경로 full strict | **979 PASS /30 intentional skip/0fail/0error/0xfail**,74.946초 |
| Runtime 경로 검증 | **127 modules** 모두 새 release `app/src`에서 import; sys.prefix 새 release `.venv` |
| 최종 상태 | **verified_not_activated**; production current는 ECD 유지 |

Archive/source/dependency는 앞선1009 Windows 검증과 동일하며 capacity 때문에 runtime을 변경하지 않았다.
Builder는 기존 hash-pinned wheelhouse로 offline build했다. 첫 full suite는 새 release venv와 exact exported tree,
추가 full suite는 그 새 venv와 **새 immutable release의 runtime import 경로**를 강제하고 module origin을 확인했다.
Legacy characterization/doc/test support는 exact export를 사용한다. 이 source origin 확인이 기존 ECD venv를 썼던
직전 continuation의 source-only Pi979/30과 다른 candidate-level 근거다.
두 새 Pi suite 모두 RuntimeWarning/PytestUnraisableExceptionWarning를 error, xfail_strict=true로 실행했다.
Private network/nonroot unit이며 실제 canonical DB/config/state/cache는 검사 fixture로 쓰지 않았다.
후속 suite는 backup/audit 경로도 차단했다. Test 임시 데이터는 분리된 run 경로에만 생성했다.

세 service scope(discord-bot/watch-web/operations)의 config/secret format/schema preflight,
exact read-only systemd credential mount, direct credential-source denial 모두 PASS.
각 scope의 root observer/proc view도 exact ACL/read-only/namespace PASS, credential 원문 출력0.
최종 manifest 전체 hash inventory 재검증으로 추가 suite가 immutable release를 수정하지 않았음을 확인했다.

### Regression 범위 및 skip 대조

동일 source 전체 검사에 A1의 stale View/actor toggle/지연 audio effect/역순 dashboard edit,
TTS ordering/pause intent/Favorites/queue/stop/disconnect, C1 playing·paused refresh/ready 순서/같은 초대 재입장,
C2 독립2clients/늦은ACK/이전video·revision 거부/autoplay 직접복구, reconnect/terminal/bounded retry가 포함된다.
구현과 수정 전 재현은 바로 다음 A1/C1/C2 continuation이 기준이다. Source 변경 없이 전부 다시 검사했다.

Windows Music154/Watch102/data127/operations248 PASS. H1 ACL10+observer credential24,
H2 data probe57+observer policy23, full-sweep observer24를 포함하며 후보 Pi에서도 Node 이외의 skip은 없다.
H1/H2, storage/operations runtime, schema/journal/busy-timeout/dependency 정책 diff0 유지.

**Pi intentional skip30개 전부 classname+testcase name으로 최종 Windows PASS와 일대일 대조**했다.
두 새 Pi suite의 skip 집합도 같다. 전부 `pytest.skip`, unexpected skip0/xfail0.
아래 각 testcase의 원인은 Pi Node 미설치이며 runtime Node dependency를 추가하지 않았다.

| Testcase | Windows / 새 Pi |
|---|---|
| `test_shipped_watch_browser_client[iframe-independent-presence]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[empty-player-protocol]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[hydrate-before-player]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[recoverable-return]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[terminal-stays-closed]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[page-lifecycle]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[bounded-reconnect]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[return-open-probe]` | PASS / intentional Node-less skip |
| `test_shipped_watch_browser_client[select-before-player]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[playing-refresh]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[paused-refresh]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[hydrate-before-ready]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[ready-before-hydrate]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[same-invite-return]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[latest-before-ready]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[late-iframe-ack]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[peer-cannot-overwrite-authority]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[multi-client-timing]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[autoplay-recovery]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[unacknowledged-playback]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[reconnect-hydration]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[video-change-before-ack]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[seek-ack-is-asynchronous]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[reconnect-paused]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[paused-cue-reports-zero]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[terminal-4001]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[terminal-4002]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[terminal-4003]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[stale-revision]` | PASS / intentional Node-less skip |
| `test_shipped_watch_playback_reconciliation[empty-session]` | PASS / intentional Node-less skip |

Classname은 기존9개 `tests.integration.watch.test_browser_client`, 새21개
`tests.integration.watch.test_playback_browser`다. Safe pairing은 `candidate-cross-platform-final.json`에 보존한다.
실제 Chrome network drop/reconnect·playback hydration/multi-client 성공을 synthetic PASS로 대체하지 않는다.

### 작업 전후 production reconciliation

- Current source **`ecd391ff4548b7bda572ef916c30be296b714f94`**, pin
  **`r-ecd391ff4548b7bd-3dac82a792fad576`** 유지. Current/activation/rollback pointer hash 전후 동일.
- Canonical **`e5661a0256c9873941db974019f30256c9ed9e3d2f2559cb2eecd06b259c2e52`**,
  config **`41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`** 불변.
  Schema5/integrity PASS, favorites40/owners3, play_counts53/settings1/users15, Watch0/0.
  Data checksum `fb56b2bcb5c77b76cef837c5f22f6f6ddbe2dd24ed80d21c33b24e599a87dd36`,
  metadata `a30f3cabc852e189acef8841c9f3832ff5c5bbba6bd88d48d1e8454089b29745` 전후 일치.
  WAL/SHM/journal sidecar 없음; journal header rollback 유지. Migration/restore/replay0.
- Data/state/cache/backups/audit/config 및 **9개 preservation** 전체 byte/metadata inventory 불변.
  집계 SHA256 전후 **`69b09b7272c5e05ce90df357f33da9193aed5e7999043ec0f1928f98826b0dfa`**.
  최신 ECD preservation과 기존8개를 그대로 보존했다. Retained c724도 최종 inventory 동일.
- Production/staging/operations stopped/MainPID0, boot·backup/update/manual timers disabled/inactive, auto-update OFF.
  전후 다른 Python/media process0, runtime listener0. V1 시작/실행 관찰0.
  후보 생성 외 production 활성화·새 production DB write·새 preservation 생성은0이다.

### Final Git publication boundary

- 현재 remote base **`99d80c6b5fc9aeddaf5ebd416539dfe7aa5a1ceb`**,
  main **`8432fdef40cddc131176fa875e350660dc897e12`** 불변. 이번 작업 push0/force0/rebase0/history rewrite0.
- Runtime endpoint는 de3aae30 그대로이며 이후 모든 commit의 변경 파일을 개별 확인한다.
  허용 tail은 full-sweep report/current-plan 두 문서뿐이다. 이 continuation을 담은 최종 docs-only HEAD까지
  **6 commits/22 new blobs**의 모든 새 tree/blob/message와 금지 artifact 경로를 검사한다.
  정확한 최종 HEAD와 scan 결과는 commit 뒤 `batch-git-audit-<HEAD12>.json` 및 최종 승인 요청에 명시한다.
  새 내용을 직접 검토하고 secret/token/private key pattern/.env/DB/SQL/backup/binary/credential/운영 data·log artifact를 검사한다.
  사용자 handoff/zip은 계속 미추적이며 포함하지 않는다. 현재 Git 변경은 보고서와 current-plan만이다.

### 단일 통합 승인 요청과 다음 live 실행

사용자 이번 첨부 §11에 따라 **후보를 활성화하지 않고** 다음을 한 번에 승인 요청한다:
최종 docs-only HEAD까지 기존 `codex/rebuild-v2` 일반 FF push → 정확한 위 immutable pin activation →
단일 bounded30-gate full-sweep → 모든 필수 기능 gate PASS 시 조건부 actual finalization.
Push 직전 remote/최종 range/secret/artifact/runtime 이후 docs-only 여부를 다시 확인한다.

새 release의 live gates는 모두 NOT TESTED다. 70초 readiness/Gateway/command sync부터 기존30gate 전체를
재검사하며, A1 **한 클릭 pause/resume의 실제 audio+UI**, Music URL/search/실제청취,
사용자가 실제로 듣는 TTS/겹침없음/이후Music/연속TTS·pause intent를 포함한다.
PC Chrome public path에서 playing·paused refresh/hydration, **실제 network disconnect/reconnect**,
둘 이상의 참여자 play/pause/seek sync, tab return, 필요 시 autoplay 차단 직접복구,
normal close/private admin close/Cloudflare 경로까지 확인한다. 과거 ECD PASS를 승계하지 않는다.

일반 SOFT FAIL은 blind retry 없이 가능한 독립 gate를 계속한다. 진짜 HARD STOP은 즉시 안전 정지·
newest state의 새 unique preservation·fsync/inventory 검증이며 기존 보존본 overwrite/old DB restore/replay/V1 시작 금지.

모든 필수30gate와 A1 실제 동작 PASS 후에는 후속 production guard 인계를 확인하고 승인 중단 없이:
newest canonical encrypted backup → private Bot-Data publication/read-back → independent download →
decrypt/isolated restore/schema5/count/data/metadata/semantic/application reconciliation → canonical 불변 확인 →
production pair boot enable/4시간 backup timer enable → bounded final observation을 이어간다.
Auto-update/manual source polling OFF 유지. Ready/live/NRestarts/DB probe/RSS/FD/threads/Music child·cache/
Watch sessions·clients/backup age/audit/disk·journal/temperature·throttling을 실제 관찰 기간만큼 기록한다.
이 모든 단계가 PASS해야 PHASE10B COMPLETE다. 현재 actual production backup/restore/enable/final observation0,
**PHASE10B INCOMPLETE**. Audit0–10/Integrated Audit/PHASE11/V1 삭제/legacy cleanup 미착수.

Safe evidence: `batch-cold-archive-candidate-20260920.json`, `retry-build-de3aae30a828.json`,
`candidate-local-suite.xml/json`, `candidate-cross-platform-final.json`. 이전 capacity 실패 evidence도 보존했다.

## Continuation — A1 / C1 / C2 통합 수정 후보 검증 (2026-09-20)

**PHASE 10B INCOMPLETE — 통합 수정·양 플랫폼 소스 검사 완료, RELEASE CAPACITY BLOCKED.**
이번 범위는 사용자 첨부의 A1 Music pause + C1 refresh/hydration + C2 multi-client + reconnect 준비를
하나의 묶음으로 처리하는 것이다. 이전 ECD 실행의 26 PASS/3 FAIL/1 NOT TESTED는 역사적 live 근거로 유지하며,
새 runtime의 실제 Music/TTS 청취·PC Chrome·network drop PASS로 승계하지 않는다. Push/activation은 이번 세션에서 0회다.

### 정지 baseline 및 데이터 보호

- 작업 시작 전 새 sudo read-only `batch-stopped-baseline-20260920.json`이
  `verified_stopped_preserved_integrity`를 반환했다. Current production source
  `ecd391ff4548b7bda572ef916c30be296b714f94`, pin `r-ecd391ff4548b7bd-3dac82a792fad576` 유지.
- Canonical/copy SHA256 **`e5661a0256c9873941db974019f30256c9ed9e3d2f2559cb2eecd06b259c2e52`**,
  schema5/integrity PASS, favorites40/owners3, music_play_counts53/music_settings1/users15, Watch0/0.
  WAL/SHM/journal sidecar 없음. 기존8개와 최신9번째 보존본 모두 유지한다.
- Newest preservation은 `phase10-retry-ecd391ff4548b7bd-live-smoke-h2-full-sweep-20260919-01-guard-preservation`이며,
  whole inventory `9f162d8825de2b468386505acaff935de77b5035f17edb332efb9a4bcc94b0d0`.
  Current/copy data/state/cache/backups/audit/config inventory 일치·fsync 확인.
  Config **`41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`** 불변.
- Production/staging/ops stopped, MainPID0, boot 및 backup/update/manual timers disabled/inactive, auto-update OFF.
  새 runtime을 활성화하거나 V1을 시작하지 않았다. Candidate replay/old DB restore/remigration/down-migration/
  기존 보존본 overwrite/production lock 재현/실사용 데이터 fixture는 모두 0회다.

### 재현된 결함과 수정 범위

| 항목 | 수정 전 결정적 재현 | 최소 수정과 검증 한계 |
|---|---|---|
| A1 Music pause | Frozen playing/paused View가 캡처한 상태로 pause/resume을 선택하면 현재 audio와 다른 intent 또는 반복 no-op 발생. 먼저 시작한 HTTP edit가 늦게 완료되면 최신 paused 화면을 덮음. 새4tests 중3FAIL/1PASS | 버튼은 session identity를 유지한 `toggle_pause` 1개를 actor mailbox에 전달. 현재 actor 상태에서 한 번 결정하고 audio 효과를 await한 뒤 상태를 변경. Guild별 dashboard 편집을 직렬화하고 최신 actor projection/게시 revision을 확인. 과거 live의 정확한 callback 시각이 없으므로 이 경로가 유일한 당시 원인이라고 확정하지 않음 |
| C1 refresh/hydration | 비동기 iframe에서 load 후 즉시 seek/play/pause를 보내면 새 영상 로드보다 먼저 적용되어 위치0/준비 상태로 남음. iframe 준비 전 대기 시간과 이후 state/seek도 검증 | 최신 authoritative snapshot을 유지하고 playing 경과 시간을 반영. 영상과 startSeconds를 한 명령으로 load/cue. video ID·재생/일시정지 의도·위치가 맞는 iframe 상태 확인 전 완료 표시/peer echo 금지. 고정400ms suppression 제거 |
| C2 multi-client protocol | 두 독립 JS VM에서 기존 stale/paused iframe이 user_joined/sync_request에 답하면 authoritative playing42를 paused0으로 덮음. 늦은 ACK도 기존400ms 뒤 user command로 되돌아옴 | 서버만 hydration snapshot을 제공하며 join/return 때 peer snapshot을 요청하지 않음. 기존 wire 형식/명시적 영상 선택 명령 유지. Presence/chat이 실제 사용자 pause 입력을 억제하지 않음. Stale revision·retired socket·다른 video의 늦은 ACK 거부 |
| C2 autoplay/미확인 | 차단된 iframe을 모사하면 기존 화면은 socket 연결만으로 동기화 성공을 표시하고 무음에서 복구 수단이 없음 | `onAutoplayBlocked`/player error/5초 미확인 시 명시적 `재생 이어가기` 표시. 사용자 gesture만으로 최신 위치·의도 재적용, timer가 media 재시도하지 않음. 차단된 peer가 전체 방을 pause시키지 않음. 실제 친구 브라우저 실패가 autoplay 때문이었다는 증거는 없음 |
| Gate24 reconnect | 이전 live는 시험 미수행이며 재현된 live bug로 분류하지 않음 | 살아 있는 방/다른 peer를 유지하고 recoverable socket 교체 후 playing 및 paused snapshot 복원. 중복 peer/socket 방지, retired socket 메시지 무시, 기존5회 bounded reconnect와 terminal4001/4002/4003 유지. 다음 실제 PC Chrome network drop/reconnect 필수 |

A1 테스트는 한 클릭→실제 fake audio pause→paused/▶️ projection, 다음 한 클릭→audio resume→playing/⏸️,
늦은 audio effect 전 UI 불변, old session 거부, 역순 HTTP 완료를 검사한다. TTS ordering/pause intent와
queue/stop/disconnect/Favorites/SDK View lifecycle은 기존 Music suite 전체로 함께 검증했다.

Watch 새 harness는 shipped inline JS를 독립 VM 두 개에서 실행하고 비동기 load/cue·자동재생 차단·fake clock을 사용한다.
초기17회귀는 수정 전12FAIL/5PASS였다. 이후 video 교체 중 late ACK, 비동기 seek ACK,
paused reconnect, CUED 시간0 반환을 추가해 새21개+기존9개 총30개다.
서버 integration은 playing/paused late join·중복 join·다른 peer 유지 중 reconnect·authoritative return response를 추가했다.
30초 creation/5초 empty grace, slow peer pump/capacity/terminal cleanup, Origin/CSRF/capability 검사는 유지했다.

YouTube API의 `cueVideoById(startSeconds)`는 일시정지 의도로 영상을 준비하며 CUED에서 `seekTo`를 호출하면
재생이 시작될 수 있다. 따라서 CUED의 시간0 반환을 잘못된 위치로 보고 자동 seek하지 않고 준비한 위치를 유지한다.
자동재생 차단은 공식 event로 별도 표시한다. [YouTube IFrame API reference](https://developers.google.com/youtube/iframe_api_reference).
이 API 계약과 합성 재현은 실제 public Chrome 복구 성공의 대체 증거가 아니다.

### 통합 회귀와 exact candidate

- Local responsibility commits: Music `998e2f2`, Watch `63a3ec6`, stopped verifier `de3aae3`.
  마지막 verifier 변경은 최신 ECD/E566/9 preservation baseline과 정확한 Node-less30 allowlist뿐이다.
  H1/H2 정책을 기능 검사를 통과시키기 위해 완화하지 않았다.
- Focused Music154 PASS, 초기 Watch96 PASS, Music/Watch255 PASS,
  Music/Watch/operations/data 통합630 PASS. CUED 추가 후 final focused Watch browser/server42 PASS.
- **최종 exact archive Windows full strict 1009 PASS /0skip/0xfail/0fail/0error**, 71.16초.
  RuntimeWarning·PytestUnraisableExceptionWarning는 error, xfail_strict=true. 기존 audioop deprecation warning1.
  Pinned `windows-media-venv` 사용, dependency 설치/upgrade0. 전체 suite에 새 회귀 전부 포함.
- 최종 Windows 내 Music154/Watch102/data127/operations248 PASS.
  H1 credential ACL10+observer credential24, H2 data probe57+observer probe policy23,
  full-sweep observer24를 포함한다. ECD 대비 storage/operations runtime, H1/H2 guard/preflight,
  requirements/pyproject 경로 diff0. DB schema/journal/busy timeout/dependency 정책 변경0.
- Runtime source **`de3aae30a82828433666c872b6789abfbb19648b`**.
  Source archive SHA256 **`5e14d8a0a30680831e8825186ea4f21233ae95bedb4c0fb3f59ab0d712903ab7`**.
  Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`** 그대로.

- **Pi exact source full strict 979 PASS /30 intentional Node-less skip/0fail/0error/0xfail**, 75.798초.
  이 검사는 archive 파일 전체 byte 대조를 마친 de3aae3 exported source를, 같은 dependency hash의
  **기존 ECD venv**로 실행했다. Nonroot/private network/production data·state·cache·backups·audit·config
  inaccessible unit이며 unit exit0. 새 immutable release의 venv/manifest 검증을 끝냈다는 뜻은 아니다.
- Classname+testcase name으로 Pi skip30개 전부 최종 Windows1009 PASS와 정확히 대조했다.
  전부 `pytest.skip`이며 unexpected skip0/xfail0. `batch-cross-platform.json`에 일대일 목록을 기록했다.
  Stopped verifier도 prefix가 아닌 정확한30개 집합을 요구하며 추가·누락·중복 skip 거부 회귀4개 PASS.
- 작업 후 canonical E566/config41ed/9개 preservation 및 data/state/cache/backups/audit 전체 protected inventory 불변.
  서비스 시작0/activation0이며 immutable candidate 생성도0이다. 운영 정지 상태를 유지한다.

아래는 **의도된 Pi skip 각각에 대응하는 Windows PASS** 목록이다. Classname은 기존9개가
`tests.integration.watch.test_browser_client`, 새21개가 `tests.integration.watch.test_playback_browser`다.

| Pi에서 skip된 testcase (각 Windows PASS) | 환경상 사유 |
|---|---|
| `test_shipped_watch_browser_client[iframe-independent-presence]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[empty-player-protocol]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[hydrate-before-player]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[recoverable-return]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[terminal-stays-closed]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[page-lifecycle]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[bounded-reconnect]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[return-open-probe]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_browser_client[select-before-player]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[playing-refresh]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[paused-refresh]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[hydrate-before-ready]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[ready-before-hydrate]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[same-invite-return]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[latest-before-ready]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[late-iframe-ack]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[peer-cannot-overwrite-authority]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[multi-client-timing]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[autoplay-recovery]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[unacknowledged-playback]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[reconnect-hydration]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[video-change-before-ack]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[seek-ack-is-asynchronous]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[reconnect-paused]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[paused-cue-reports-zero]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[terminal-4001]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[terminal-4002]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[terminal-4003]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[stale-revision]` | Node.js 미설치; runtime dependency 추가 없음 |
| `test_shipped_watch_playback_reconciliation[empty-session]` | Node.js 미설치; runtime dependency 추가 없음 |

### Genuine blocker — release capacity / 보존 기한

첫 exact candidate build는 `offline_build_full_strict` 단계에서 중단됐다. `build-result.json`/pytest.xml/
새 candidate 디렉터리 모두 없었으므로 그 시도에서 Pi test가 실행됐다고 기록하지 않는다.
Read-only diagnosis로 `/opt/discordbot/releases` **16개/상한16**을 확인했고, 후속 private/read-only unit에서
동일 새 source의 실제 `Builder.build`가 dependency 검증 후 **release capacity guard**로 거부되는 것을
결정적으로 재현했다. 다른 build 오류를 추측한 결론이 아니다.

16개 모두 published이며 incomplete artifact0, 정상 retention eligible0이다. 현재/activation·rollback 참조/
최신4개 보호 정책을 그대로 계산했고 모든 release가 최소7일 보존 기한 안에 있다.
가장 오래된 release age는 검사 시533216.663초로 7일보다 짧다. 상한이나7일 정책을 변경하지 않았다.
H1/H2 live HARD STOP이 새로 발생한 것은 아니며, production을 시작하지 않은 상태의 빌드 admission blocker다.

**예상 identity `r-de3aae30a8282843-3dac82a792fad576`는 아직 존재하지 않는다.**
새 candidate manifest hash/file count/schema range/credential preflight/immutable inventory 검증은 **NOT COMPLETED**.
Source의 schema5 계약과 기존 credential 회귀 PASS를 이 미완료 항목의 PASS로 대체하지 않는다.

명시적 승인 전에는 정상 retention을 우회하는 이동/삭제나 capacity 확대를 하지 않는다.
즉시 계속하려면 아래 하나의 구체적 cold-archive 예외를 검토할 수 있다:

- 대상: `/opt/discordbot/releases/r-c72428e7db42e6ab-3dac82a792fad576`.
  과거 full-sweep 준비의 superseded 중간 후보이며 이 보고서의 이전 continuation도 미활성 후보로 기록한다.
  현재·rollback/activation 참조·최신4개 보호 집합에 없음; published/files17410.
  Manifest SHA256 `0a4d1d22e7c2561fcaab7c5906e92188e4bf6a309020773f21e9fee7e2ab6d2c`.
- 제안 목적지: `/opt/discordbot/retained/releases/r-c72428e7db42e6ab-3dac82a792fad576`.
  승인 후 직전 보호 집합/current/DB/config/9개 preservation 재검사와 전체 manifest inventory 검증을 먼저 수행한다.
  동일 filesystem·목적지 미존재를 확인하고 원본 byte/권한을 유지하는 rename·부모 fsync·이동 후 inventory/hash 대조로
  한 슬롯을 확보한다. 삭제/압축 손실/현재 pin 변경/DB 조작/V1 작업은 하지 않는다.
  Cold archive는 실행 경로가 아니며 필요 시 같은 원래 경로로 되돌린 뒤 검증해야 한다. Venv 경로를 고치거나 실행하지 않는다.
  이는7일 내 online release 위치에서 제외하는 **운영 보존 예외 제안**이며 아직 승인·실행되지 않았다.
- 다른 방법은 정상 보존 기한이 지난 뒤 보호 집합과 정리 대상을 새로 검토하는 것이다. 자동 정리/예약은 만들지 않았다.

사용자 첨부 §7의 “genuine safety blocker” 조항에 따라, 기능 하나만 수정하고 멈춘 것이 아니라
A1/C1/C2/reconnect·full Windows·exact Pi 소스 검사를 모두 끝낸 뒤 이 보존/승인 경계에서 멈춘다.
Capacity 해소 후에도 같은 source archive로 새 release build/full strict/credential/immutable/protected-state 검증이 필요하다.
현재 failed build work/result는 unique 이력 경로에 그대로 보존한 뒤, exact verifier의 fresh-path 조건에 맞춰 재개한다.
기존 실패 JSON을 덮어쓰거나 DB/preservation 경로를 옮기는 절차가 아니다.
그 검증이 성공한 뒤에만 사용자가 요청한 **하나의 combined push/pin/live+conditional finalization 승인**을 제시할 수 있다.
지금은 검증되지 않은 pin의 activation 승인을 미리 요청하지 않는다.

Safe evidence: `batch-stopped-baseline-20260920.json`, `retry-build-de3aae30a828.json`,
`batch-build-diagnosis-de3aae30a828.json`, `batch-exact-pi-tests-de3aae30a828.json`,
local `batch-windows-de3aae30a828.xml`, `batch-cross-platform.json`, `batch-safety-regression.json`.


### Git publication과 단일 승인 범위

- Remote base **`99d80c6b5fc9aeddaf5ebd416539dfe7aa5a1ceb`**, main
  **`8432fdef40cddc131176fa875e350660dc897e12`** read-only 재조회 불변.
- Runtime까지 range `99d80c6b5fc9aeddaf5ebd416539dfe7aa5a1ceb..de3aae30a82828433666c872b6789abfbb19648b`:
  4 commits/18new blobs 및 모든 새 commit tree/message 검사 finding0. 현재까지 push0.
- 최종 publication 대상은 위 base부터 **이 continuation을 기록하는 docs-only HEAD**까지다.
  Runtime 이후 허용 파일은 이 full-sweep report와 `docs/rebuild/current/current-plan.md` 두 개뿐이다.
  최종 HEAD·commit/blob 수와 전체 range 재검사 결과는 commit 후 `batch-git-audit-<HEAD12>.json` 및 최종 응답에 기록한다.
  Secret/token/private key 패턴과 .env/DB/SQL/backup/binary/운영 data/log/credential artifact 경로를 검사하며
  user handoff/zip은 미추적 상태로 보존한다. Pattern scan은 모든 형태의 비밀 탐지를 보장하지 않으므로
  새 코드·합성 fixture·문서 내용도 직접 검토했다. 실제 credential 값을 읽어 비교하지 않았다.

사용자 첨부 §7/§11/§12에 따라 이번에는 runtime/client를 수정했으므로 **새 production activation을 하지 않는다**.
검증된 runtime + 그 뒤 full-sweep-report/current-plan만 바꾸는 docs-only tail까지 `codex/rebuild-v2` 일반 FF push,
exact immutable pin, 단일 bounded30-gate full-sweep, 전30PASS 때 조건부 finalization을 **하나의 승인**으로 요청한다.
Push 직전에 remote/range/secret/artifact 및 runtime 이후 docs-only 여부를 다시 검사한다. Force/rebase/history rewrite 금지.

### 다음 실행의 필수 범위와 종료 조건

새 후보의 live gate1–30은 모두 **NOT TESTED — 새 push/pin 승인 대기**이며 ECD의 역사적 PASS를 승계하지 않는다.
70초 readiness/Gateway/command sync → 내정보/랭킹/요약/Favorites/volume → Music URL/search/selection/queue/
실제 청취/한 클릭 pause·resume/stop·퇴장 → 실제 들리는 join TTS/겹침 없음/이후 Music/연속TTS·pause intent →
PC Chrome public Watch create/connect/presence/refresh/**실제 네트워크 단절·재연결**/tab return/playing·paused hydration/
둘 이상의 참여자 play·pause·seek sync/normal close/private admin close/public path까지 단일 bounded sweep로 확인한다.
Gate19의 기존 TTS pause intent와 추가 A1 버튼 검사를 각각 기록한다. Browser 차단 시 안내·직접 재생으로 복구되는지도 확인한다.

일반 SOFT FAIL은 재시도하지 않고 가능한 독립 gate를 끝까지 수집한다. H1/H2를 포함한 진짜 HARD STOP은
즉시 stop→new unique preservation→fsync/inventory 검증이며 기존9개를 덮어쓰거나 DB를 되돌리지 않는다.

전30gate 및 A1 실제 동작이 PASS하면 이미 active인 후속 guard로 인계한 상태에서 다음을 이어간다:
newest canonical encrypted production backup → private Bot-Data publication/read-back → independent download →
decrypt/schema5/count/data/metadata/semantic/application isolated restore/open → canonical 불변 확인 →
production pair boot enable/4시간 backup timer enable → 실제 bounded observation.
Ready/live/NRestarts/DB probe/RSS/FD/threads/Music child·cache/Watch sessions·clients/backup age/audit/disk·journal/
temperature·throttling을 실제 관찰 기간만큼 기록한다. Auto-update와 manual source polling은 OFF 유지.
이 finalization까지 PASS한 경우에만 **PHASE 10B COMPLETE**로 기록한다. 지금은 actual backup/publication/restore/
boot/timer/final observation0이며 PHASE10B INCOMPLETE다. Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy cleanup 미착수.

## Continuation — ECD approved full sweep / functional failures / stopped and verified

**PHASE 10B INCOMPLETE.** 2026-09-19 사용자의 exact ECD 통합 승인을 집행했다.
승인된 일반 FF push와 단일 activation을 마쳤으며 **26 PASS / 3 FAIL / 1 NOT TESTED**다.
추가로 Music pause 버튼과 실제 음성 상태 불일치를 SOFT FAIL로 기록한다.
기능 실패 뒤에도 독립 Music/TTS/Chrome/두 종료 경로를 끝까지 확인한 다음 operator `finish`로 정지·새 보존했다.
이번 실행에서 HARD STOP invariant 위반은 관찰되지 않았다. 완료되지 않은 필수 기능을 PASS로 바꾸지 않는다.
현재 runtime은 ECD pin 그대로지만 서비스는 정지 상태다. 새 runtime 수정·추가 activation·blind retry 없음.

### Exact publication and activation

- Runtime **`ecd391ff4548b7bda572ef916c30be296b714f94`**, production pin **`r-ecd391ff4548b7bd-3dac82a792fad576`**.
  Source archive SHA256 `6d75f95d151c954cc84b3ee309b085ae954896cdeaaede143f1c882fb68f3418`.
  Dependency `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6` 불변.
  Manifest `f023b1fa6d412b81300a9dd64a1ed584b653fd3040513399d14e755421d8ea6a`,17416files/schema[5,5].
- 직전 remote `af37aa58a17753663ff33543e487da6455318cc9` → **`99d80c6b5fc9aeddaf5ebd416539dfe7aa5a1ceb`**
  `codex/rebuild-v2` 일반 FF push/read-back 완료. Main `8432fdef40cddc131176fa875e350660dc897e12` 불변.
  Push 직전5 commits/18new blobs 및 각 commit tree/message 검사 finding0. ECD 이후 report/current-plan docs-only.
  Secret/.env/DB/SQL/backup/private key/credential/production artifact 미포함. Force/rebase/history rewrite 없음.
  사용자 미추적 handoff/zip은 그대로 유지했다. 이 결과 보고의 후속 docs는 승인된99d push에 포함됐다고 주장하지 않는다.
- Exact-source Windows **978 PASS/0skip/0xfail**, Pi **969 PASS/9 intentional skip/0xfail** 검증을 사용했다.
  Pi Node-less browser9는 동일9 testcase Windows PASS로 대조돼 있다. 이번 live 실행 중 runtime/dependency 변경0;
  기존 synthetic/Node PASS가 아래 실제 Chrome 실패를 배제하지 못한다.
- Fresh stopped preflight: canonical `678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66`, schema5/integrity/config 호환 PASS,
  기존8개 preservation 및 protected inventory 불변, rollback journal header 확인.
  세 credential scope/root observer/direct source denied, writers0/listeners0, boot/timers disabled 확인.
  Config `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 그대로이며 DB replay/restore/migration을 하지 않았다.
- Run `h2-full-sweep-20260919-01`. Start `2026-09-19T14:26:49.513308+00:00` → ready `2026-09-19T14:27:14.358607+00:00`,
  **24.840초/70초 PASS**; Gateway/sync/exact release/NRestarts0.

### Current-release 30-gate human/technical matrix

| # | Gate | 판정 | 이번 실행의 근거·범위 |
|---|---|---|---|
| 1 | 70초 bounded startup | PASS | 24.840초, exact release ready |
| 2 | Gateway | PASS | Ready gate 및 실제 명령 응답 |
| 3 | Command sync | PASS | Ready gate 및 실제 명령 응답 |
| 4 | `/내정보` | PASS | 사용자 이번 release 성공 확인 |
| 5 | `/랭킹` | PASS | 사용자 이번 release 성공 확인 |
| 6 | `/요약` | PASS | 사용자 최소 범위 요청 성공 확인; 이전503 판정을 승계하지 않음 |
| 7 | `💾 보관함` | PASS | 사용자 열림 확인 |
| 8 | Dashboard / stored volume | PASS | 표시 성공; 사용자가 봇 조절 UI를 의도적으로 제거하고 Discord 사용자별 음량을 쓰는 의도 확인 |
| 9 | Music URL 요청 | PASS | 사용자 URL 자동 선택·추가·실제 청취 확인 |
| 10 | Music 검색어 요청 | PASS | 사용자 검색→선택→추가→청취 성공 확인 |
| 11 | 검색 결과 선택 | PASS | 사용자 명시적 성공 확인 |
| 12 | 대기열 추가 | PASS | 사용자 명시적 성공 확인 |
| 13 | 실제 Music 청취 | PASS | 사용자 URL·검색 경로 모두 들림 확인 |
| 14 | 정상 정지 | PASS | 사용자 정지 성공 확인 |
| 15 | 음성방 퇴장 | PASS | 사용자 성공 확인; 버튼 후1–3초 지연은 별도 관찰 |
| 16 | 입장 TTS 실제 청취 | PASS | 사용자 봇 입장 직후 안내가 들렸다고 확인 |
| 17 | TTS가 Music에 덮이지 않음 | PASS | 사용자 TTS 후 노래 순서 확인 |
| 18 | TTS 종료 뒤 Music 시작 | PASS | 사용자 실제 청취 순서 확인 |
| 19 | TTS / pause intent | PASS | 사용자 TTS 확인 중 정지 유지 확인; 일반 pause 버튼 결함 A1과 구분. 독립적인 연속 TTS 횟수는 미확정 |
| 20 | PC Chrome Watch 생성 | PASS | 사용자 실제 public 초대 경로 생성 성공 |
| 21 | Watch 접속 | PASS | 사용자 실제 접속 성공; 서버 접속 최대3 |
| 22 | 참여자 목록 | PASS | 사용자가 탭 전환까지 기본 항목 동작 확인 |
| 23 | 새로고침 | FAIL | 새로고침 후 영상 영역 검음·위치 복원 실패 |
| 24 | 네트워크 단절 후 재접속 | NOT TESTED | NOT TESTED 사유: 사용자가 네트워크를 끊는 시험을 수행하지 못함. 링크 재입장은 가능했으나 hydration 실패 |
| 25 | 다른 탭 이동 / 복귀 | PASS | 사용자 동작 확인; 전체 hydration 성공을 뜻하지 않음 |
| 26 | 재생 hydration | FAIL | 새로고침 검은 화면, 탭 닫고 같은 초대로 재입장하면 처음부터 재생 |
| 27 | 재생 동기화 | FAIL | 한 참여자는 연동되나 다른 참여자는 썸네일에 정지·무음; 전체 PASS 불가 |
| 28 | 일반 Watch 종료 | PASS | 전체 탭 종료 후 정상 종료·초대 메시지 자동 삭제 확인 |
| 29 | 개인 관리 서버 강제 종료 | PASS | 별도 새 방에서 관리자 종료·초대 메시지 자동 삭제 확인 |
| 30 | 실제 Cloudflare public path | PASS | PC Chrome 실제 public 접속 확인; route Watch9000만 일치. 재생 복원 실패는 별도 판정 |

추가 SOFT FAIL **A1 Music pause UI**: 사용자는 첫 클릭에 버튼 모양만 바뀌고 노래가 계속 나오며,
다음 클릭에서는 재생 이모지 상태에서 실제 일시정지됐다고 보고했다. TTS 중 pause 유지 PASS가 이 결함을 상쇄하지 않는다.
퇴장1–3초 지연은 정리 후 퇴장 성공과 함께 기록한다. 코드에 오디오 정리·voice disconnect 순서가 있으나
실제 지연의 원인을 확정하거나 버튼 무응답 문제 전체가 해결됐다고 주장하지 않는다.
`watch_reconnect`는 연결 기능 자체 FAIL로 오인하지 않고 시험 미수행으로 남긴다. 재입장 후 처음부터 재생된 현상은 hydration FAIL이다.
Music/TTS 청취와 순서는 사용자 확인에 기반한다. PCM/Voice acceptance는 보조 기술 근거다.
Chrome PASS/FAIL도 사용자 실제 public 화면 보고에 기반하며, 다른 참여자의 정확한 browser/autoplay 상태는 수집하지 않았다.

### Bounded sweep observation and safety limits

- Observer **1350.149초 / 65 samples**. 이는 full-sweep 부분 관찰이며,
  backup/timer enable 뒤 요구되는 final production observation이 아니다.
- 마지막 stop 전 sample: Discord/Watch ready=true, NRestarts0, DB successful probes **265/265**.
  이번 window에서 failed probe/contention/recovery event0, recovery_pending0, recent_failures0,
  allowlisted error codes0, journal read exit0/truncation=false. 과거 H2 원인의 소급 증명도, bounded BUSY live exercise도 아니다.
- H1 exact credential scope, schema5/integrity, release/config identity, writer scope, public route가 관찰 중 PASS.
  Cloudflare `watch.lgw323.com → http://127.0.0.1:9000` matching1/internal9001·9010·9011 route0;
  stopped inspector도 route를 재확인했다. 실제 browser 접속 PASS와 별도로 기록한다.
- Technical Music work started/succeeded **28/28**,
  firstPCM/Voice acceptance **12/12**.
  이는 URL 요청 수/곡 수/실제 청취 횟수가 아니다. 서버 `soft_failures=[]`는 UI/browser 결함 미검출을 뜻하며,
  사용자 보고 SOFT FAIL을 지우거나 성공으로 취급하지 않았다.

| Process | RSS KiB min–max | FD min–max | Threads min–max | NRestarts |
|---|---:|---:|---:|---:|
| `discord-bot.service` | 82184–91000 | 9–19 | 6–13 | 0 |
| `watch-web.service` | 68428–70736 | 9–15 | 3–5 | 0 |

- Sampled `music_processes` gauge는 0–0이었다. FFmpeg/PCM event는 있으므로 이 gauge만으로
  실행 중 child가 전혀 없었다고 판단하지 않는다. Music cache bytes 6,567,679–6,624,319.
  Watch sessions max 1,
  clients max 3; 종료 확인 뒤0/0.
- Audit aggregate 마지막 158files/33039bytes,
  disk free 104,122,605,568–104,123,109,376bytes,
  temperature 61.7–66.65°C, throttling values ['0'].
  Collection errors 0, metric/telemetry drops0.
  Backup0/age−1/RPO exceeded1은 actual production backup 미실행 상태이며 PASS가 아니다.
  전체 journal disk 사용량·완료 후 장기안정성은 이번 sweep에서 판정하지 않았다.

### Controlled stop and newest preservation

독립 gate 결과를 모두 분류한 뒤 operator `control/finish`를 생성했다. Guard reason 문자열은
`sweep_finished_or_deadline`이지만 이번 원인은 **operator finish**이며 finite deadline 만료나 HARD STOP이 아니다.
Pair stopped/newest state preserved/inventory verified 후, 별도 root read-only inspector가
**`verified_stopped_preserved_integrity`**를 반환했다. sudo 비밀번호는 사용자가 터미널에만 입력했다.

- Newest canonical/copy SHA256 **`e5661a0256c9873941db974019f30256c9ed9e3d2f2559cb2eecd06b259c2e52`**. 이전678e93 DB로 되돌리지 않았다.
  Schema5/integrity PASS; favorites40/owners3, music_play_counts53/music_settings1/users15, Watch sessions/playlists0.
  Data checksum `fb56b2bcb5c77b76cef837c5f22f6f6ddbe2dd24ed80d21c33b24e599a87dd36`; metadata `a30f3cabc852e189acef8841c9f3832ff5c5bbba6bd88d48d1e8454089b29745`.
  Canonical/copy 동일, WAL/SHM/journal sidecar 모두 없음.
- Ninth preservation **`/var/lib/discordbot/phase10-retry-ecd391ff4548b7bd-live-smoke-h2-full-sweep-20260919-01-guard-preservation`**.
  Whole inventory SHA256 `9f162d8825de2b468386505acaff935de77b5035f17edb332efb9a4bcc94b0d0`.
  data/state/cache/backups/audit/config current/copy 전부 일치, fsync PASS,
  기존8개 preservation 전체와 config 불변; read-only inspection 전후 protected state 불변.
- Production pair/staging/operations/observer inactive/MainPID0;
  production/staging boot disabled, backup/update/manual timers disabled/inactive, auto-update OFF.
  Candidate replay/old restore/remigration/down-migration/V1 start·기존 보존본 overwrite 없음.

### Consolidated remediation matrix and completion boundary

| Group | 확인된 사실 / 범위 | 다음 격리 검증·해결 과제 |
|---|---|---|
| A application/runtime | A1 pause 버튼 표시와 실제 음성 상태 불일치 SOFT FAIL. 퇴장1–3초 지연은 별도 관찰 | 실제 첫 클릭 intent·UI snapshot·actor/audio 상태 순서를 synthetic로 재현; TTS pause 유지와 일반 pause toggle을 분리 검증. 원인 미확정 |
| B external/provider | 이번 Summary/URL/search는 사용자 성공 확인; 안전 집계에 provider failure 없음 | Watch iframe/provider/autoplay 영향은 아직 배제할 수 없으나 provider 원인으로 확정하지 않음 |
| C browser/integration | C1 refresh/hydration 검은 화면·재입장 위치 소실, C2 일부 참여자 thumbnail 무음·sync 실패 | 실제 player ready/state hydration/autoplay/peer sync 순서를 격리 재현; 현재 Node9 harness PASS만으로 해결됐다고 판단 금지 |
| D operations/deployment | 이번 startup·H1 ACL·H2 probe·identity·route·controlled stop/preservation PASS, HARD STOP0 | 현재 e5661a DB/9preservations 보존. Runtime 수정 시 exact Windows/Pi 검증 뒤 새 push/pin 승인 필요 |
| E insufficient evidence | Network drop/recovery 미시험; 실패 참여자의 browser/player 조건과 pause 첫 클릭 원인 미확정 | 안전한 category/state metadata와 재현 조건만 확보. raw content/ID/URL/capability/credential 수집 금지 |

Actual newest encrypted backup →private Bot-Data publication/read-back/independent download/decrypt/
schema/count/data/metadata/semantic/application restore는 **BLOCKED BY Watch 필수 FAIL 및 network recovery 미검증**.
Boot/4시간 backup timer enable과 그 뒤 bounded final observation도 이 선행조건에 의해 **미실행**이다.
All-PASS일 때 사용할 외부 orchestration helper는 준비·문법검사만 했고 handoff/backup/finalizer는 실행하지 않았다.
서비스를 다시 시작하거나 finite 창을 연장하지 않았다. 이번에는 요청된 failure matrix를 후속 일괄 수정의 기준으로 남기고 중단한다.
PHASE10 COMPLETE/Audit0–10/Integrated Audit/PHASE11/V1삭제·legacy cleanup을 진행하지 않는다.

Safe evidence: `h2-approved-preflight.json`, `h2-approved-push.json`, `h2-approved-start.json`,
observer `summary.json`/`samples.jsonl`, `h2-approved-stop-inspection.json`, local `h2-approved-gates.json`.
위 JSON 및 runtime/preservation은 Pi 또는 ignored scratch에 유지한다. 운영 artifact 자체를 Git에 추가하지 않았다.
결과 문서3개를 exact-source archive에 overlay한 문서 구조·상대 링크 검사2 PASS, `git diff --check` PASS.
이번 결과 기록은 docs-only이며 변경 없는 runtime full suite를 다시 실행한 것으로 표시하지 않는다.

## Continuation — H2 subtype remediation VERIFIED / exact push-pin approval required

2026-09-19 첨부 지시에 따라 current plan·부모 보고서·최신 full-sweep continuation으로 상태를 재구성하고,
정지 상태 재검증 →synthetic 재현 →최소 진단/정책 수정 →회귀 →exact Windows/Pi 검증을 완료했다.
**PHASE 10B INCOMPLETE. 새 production activation0/push0/provider request0.**
다음 승인 후보는 아래 **ecd391ff 단 하나**다. 기존 운영 H2의 실제 SQLite 하위 코드는 소급 확정하지 못했다.
이번 결과는 가능한 BUSY 경로의 실제 재현 및 엄격한 subtype 처리·진단 보강을 검증한 것이며,
과거 H2가 BUSY였거나 모든 live 문제가 해결됐다는 주장이 아니다.

### Current production reconciliation and H1 boundary

- Current source/pin `92c25546af6b49044e17ed2a705a7cdf885532a0` /
  `r-92c25546af6b4904-3dac82a792fad576` 그대로. Dependency3dac82a…/config41edd03… 불변.
- Fresh root read-only `h2-stopped-baseline.json`: **verified_stopped_preserved_integrity**;
  canonical/copy **`678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66`**, schema5/integrity PASS.
  Favorites40/owners3, music_play_counts53/music_settings1/users15, Watch sessions/playlists0.
  Data checksum6c32578e…/metadata318a1331… 및 current/preservation inventory는 직전 H2 evidence와 같다.
  최신8번째 preservation inventory `6cb75333b6e47812a28a7d1bc1284fc0a03768852b713dcc42782035e08cc0e8` 불변.
- Production/staging/operations inactive/MainPID0, production/staging boot disabled,
  backup/update/manual timers disabled/inactive, auto-update OFF, current Watch9000 route/internal route0 확인.
  재현/빌드 전후 protected data/state/cache/backups/audit/config 및 모든8개 preservation 불변.
  테스트는 canonical에 mutation/lock을 걸지 않았고 candidate replay/restore/remigration/down-migration/V1 start 없음.
- H1은 직전 actual production ACL PASS가 유효하다. H1 구현을 재설계하거나 ACL 허용 범위를 바꾸지 않았다.
  최종 후보에서도 세 credential scope와 root observer view의 exact/read-only/direct-source-denied 검증을 통과했다.

### Concurrency review and what can cause the umbrella error

1. Discord와 Watch는 같은 파일에 각각 독립적인 `SqliteDatabase`를 구성한다. 각 process는 reader1/writer1
   bounded executor를 소유하며 worker가 매 요청의 connection을 열고 같은 thread에서 닫는다.
   Process-global DB lock은 없고 cross-process 동시성은 SQLite가 관리한다.
2. `connect`는 existing mode=ro/rw, busy100ms(남은 deadline 이하), synchronous=NORMAL/temp_store=MEMORY/
   cache_size−2000/trusted_schema OFF, read query_only를 설정한다. Reader BEGIN, writer BEGIN IMMEDIATE;
   callback은 동기 SQL transaction이고 DB transaction 안에서 provider/network await를 하지 않는다.
3. 두 process의 health probe는 정상 주기5초마다2초 request budget으로 reader lane을 사용한다.
   Watch writer는 owner lease heartbeat/receipt cleanup을 수행하고 Discord의 engagement/Music도 짧은 writer
   transaction을 사용한다. 별도 reader lane이 다른 process나 같은 process writer의 SQLite 잠금을 없애지는 않는다.
   장시간 transaction이 운영에서 실제 관찰됐다는 증거는 없다.
4. Phase3 계약은 explicit bootstrap WAL, archive/restore DELETE, startup journal 유지 및 busy/I/O typed umbrella를
   명시한다. WAL 전환 운영 절차를 Phase8로 넘겼지만 실제 promotion은 bytes를 보존하고 별도 WAL 전환을 하지 않는다.
   이번 root verifier는 DB header format bytes18/19만 읽어 **rollback**을 확인했다. 초기 immutable URI의
   `PRAGMA journal_mode` 결과만으로 mode를 확정하지 않고 header로 보완했다.
   따라서 **live WAL 전환이라는 과거 계획이 실제 운영 경로에는 구현되지 않은 차이**를 기록한다.
   Rollback 자체를 corruption으로 간주하지 않으며 이번 수정에서 journal/schema/DB 경로를 바꾸지 않았다.
5. SQLite rollback EXCLUSIVE는 다른 reader와 공존할 수 없고, BUSY는 process 간 충돌에서 발생할 수 있다.
   LOCKED는 같은 connection/shared-cache 상황을 구분한다. [SQLite locking](https://www.sqlite.org/lockingv3.html),
   [SQLite result codes](https://www.sqlite.org/rescode.html)를 코드·실제 synthetic 결과와 함께 대조했다.
   이 일반 규칙은 지난 H2의 실제 원인 확정 근거를 대신하지 않는다.

기존 `database_recent_failures=2`는 같은 요청의 worker/awaiter observation 두 개이며 독립 실패2건이 아니다.
지난354.569초/17 samples/Watch66 success+1 failure/ready snapshot 및 무결성 PASS는 그대로 유지한다.

### Isolated reproduction and causal limits

모든 재현은 fixture가 만든 임시 synthetic DB만 사용한다. Windows와 network-disabled Pi ARM64에서
동일 test case를 실행했다. Production 데이터/원문 exception/SQL/user content/credential을 출력하지 않았다.

| Condition | Reproduced evidence / classification |
| --- | --- |
| Separate process BEGIN / IMMEDIATE / EXCLUSIVE × DELETE / WAL | Pipe barrier로 writer 잠금을 확정한 뒤 실제 probe 실행. DELETE+EXCLUSIVE만 configure-stage SQLITE_BUSY5, connection_opened=true/close_succeeded=true. 나머지5조건 PASS. 기존 read+SELECT1 경로도 같은 BUSY umbrella 실패 재현. |
| Short writer overlap | 별도 process EXCLUSIVE를 probe connection 생성 뒤 해제하여 같은 request가 성공. 테스트를 위한 명시적 barrier이며 runtime retry/sleep 추가 없음. |
| SQLITE_LOCKED | Synthetic shared-cache schema lock에서 실제 extended LOCKED 재현. 현재 application은 shared cache를 켜지 않으므로 정상 process 간 transient로 허용하지 않음. |
| Missing file/parent | Actual temporary missing path CANTOPEN, 자동 DB 생성 없음. CANTOPEN만으로 missing과 permission을 항상 구별할 수 있다는 주장은 하지 않음. |
| Permission | Pi의 nonroot test worker에서 actual mode000 파일 접근 거부. Windows는 같은 PermissionError boundary 주입으로 대조; Windows POSIX chmod 검증이라 주장하지 않음. |
| Read-only filesystem / I/O | EROFS/EIO/ENOSPC 및 SQLite extended IOERR의 안전한 boundary 주입. 실제 디스크 고장·filesystem remount를 하지 않음. |
| Non-database / corruption | 임시 non-database bytes 및 SQLite 첫 B-tree page type 손상에서 실제 NOTADB/CORRUPT →data_integrity. |
| Open/configure/begin/execute/fetch/commit/close | 각 단계의 BUSY/LOCKED/IOERR/CORRUPT/NOTADB fault injection으로 단계·family·숫자·close 결과 검증. 임의 sqlite_errorname/경로/원문 메시지 미출력. |
| Cancellation / cleanup | Awaiting probe 취소 후 worker capacity를 조기 반환하지 않고 동일 reader lane barrier까지 drain·close 확인. Primary BUSY 뒤 close 실패는 cleanup_failed=true로 HARD; 원래 실패를 가리지 않음. |
| Threshold / observer | BUSY1→healthy1→healthy2 회복,60초 내 재발,15초 만료,stale readiness,unknown/malformed subtype,LOCKED/extended BUSY/close failure,terminal deadline/capacity 모두 fail-closed 검사. 실제 observer loop가 BUSY 뒤 계속하고 다음 hard event에서 stop하는 회귀 포함. |

처음 회귀는 새 `probe` 진단 API 부재로 실패했다. 이후 actual shared-cache test의 URI keyword 중복 문제를
fixture에서 수정했고 해당 실패를 production failure로 분류하지 않았다. 최종 full strict에는 skip/xfail로 숨긴 H2 test가 없다.

### Minimal repair and precise safety policy

- **`5e1a8b8`**: 고정 `select1_probe`의 stage, exception family, numeric SQLite code, allowlisted SQLite/errno
  family, connection_opened/close_succeeded/cleanup_failed만 기록한다. AppError context와 observer extraction에서
  두 차례 allowlist를 적용하며 raw exception/SQL/path/row/임의 symbol을 내보내지 않는다.
  `SqliteDatabase.probe`는 기존 connect/PRAGMA/busy deadline/reader executor를 공유하는 고정 read operation이다.
  Application data transaction/API, journal, schema, dependency, credential/config 값은 변경하지 않았다.
- **허용 조건 모두 일치해야 함**: database_unavailable + select1_probe + probe_configure +
  sqlite_operational + exact numeric5 + family busy + connection_opened=true + close_succeeded=true + cleanup_failed=false.
  Extended BUSY와 LOCKED도 허용하지 않는다. 재현한 subtype 이외 일반 DB 오류의 global downgrade는 없다.
- 직전 readiness가 유효하고 pending recovery가 없으며 최근60초 동안 허용 BUSY가 없을 때만1회
  `database.probe_contention`으로 기록한다. 실패 metric/history는 그대로 증가한다. 추가 요청/retry/backoff를
  만들지 않고 기존5초 정기 probe에서 **15초 미만에 연속 정상2회**를 요구한다.
- 회복 중 readiness가 사라지거나15초 만료/60초 내 두 번째 failure/정리 실패/다른 오류이면 HARD.
  Terminal failure는 readiness를 latch하고 다음 probe scheduling을 중단한다. 임의 성공1회로 terminal 상태를 풀지 않는다.
  Release/DB/schema/credential/writer/restart/resource/public-route 안전 조건은 계속 독립적으로 즉시 적용한다.
- **`ecd391f`**: terminal probe의 deadline/capacity 등 최상위 code가 database_unavailable이 아닌 경우도
  `database.probe_failed` event/count 자체로 HARD STOP을 유지한다. 최근 event tail에서 사라져도 누적 count가 보존한다.
- **`1014a08`**: stopped verifier를 최신92 pin/678e93 DB/8개 preservation에 맞추고 boot/timer disabled,
  header metadata 검증을 추가했다. H1 ACL 검사는 그대로 사용한다.

### Exact final candidate and verification

- Runtime source **`ecd391ff4548b7bda572ef916c30be296b714f94`**.
- Source archive SHA256 **`6d75f95d151c954cc84b3ee309b085ae954896cdeaaede143f1c882fb68f3418`**.
- 유일한 다음 승인 후보 immutable release **`r-ecd391ff4548b7bd-3dac82a792fad576`**.
- Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`** 불변.
- Manifest **`f023b1fa6d412b81300a9dd64a1ed584b653fd3040513399d14e755421d8ea6a`**;
  **17416 files / schema range [5, 5] / immutable validation PASS**.
- Focused data/operations363 PASS 후 verifier header3/terminal-error5 회귀를 추가했다.
  최종 Windows 전체 strict **978 PASS/0 skip/0 xfail/0 fail/0 error**,79.62초,
  RuntimeWarning/PytestUnraisableExceptionWarning error 및 xfail_strict, 기존 audioop deprecation1.
  새 H2 test는 data57/policy23/header3 = **83개**, 최종 전체에 모두 포함됐다.
- Exact-source Pi ARM64 **969 PASS/9 intentional skips/0 fail/0 error/0 xfail**,
  build+strict+immutable verification 168.827초. PrivateNetwork/production paths inaccessible인 nonroot
  격리 build/test service에서 승인된 기존 wheelhouse만 사용했다. 실제 운영 DB/서비스 요청 없음.
- 최종 상태 **verified_not_activated**; 세 application credential scopes + 세 root observer views PASS,
  readonly/exact/direct-source-denied, current pin/config/canonical/protected inventory/8개 preservation 불변 확인.
- 중간1014 source도 Windows973/Pi964+9 skip으로 검증됐으나, terminal probe HARD 정책 보완 뒤 final ecd에서
  두 플랫폼 full strict를 다시 실행했다. 중간 release는 **미활성·미승인 superseded build evidence**로 보존하며,
  다음 activation 후보로 제시하거나 별도 pin 승인 대상으로 삼지 않는다.

Pi Node-less browser skip9개는 아래 **동일 testcase 이름의 final Windows PASS와 일대일 대조**했다.
이는 harness 검증이고 PC Chrome/public-path live PASS는 아니다.

- `test_shipped_watch_browser_client[iframe-independent-presence]`
- `test_shipped_watch_browser_client[empty-player-protocol]`
- `test_shipped_watch_browser_client[hydrate-before-player]`
- `test_shipped_watch_browser_client[recoverable-return]`
- `test_shipped_watch_browser_client[terminal-stays-closed]`
- `test_shipped_watch_browser_client[page-lifecycle]`
- `test_shipped_watch_browser_client[bounded-reconnect]`
- `test_shipped_watch_browser_client[return-open-probe]`
- `test_shipped_watch_browser_client[select-before-player]`

### Preservations and publication boundary

아래 모든 path는 `/var/lib/discordbot/` 아래이며 DB SHA256 기준이다. 전체 directory inventory도 빌드 전후
일치했다. Latest canonical은 마지막 행과 같고, 이 작업에서 어떤 보존본도 덮어쓰지 않았다.

| Preservation | DB SHA256 |
| --- | --- |
| `phase10-precutover-63c7722/failed-attempt` | `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af` |
| `phase10-retry-368c8ebf7cbf-favorites-failed-20260919T065256492640Z` | `fab61bdda1dd2c8b664c5fd19525d1cdd46f20c82d630a94ce2ed4caf6f5cc65` |
| `phase10-retry-368c8ebf7cbff244-favorites-resume-guard-preservation` | `fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f` |
| `phase10-retry-49639828a3c2f181-operator-failed-20260919T092351777156Z` | `28291bf37128dd62815c818ac45865c8a504cc04a2b3dbb9a8a564d8226dab1d` |
| `phase10-retry-d14eba80bdec9126-live-smoke-guard-preservation` | `1d871bed4ba8b8fe4fd9426cfa15c8b373f700baca2f548f5cea571570252363` |
| `phase10-retry-2c768ec98d1fc8b1-live-smoke-guard-preservation` | `6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099` |
| `phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01-guard-preservation` | `f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` |
| `phase10-retry-92c25546af6b4904-live-smoke-h1-full-sweep-20260919-01-guard-preservation` | `678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66` |

원격 `codex/rebuild-v2=af37aa58a17753663ff33543e487da6455318cc9`,
`main=8432fdef40cddc131176fa875e350660dc897e12` read-back 불변.
미게시 source range **af37aa58…→ecd391ff…:4 commits/16 new blobs**(기존 live 결과 docs commit e15f062 포함).
각 range commit tree/message/blob의 forbidden artifact/secret pattern 검사 finding0.
이후 tail은 이 전용 보고서/current plan만 변경하는 docs-only 기록이며 최종 HEAD/range를 다시 검사한다.
최종 docs-only tail을 포함한 게시 예정 범위는5 commits/18 new blobs다. 최종 검사 결과와 HEAD는
`h2-git-audit-<HEAD>.json` 및 통합 승인 요청에 고정한다. 문서 구조·relative link2 PASS와 diff whitespace 검사도 통과했다.
사용자 미추적 handoff/zip은 수정·추가하지 않았다. 새 runtime/safety code 변경 **있음**;
dependency/config/schema/DB mode/location 변경 **없음**. Main/force/rebase/history rewrite 없음.

안전한 evidence: `h2-stopped-baseline.json`, `h2-focused.xml`, `h2-windows-ecd391ff4548.xml`,
`retry-build-ecd391ff4548.json`, `h2-cross-platform.json`, `h2-git-audit-*.json`.
Production 상태/30-gate 판정은 바로 아래 H2 live continuation의 **PASS3/BLOCKED27** 그대로다.
새 audible Music/TTS·Chrome/Watch·backup/restore/boot/timer/final-observation PASS는 없다.

**다음 단계는 한 번의 통합 승인**: final ecd391ff runtime + 이후 report/current-plan docs-only tail의
normal FF push, 위 exact immutable pin의 activation, newest678e93 canonical DB를 유지한 단일 bounded30-gate
full-sweep. 승인 전 push/production activation은 하지 않는다. 단순 재시도 대신 subtype·stage·cleanup evidence를
수집하며, generic DB failure와 검증 범위 밖 오류는 계속 HARD STOP/new preservation 대상으로 남긴다.
Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy cleanup은 시작하지 않는다.

## Continuation — approved H1 retry / H2 DB probe HARD STOP / preservation VERIFIED

2026-09-19 exact candidate 승인에 따라 단일 bounded full-sweep을 실행했다.
**PHASE 10B INCOMPLETE — STOPPED AND PRESERVED.** H1 ACL correction은 실제 production credential
검사에서 통과했다. 별개 **H2 `database.probe_failed / database_unavailable` HARD STOP**으로
감시기가 두 서비스를 정지하고 새 보존본을 생성했다. 원인을 확정하거나 safety 정책을 완화하지 않았다.
아래가 최신 상태이며, 이전 continuation의 승인 대기/787 pin/7개 보존본 상태보다 우선한다.

### Publication, exact identity and admission

- Runtime source **`92c25546af6b49044e17ed2a705a7cdf885532a0`**;
  current immutable pin **`r-92c25546af6b4904-3dac82a792fad576`**.
- Dependency `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`;
  manifest `fcc5d91f65aaf29b19018fa16f5e833f41e69e05d6b262b0c47780ac2b76e543`,17411 files/schema[5,5].
- Push 직전1715c1f…→**`af37aa58a17753663ff33543e487da6455318cc9`**의4 commits/11 new blobs와
  각 commit tree/message를 재검사했다. Runtime92 이후 전용 report/current-plan docs-only,
  source/dependency 변경0, secret/.env/DB/SQL/backup/private key/credential/운영 데이터 finding0.
  기존 `codex/rebuild-v2`에 normal FF push 후 exact af37aa58… remote read-back 완료.
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변; force/rebase/history rewrite 없음.
  미추적 사용자 handoff/zip은 추가·수정하지 않았다. 실행 결과 문서는 이 push 이후 로컬에서 갱신했다.
- 승인 후보의 exact tests: Windows895 PASS/0 skip/0 xfail; Pi886 PASS/9 intentional Node-less
  Watch skips/0 fail/0 error/0 xfail. 동일9개 Windows PASS 대조 완료. 상세 및 최초 잘못된 Windows
  runner 실패는 바로 아래 역사적 H1 검증 절에 남겼다. 이번 실행 중 runtime/dependency 변경0.
- Fresh preflight `verified_stopped_ready_for_approved_start`: canonical f47fbef…/schema5/integrity,
  config `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`, 모든 기존7개
  preservation/protected inventory, stopped writers/extra Python·media0/listeners0 확인.
  Boot/backup/update/manual timers disabled/inactive, exact credential scopes 및 direct source access denied,
  세 root credential observer view PASS. Public Watch9000 route1/internal9001·9010·9011 route0.
  Candidate replay/old restore/remigration/down-migration/V1 start 없음.

### Activation and H2 evidence

- Unique run **`h1-full-sweep-20260919-01`**, 새 root marker/observer path/preservation target 사용.
  22:33:37.702774 KST start →22:34:02.566434 ready, **24.856초/70초 PASS**.
  Discord/Watch exact release/Gateway/command sync/NRestarts0 및 live corrected credential safety PASS.
- Observer **354.569초/17 samples** 뒤 `guard_stopped_pair`; diagnostic에는
  `database.probe_failed=1`, `database_unavailable=1`, SOFT FAIL0, journal exit0/truncation false.
  전체 검사를 끝낸 정상 final observation이 아니라 HARD STOP까지의 부분 관찰이다.
  실제 sampling은 immutable inventory 검사 등을 포함해 약20–21초 간격이었다. 5초 간격이라 주장하지 않는다.
- 마지막 sampled health: Discord probe67 ok; Watch66 ok/1 failed. 두 health는 그 snapshot에서 ready=true였고
  Watch `database_recent_failures=2`였다. Adapter가 한 요청의 worker/awaiter failure를 각각 기록하므로
  이 수치를 독립적인 DB 장애2건으로 해석하지 않는다. Journal의 typed DB failure로 guard가 정지했다.
- 같은 마지막 safety 검사: schema5/integrity/identity/credential_scope/writer_scope/route verified.
  Restart0, Music processes0, cache5 files/6,567,679 bytes, Watch sessions0/clients0,
  telemetry/metric dropped0. 서비스 정보는 정지 직전 snapshot이고 정지 후 상태는 아래 inspector로 별도 검증했다.
- 정지 직전 RSS Discord82,292 KiB/Watch68,672 KiB, FD10/10, threads6/4,
  disk free105,053,290,496 bytes, temperature63.9°C/throttling0, audit156 files/32,570 bytes.
  Backup0/age−1은 최초 실제 production backup 미완료를 뜻하며 PASS가 아니다.

**확인된 범위와 미확정 원인:** 실패는 Watch process의 주기적 `SELECT 1` probe 경로다.
`storage/adapters/execution.py`는 여러 SQLite 오류와 filesystem OSError를 `database_unavailable`로
분류하지만 `operations/adapters/probe.py`는 최상위 error_code만 emit한다. 따라서 이번 telemetry로
SQLITE_BUSY/LOCKED/IO/permission 등의 세부 원인을 구분할 수 없다. 원문 DB/credential/log를 노출해
추측을 보완하지 않는다. 이번 정지 뒤 무결성 PASS는 corruption 증거가 없음을 보여 주지만,
일시적인 DB 접근 실패를 배제하지 않는다. H1 재발·credential 노출·Gemini quota·Music 원인으로 결론내리지 않는다.

### Current 30-gate matrix — this release only

**PASS3 / BLOCKED27 / functional FAIL0 / safety HARD STOP1.** 기본 기능 확인 안내 후 보고 시점까지
새 release의 사용자 성공/실패 답변을 받지 못했다. 4–30은 H2로 현재 검증이 차단되었으며,
사용자가 실제 실행하지 않았다고 단정하는 의미는 아니다. 뒤늦은 답변은 정지 전 실행임을 확인해 별도로 반영한다.
과거 Music/TTS/Chrome PASS는 승계하지 않는다. SOFT FAIL 때문에 independent gates를 생략한 것이 아니다.

| # | Gate | Result |
| --- | --- | --- |
| 1 | bounded startup | PASS |
| 2 | Gateway ready | PASS |
| 3 | command sync | PASS |
| 4 | /내정보 | BLOCKED BY H2 database_unavailable HARD STOP |
| 5 | /랭킹 | BLOCKED BY H2 database_unavailable HARD STOP |
| 6 | /요약 | BLOCKED BY H2 database_unavailable HARD STOP |
| 7 | 💾 보관함 | BLOCKED BY H2 database_unavailable HARD STOP |
| 8 | dashboard / stored volume | BLOCKED BY H2 database_unavailable HARD STOP |
| 9 | Music URL request | BLOCKED BY H2 database_unavailable HARD STOP |
| 10 | Music search request | BLOCKED BY H2 database_unavailable HARD STOP |
| 11 | result selection | BLOCKED BY H2 database_unavailable HARD STOP |
| 12 | queue addition | BLOCKED BY H2 database_unavailable HARD STOP |
| 13 | actual human-audible Music | BLOCKED BY H2 database_unavailable HARD STOP |
| 14 | normal stop | BLOCKED BY H2 database_unavailable HARD STOP |
| 15 | voice disconnect | BLOCKED BY H2 database_unavailable HARD STOP |
| 16 | join TTS actual audibility | BLOCKED BY H2 database_unavailable HARD STOP |
| 17 | TTS not overwritten by Music | BLOCKED BY H2 database_unavailable HARD STOP |
| 18 | Music after TTS completion | BLOCKED BY H2 database_unavailable HARD STOP |
| 19 | consecutive TTS / pause intent | BLOCKED BY H2 database_unavailable HARD STOP |
| 20 | PC Chrome Watch create | BLOCKED BY H2 database_unavailable HARD STOP |
| 21 | Watch connect | BLOCKED BY H2 database_unavailable HARD STOP |
| 22 | viewer presence | BLOCKED BY H2 database_unavailable HARD STOP |
| 23 | refresh | BLOCKED BY H2 database_unavailable HARD STOP |
| 24 | reconnect | BLOCKED BY H2 database_unavailable HARD STOP |
| 25 | tab leave / return | BLOCKED BY H2 database_unavailable HARD STOP |
| 26 | playback hydration | BLOCKED BY H2 database_unavailable HARD STOP |
| 27 | playback synchronization | BLOCKED BY H2 database_unavailable HARD STOP |
| 28 | normal Watch close | BLOCKED BY H2 database_unavailable HARD STOP |
| 29 | private admin close | BLOCKED BY H2 database_unavailable HARD STOP |
| 30 | actual public Chrome path | BLOCKED BY H2 database_unavailable HARD STOP |

Music/TTS audible 및 ordering 사용자 확인0, PC Chrome/public-path 사용자 확인0.
Telemetry/health/Cloudflare route 검증을 actual audio/browser PASS로 대체하지 않았다.
Service 자동 정지는 gate14/15의 정상 사용자 stop/voice-disconnect PASS가 아니다.

### Newest stopped state and preservation

- 자동 guard: pair_stopped/newest_state_preserved/inventory_verified 모두true.
  별도 sudo read-only inspector **`verified_stopped_preserved_integrity`** 완료.
- Pre-retry canonical SHA256 `f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` →
  **최신 canonical = 새 preserved DB `678e93ec4fd2d087d5ce20ba2239fb205b0daa130cb3e804e300dbd5183aef66`**. 최신 DB를 유지하며 f47로 되돌리지 않는다.
- 새 preservation: `/var/lib/discordbot/phase10-retry-92c25546af6b4904-live-smoke-h1-full-sweep-20260919-01-guard-preservation`.
  전체 inventory SHA256 **`6cb75333b6e47812a28a7d1bc1284fc0a03768852b713dcc42782035e08cc0e8`**.
  data/state/cache/backups/audit/config byte inventory 모두 current/copy 일치, fsync PASS.
  Canonical/copy schema5/integrity 및 counts/data/metadata checksum 일치. Read-only 검사 전후 protected inventory 불변.
- Counts favorites40/owners3, music_play_counts53, music_settings1, users15, watch sessions/playlists0.
  Data checksum `6c32578e5cf1109496f3ebbb86dc22c4b1f924e79275750c13bdb4d838295a16`;
  metadata checksum `318a1331957dd522d918b7915c73f3a3e8985e12f2a78dc6aedbdf14c44d2803`.
  Counts는 시작 전과 같지만 data/metadata hash는 변경됐다. 실제 row를 읽어 변경 내용을 추정하지 않는다.
  정상 종료 후 canonical/copy WAL/SHM/journal sidecars 없음을 확인했으며 별도 삭제하지 않았다.
- 기존7개 preservation/config 불변, 새 보존본 포함 총8개. Credential source7개 root0600 regular/nonsymlink;
  종료된 runtime credential mounts 없음. 이것을 종료 전 mount 검사 대신 사용하지 않는다.
- Production/staging/operations/guard inactive/MainPID0/NRestarts0. Production/staging boot 및
  backup/update/manual timers disabled/inactive. Auto-update OFF. Cloudflare Watch9000 route만 유지.

### Consolidated remediation / finalization boundary

| Group | Evidence and next requirement |
| --- | --- |
| A. application/runtime | H2 Watch DB probe failure confirmed; precise SQLite/filesystem cause unresolved. 다음 수정은 안전한 numeric error code/operation-stage 분류를 먼저 보존하고 synthetic multi-process SQLite/동시 reader·writer 조건에서 재현해야 한다. Runtime 재활성화 없이 준비하며, 재현 전 임의 busy timeout 증가나 failure 무시 금지. |
| B. external/provider | 이번 run에서 Summary/Music provider 실패 증거 없음. 이전503/음성 evidence를 이번 결과로 승계하지 않는다. |
| C. browser/integration | 이번 PC Chrome Watch evidence 없음; 전체 lifecycle/public-browser 검사는 H2로 차단. |
| D. operations/deployment | H1 정상 named-service ACL 검사 live PASS. H2 guard stop/new preservation/7개 old preservation 검증 PASS. 새 활성화는 이번 단일 실행 승인에 포함되지 않는다. |
| E. insufficient evidence | 27개 functional gates 및 DB 하위 원인 미확인. 정지 뒤 성공 요청을 다시 보내거나 과거 telemetry로 PASS 채우지 않는다. |

Mandatory live gates가 완료되지 않아 actual newest encrypted backup →private Bot-Data publication →remote
read-back/independent download/decrypt/schema/count/data/metadata/semantic/application restore를 **시작하지 않았다**.
Boot/4-hour timer enable 및 bounded final production observation도 **미실행**이다.
운영 pair는 정지 상태로 유지하고 이 승인에 따른 live 작업은 여기서 끝낸다.
Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy cleanup은 시작하지 않는다.

안전한 evidence: `h1-approved-preflight.json`, `h1-approved-push.json`, `h1-approved-start.json`,
`h1-observer-stopped.json`, `h1-observer-samples.jsonl`, `h1-approved-stop-inspection.json`,
`h1-approved-gates.json`. 로컬 `scratch/phase10`의 ignored safe 결과만 보고에 사용했고 원본 DB/로그/credential을
Git에 추가하지 않았다. 새 runtime 수정 없이 보고서와 current plan만 실제 결과로 갱신한다.
최종 문서 검증: tracked source archive에 변경된 보고 문서3개만 overlay하여 구조·relative link **2 PASS**;
사용자 미추적 handoff/zip은 검사 대상 archive에 넣지 않았다. `git diff --check` PASS, runtime/dependency diff0.

## Continuation — H1 ACL correction VERIFIED / new push-pin approval required

2026-09-19 사용자 지시에 따라 보고서 분리 뒤 같은 세션에서 H1 조사·격리 재현·최소 수정·후보 검증을 계속했다.
**PHASE 10B INCOMPLETE.** 이 continuation의 production activation/restart/provider request는0이다.
Current source/pin은787b3178908c08ffa926f41c64ae73753c39799a /
`r-787b3178908c08ff-3dac82a792fad576`, canonical DB는
`f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748` 그대로다.
기존 일곱 preservation·설정·data/state/cache/backups/audit의 전체 inventory 불변을 Pi 재현 전후 확인했다.
Services stopped/boot·backup/update/manual timers disabled, auto-update OFF를 유지한다.
마지막 실제 [30-gate matrix](#single-current-30-gate-live-matrix)는 PASS3/BLOCKED27/functional FAIL0이며
새 준비 검사를 audible Music/TTS·Chrome PASS로 승계하지 않는다.

### Reporting split and reconstruction

- 별도 commit **`9829aa3`**에서 부모 보고서의 최신 full-sweep 두 절을 이 파일로 이동했다.
  이동한 내용은 relative runbook link와 마지막 빈 줄 외에 그대로이고, 부모의 초기2c 이하 역사적 본문은 불변이다.
  이동 대상 원문(normalized text) SHA256 `b2ea46bdf620c2fa2295f50c7c93feba74d2e124c82737c154dd2967ba991575`.
- 부모는 실제 기존 위치 `phases/phase-10/phase-10-report.md`를 유지하고 current production 요약·이관 링크만 둔다.
  새 전용 보고서는 요청한 `docs/rebuild/phase-10-full-sweep-report.md`다.
  Current plan/README는 PHASE10에서 두 보고서를 모두 읽고 책임별 최신 continuation을 우선하도록 안내한다.
  Tracked `master_prompt.txt`는 없어 별도 파일을 만들지 않았다.
- 문서 구조 검사의 root 파일 목록을 새 보고서에 맞게 변경했다. Tracked archive 기반 구조·링크 **2 PASS**.
  사용자 미추적 handoff/zip, evidence, DB, preservation, release, Git history를 제거하거나 수정하지 않았다.
  보고서 분리 커밋은 production 동작 변경과 분리했다.

### H1 evidence and classification

현재 H1은 **observer/application-validator 정책 불일치로 재현된 운영 검증 결함**으로 분류한다.
Credential 노출이 확인됐다는 의미는 아니다. 과거 정지된 mount 자체는 남아 있지 않으므로 당시 모든
접근 권한을 소급 증명하지 않으며, 아래 실제 Pi 격리 재현과 당시 HARD STOP을 구분한다.

- Pi **systemd255 (255.4-1ubuntu8.17)**에서 운영 Discord/Watch와 동일한 LoadCredential source binding을 typed D-Bus로 확인했다.
  운영 pair는 정지한 채, 별도 bounded transient unit의 network를 차단하고 production data/state/cache/backups/audit를
  접근 불가로 설정했다. Credential 내용은 읽지 않고 stat/ACL metadata 및 access 여부만 검사했다.
- Discord3/Watch2/operations3 entries **모두 root-owned regular/non-symlink0440**,
  exact service-user read-only ACL, read-only mount. Root와 해당 service UID 외 reader가 없는 ACL이며 service의 source 직접 접근은 거부됐다.
  모든 entry에서 application `private_mode` PASS, 이전 observer의 `st_mode & 0o077` predicate FAIL을 재현했다.
  안전한 결과 `h1-credential-reproduction-02.json`: **validator_policy_mismatch_reproduced**,
  protected_state_unchanged=true, preservation_count7, production_started=false, DB/provider/network 요청0.
- 첫 격리 도구는 `systemctl show LoadCredential`의 복합 속성을 단순 문자열로 비교하다 child 실행 전에 멈췄다.
  이를 credential security 실패로 분류하지 않는다. D-Bus `a(ss)` 방식으로 source 일치를 확인한 후
  새 경로02에서 재현했고01 evidence/run은 보존했다. Production 재시도나 provider blind retry가 아니다.
- 로컬 회귀에서 기존 predicate가 exact named-service ACL을 거부하는 실패를 먼저 기록했다.
  수정은 `private_mode`를 공유하여 같은 ACL 판정을 사용하며, credential bytes는 읽지 않는다.
  Root observer의 UID 대신 실제 configured `discordbot` UID와 runtime process owner 일치를 요구한다.
  Descriptor nofollow/nonblock/cloexec, 성공·실패 close, directory/file mount read-only를 검사한다.
  다른 UID, owning group/other reader, extra ACL, writer/malformed/missing ACL, symlink/nonregular,
  잘못된 owner 및 writable mount는 계속 `credential_permission` HARD STOP이다.
- 기존 strict/full-sweep SOFT FAIL 정책·Music/TTS/Watch 동작·dependency/schema/DB/config/credential 권한은 바꾸지 않았다.
  회귀에는 실제 shared ACL 검사기를 통과하는 observer loop와 잘못된 ACL에서 즉시 stop하는 loop를 포함했다.
  관련 ACL/observer **67 PASS**, 이 중 새 회귀24개. Summary503 뒤 정상 ACL에서는 independent Watch ready 유지,
  unsafe ACL에서는 HARD STOP 유지 확인. 이것은 synthetic evidence이며 live smoke가 아니다.

### Exact retry candidate and verification

- Fix commit **`391e415`**: observer ACL 정책 정렬 + 회귀 + changelog.
- Verifier commit/runtime source **`92c25546af6b49044e17ed2a705a7cdf885532a0`**:
  newest f47 DB·787 pin·7개 preservation에 stopped admission을 고정했다.
  후보의 root observer가 `/proc/<isolated PID>/root/run/credentials`를 직접 검사하는 세 scope 검증을 추가했다.
  Protected wheelhouse symlink metadata 검사는 sudo 이후 수행하되 symlink 거부는 유지한다.
- Exact source archive SHA256 **`236630a076e6c9f448378eab9dda5a0dda40ff1d632e975cfa608204bed8f87a`**.
  Dependency requirements와 승인된 wheelhouse는 변경하지 않았다.
- 첫 Windows 전체 검사: 기본 개발 venv의 Deno launcher 부재로 **894 PASS/1 FAIL**,
  65.17초. 원인은 `test_pinned_provider_and_runtime_load_without_network`의 실행 파일 부재로 확인했다.
  해당 실행을 PASS로 숨기지 않는다. 이미 존재하던 `windows-media-venv`의
  yt-dlp2026.8.19/EJS0.8.0/Deno2.9.7 pin과 launcher를 확인해 같은 archive에서 다시 검증한다.
- Exact pinned Windows full strict **895 PASS/0 skip/0 xfail**,63.80초,
  RuntimeWarning/PytestUnraisableExceptionWarning error 및 xfail_strict 적용; 기존 audioop deprecation warning1.
- Pi exact ARM64 **886 PASS/9 intentional Node-less Watch harness skips/0 failures/0 errors/0 xfails**,
  151.390초.9개 testcase name 모두 위 Windows895의 PASS와 대조 완료, 예상 밖 skip0.
  최종 상태 **verified_not_activated**.
- 새 immutable candidate **`r-92c25546af6b4904-3dac82a792fad576`**.
  Manifest **`fcc5d91f65aaf29b19018fa16f5e833f41e69e05d6b262b0c47780ac2b76e543`**,
  17411 files/schema[5,5], immutable inventory PASS.
  Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`** 불변.
- Pi Discord/Watch/operations 세 scope의 config/credential-format/exact scope/read-only/direct-source-denied 검사 PASS.
  별도로 새 safety code를 root에서 실행해 실제 isolated service의 `/proc/.../root/run/credentials`를 검사한
  **세 root observer view 모두 PASS**. 이 root probe는 credential contents/DB/network를 읽거나 요청하지 않았다.
  재현·빌드 전후 current pin·canonical f47·config41edd0…·7개 preservation 및 protected inventory 불변,
  production pair inactive/MainPID0/boot disabled, backup/update/manual timers disabled/inactive 재확인.
- 원격 read-back `codex/rebuild-v2=1715c1f5d1de80b8693996662985eb6221259968`,
  `main=8432fdef40cddc131176fa875e350660dc897e12` 그대로다. 이 continuation의 push0/activation0.
  Remote1715c1f..runtime92c2554 **3commits/9newblobs**, 모든 새 commit tree/message/blob의
  secret/.env/DB/SQL·backup/private key/credential/운영 data artifact 검사 PASS, findings0.
  이후 검증 결과는 이 보고서/current plan만 변경하는 docs-only tail로 기록한다.

안전한 증거: Pi `/home/os/discordbot-phase10/h1-credential-reproduction-02.json`,
`retry-build-92c25546af6b.json`; local ignored `h1-windows-pinned-92c25546af6b.xml`,
`h1-cross-platform.json`, `final-push-audit-92c25546af6b.json`. 최초 도구/runner 실패 evidence도 유지했다.

### Consolidated remediation state

| Group | Current finding | Remaining boundary |
| --- | --- | --- |
| A — runtime validator | Exact service ACL에 대한 observer/application 정책 불일치 수정·24개 새 회귀·전체 strict PASS | 새 candidate의 production 동작은 미검증 |
| B — provider | 이 continuation의 external provider 호출0 | Summary503/429 및 Music provider 상태는 다음 단일 live 요청에서만 판정; blind retry 금지 |
| C — browser/audio integration | 현재 production 기능 gate27개는 기존 H1로 BLOCKED | 실제 사용자 Music/TTS/order 및 PC Chrome public lifecycle 확인 필요 |
| D — operations | 동일 Pi systemd mount에서 과거 판정 거부/새 root 판정 PASS, metadata-only 재현 완료 | 새 push/pin 승인 후 fresh reconciliation·70초 readiness·bounded sweep 필요 |
| E — evidence limits | 당시 종료된 mount ACL은 남아 있지 않음. 노출을 보여주는 증거 없음 | 재현한 정상 mount의 정책 불일치와 과거 instance에 대한 증거 한계를 구분 |

### Remaining gate / approval boundary

이번 준비는 production 재활성화 승인이 아니다. 후보의 Windows/Pi/root metadata 검증과 source-range 검사를 완료했으며,
새 source/pin 일반 FF push와 production activation을 위 정확한 identity로 승인 요청한다.
승인 대상은 `codex/rebuild-v2`로 runtime92c2554 및 그 뒤 full-sweep report/current plan docs-only tail의
일반 FF push, pin `r-92c25546af6b4904-3dac82a792fad576`를 사용한 단일 bounded full-sweep retry다.
Push 직전 최종 HEAD/range/secret 검사와 새 canonical/config/release reconciliation을 다시 수행한다.
현재 마지막 live H1와27 BLOCKED는 실제 재검증 전까지 남는다. 승인 후에는 단일 bounded full-sweep에서
HARD STOP만 즉시 중단하고 일반 feature/provider SOFT FAIL은 기록 후 독립 gate를 계속한다.
Actual audible Music/TTS/order 및 PC Chrome public Watch 전 gate PASS 뒤에만
actual newest encrypted backup/private Bot-Data read-back/independent restore/boot/4h timer/final observation으로 진행한다.
DB replay/old restore/remigration/down-migration/V1 start·Audit·PHASE11·legacy cleanup은 진행하지 않는다.

## 10B continuation — APPROVED FULL SWEEP / CREDENTIAL HARD STOP

**PHASE 10B INCOMPLETE.** 2026-09-19 exact full-sweep 후보 승인을 받아 production activation을
1회 수행했다. 70초 readiness gate는 **24.870초**에 통과했으나 첫 안전 검사에서
`safety_invariant_failed / credential_permission` HARD STOP이 발생했다.
감시기가 두 서비스를 정지하고 최신 상태를 **새 일곱 번째 preservation**에 보존했다.
이것은 Summary/Music 기능 실패에 따른 과거 fail-first 중단이 아니다. 사용자 지정 HARD STOP 경계이며,
재시작·자동 재시도·runtime 수정 없이 정지 후 확인과 통합 보고만 진행한다.
아래가 현재 결과이며, 이후 절은 당시의 역사적 기록이다.

### Exact publication and activation evidence

- Approved runtime **`787b3178908c08ffa926f41c64ae73753c39799a`**;
  current immutable pin **`r-787b3178908c08ff-3dac82a792fad576`**.
- Dependency **`3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`**;
  manifest **`906c8bcad00c5e78f54a42dd67d2b56fc0c5022d6430c058c70dd4f1786314ad`**,
  17410 files/schema[5,5]. Source archive
  `ce1760794f196620d372ee30b808ca9b5ed17168f33058ea3b1afd97049e5bb6`.
- Normal FF push/read-back **`e616511b77f5eb4553c7ede4fffdf2f0e69acf2c`** to `codex/rebuild-v2`.
  Before-push range `686b946439ab5404cf194f8282f4559be245a1ea..e616511b77f5eb4553c7ede4fffdf2f0e69acf2c`:
  5 commits/17 new blobs, all new commit trees/messages/blobs inspected; actual secret/forbidden artifact/binary0.
  Runtime 이후 tail은 phase report/current plan 두 문서뿐이며 runtime/dependency 변경0.
  `main=8432fdef40cddc131176fa875e350660dc897e12` read-back 불변; force/rebase/history rewrite0.
  미추적 `gpt_handoff` 자료와 zip은 포함하거나 변경하지 않았다.
- Exact archive Windows **871 PASS/0 skip/0 xfail**, 65.39초;
  Pi **862 PASS/9 skip/0 failures/0 errors/0 xfail**, 155.342초.
  Pi9개는 Node 부재에 따른 의도된 Watch harness skip이며 같은9개 testcase의 Windows PASS 대조 완료.
  이 검증 결과를 실제 audible/Chrome PASS로 승계하지 않는다.
- Fresh stopped preflight: canonical
  **`6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099`**,
  schema5/integrity/현재·최신2c 보존본 inventory 일치 및 이전 보존본6개 전체 불변.
  Favorites40/owners3, play counts53/settings1/users15, Watch sessions0/queue0.
  Config **`41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`** 불변.
  세 credential scope exact/read-only/direct source access denied, 외부 login 없는 preflight PASS.
  `watch.lgw323.com → http://127.0.0.1:9000` route1/internal9001·9010·9011 route0.
- Activation은 code pointer만 변경했고 현재 canonical DB를 사용했다.
  DB promotion/replay/old restore/remigration/down-migration/V1 start0.
  2026-09-19 **21:17:00.664 KST** start → **21:17:25.540 KST** readiness.
  Discord/Watch ready=true, same approved release, NRestarts0.
  Discord readiness는 Gateway ready와 `DeferredMusic`의 `tree.sync()` 완료 후에만 true이므로
  Gateway/command sync의 기술 증거로 기록한다.

### Single current 30-gate live matrix

**H1 = 첫 full-sweep safety 검사 `credential_permission` HARD STOP으로 production pair가 정지됨.**
사용자 기능 검사 요청을 보내기 전 H1이 발생했다. 기능 gate를 FAIL이나 과거 PASS로 대체하지 않는다.

| # | Gate | Result | Evidence / dependency |
| --- | --- | --- | --- |
| 1 | Bounded startup (70s) | PASS | 24.870s, exact release ready |
| 2 | Gateway ready | PASS | current runtime readiness true |
| 3 | Command sync | PASS | readiness requires successful tree sync |
| 4 | `/내정보` | BLOCKED BY H1 | no current-release user test |
| 5 | `/랭킹` | BLOCKED BY H1 | no current-release user test |
| 6 | `/요약` | BLOCKED BY H1 | no current-release provider request |
| 7 | `💾 보관함` | BLOCKED BY H1 | no current-release user test |
| 8 | Dashboard / stored volume | BLOCKED BY H1 | no current-release user test |
| 9 | Music URL request | BLOCKED BY H1 | no current-release request |
| 10 | Music search request | BLOCKED BY H1 | no current-release request |
| 11 | Result selection | BLOCKED BY H1 | search path not executed |
| 12 | Queue addition | BLOCKED BY H1 | selection/add path not executed |
| 13 | Human-audible Music | BLOCKED BY H1 | no human confirmation |
| 14 | Normal stop | BLOCKED BY H1 | guard stop is not a normal Music stop test |
| 15 | Voice disconnect | BLOCKED BY H1 | no functional voice-disconnect test |
| 16 | Join TTS human audibility | BLOCKED BY H1 | no human confirmation |
| 17 | TTS not overwritten | BLOCKED BY H1 | no observed Music/TTS ordering |
| 18 | Music starts after TTS | BLOCKED BY H1 | no observed Music/TTS ordering |
| 19 | Consecutive TTS / pause intent | BLOCKED BY H1 | no independent live TTS/pause test |
| 20 | Chrome Watch create | BLOCKED BY H1 | no actual Chrome session |
| 21 | Watch connect | BLOCKED BY H1 | create/connect path not executed |
| 22 | Viewer presence | BLOCKED BY H1 | no actual Chrome session |
| 23 | Refresh | BLOCKED BY H1 | no actual Chrome session |
| 24 | Reconnect | BLOCKED BY H1 | no actual Chrome session |
| 25 | Tab leave / return | BLOCKED BY H1 | no actual Chrome session |
| 26 | Playback hydration | BLOCKED BY H1 | no actual Chrome session |
| 27 | Playback synchronization | BLOCKED BY H1 | no actual Chrome session |
| 28 | Normal Watch close | BLOCKED BY H1 | guard shutdown is not normal browser close |
| 29 | Private admin close | BLOCKED BY H1 | no current-release admin close test |
| 30 | Actual Cloudflare public browser path | BLOCKED BY H1 | route inspection alone is not Chrome evidence |

30개 중 **PASS3 / BLOCKED27 / 기능 FAIL0 / NOT TESTED0**. 별도 safety gate H1은 FAIL/HARD STOP이다.
SOFT FAIL0은 기능 성공을 뜻하지 않는다. 이 activation의 allowlisted Music/Summary event0,
safe error code0, journal exit0/truncation=false였으며 기능별 실제 요청이 수행되지 않았다.
실제 audible Music/TTS와 Chrome public-path evidence는 모두 없고 과거 청취·harness 결과와 구분한다.

### Stop, preservation and observation

- Observer result `guard_stopped_pair`, policy `full-sweep`, first safety result
  `RuntimeError / credential_permission`, trigger `safety_invariant_failed`.
  보존 결과 `pair_stopped=true / newest_state_preserved=true / inventory_verified=true`.
  후속 read-only systemd 확인에서 두 production unit 및 guard inactive/MainPID0/NRestarts0/Result=success.
- New preservation:
  `/var/lib/discordbot/phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01-guard-preservation`.
  기존 보존본 overwrite 없음. Current release pin은787 그대로이며 재활성화하지 않는다.
- 독립 sudo read-only 결과 **`verified_stopped_preserved_integrity`**.
  Canonical after = preserved DB SHA256
  **`f47fbef36b7eded3e4b990f8179598b38b0e0bdbd818431eada33dab9aa89748`**.
  두 DB schema5/integrity/count/data/metadata reconciliation PASS, WAL/SHM/journal sidecar 모두 없음.
  Data checksum **`d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`** 및
  Favorites40/owners3/play counts53/settings1/users15/Watch0/0 유지.
  Metadata checksum은 before `4cae0601ec1209414019e6028e1b702101f464e9fd928c06a647f0c3d4ff797d` →
  after **`4958e8f59c02677ade32e91da63f8c655bbab2ae2dd6a528a50304664f519933`**.
  최신 상태를 보존했으며 historical hash로 되돌리지 않았다.
- Data/state/cache/backups/audit/config 전체 원본·보존본 inventory 일치, fsync 확인,
  **이전 보존본6개 및 설정 전체 inventory 불변**, read-only 검사 전후 protected state 불변.
  새 preservation 전체 inventory SHA256
  **`6cb61f67b87d2bd7d7f699a7621bf88b476bec6b797e2cc075453386cabc1d7b`**.
  Production/staging/ops/guard inactive/MainPID0, production boot 및 backup/update/manual timer disabled/inactive.
- Source credential 파일7개 metadata는 모두 regular/non-symlink/root:root0600.
  정지 후 두 runtime credential mount는 실제로 없어져 당시 mount ACL은 이 검사로 재확인할 수 없다.
  Unit User/Group=discordbot, UMask0077, NoNewPrivileges=yes, ProtectSystem=strict, ProtectHome=yes.
  현재 Cloudflare invocation의 마지막 구성에서 public9000 route1/internal route0 재확인;
  actual browser path 성공으로 해석하지 않는다.
- Live observer는 **1 sample /22.105초**이며 그 시간에는 안전 검사·정지·보존이 포함된다.
  정상 운영 22초 관찰이나 완료 후 final observation으로 해석하지 않는다.
  첫 표본: Discord RSS82052KiB/FD11/threads6, Watch RSS68380KiB/FD10/threads3,
  Music child0/cache6567679bytes, Watch sessions0/clients0, DB recent failures0,
  telemetry/metric drops0, backup age-1/RPO exceeded1, audit154files/32101bytes,
  free disk105517568000bytes, temperature67.2°C/throttling0. NRestarts0.
  첫 actual production backup 이전이므로 backup age-1은 PASS가 아니다.
  Journal priority6 count26, safe feature event0; journal 사용량·장기 자원 추세는 측정하지 않았다.

### Consolidated failure and remediation matrix

| Group | Current evidence | Conclusion / later batch remediation |
| --- | --- | --- |
| A — application/runtime | 설정 검증의 `private_mode`는 exact named-service ACL을 검사하지만 `sweep-safety.py`는 `st_mode & 0o077`만으로 거부 | 두 검증기의 정책 불일치 확인. 승인 runtime은 그대로 두고, 향후 동일 ACL 정책·부정 사례·observer integration을 함께 검증할 것 |
| B — external/provider | 이번 Summary/Music provider request0, historical Summary503 및 Music 실패만 존재 | 현재 provider 상태/무료 quota 여부 미확정. 새 PASS/FAIL로 승계하거나 blind retry하지 않음 |
| C — browser/integration | 실제 PC Chrome Watch0, current audible Music/TTS confirmation0 | 모든 관련 gate H1 차단. Harness PASS는 실제 browser/audio 증거를 대체하지 않음 |
| D — operations/deployment | readiness PASS 뒤 credential permission HARD STOP, pair stop/new preservation 성공 | 감시기의 credential 판정으로 sweep 종료. Mode/ACL metadata와 실제 접근 범위를 구분해 후속 격리 검증 필요 |
| E — insufficient evidence | 실패 이벤트에 실제 credential mode/ACL/파일 종류 세부 값이 없고 정지 후 두 mount 부재 확인 | 실제 노출인지 정상 ACL 오탐인지 이 이벤트만으로 확정하지 않음. Source 파일0600은 mount ACL의 대체 증거가 아님. 후속 검사는 값 없이 metadata만 사용 |

정지 후 값 없는 합성 ACL 검사에서 root-owned0440/named-service-read-only ACL은 기존 application validator가
허용하고 새 observer predicate는 거부하는 차이를 재현했다. 기존 ACL 회귀 **10 PASS/0 skip**, 0.35초.
이는 코드 정책 불일치의 증거이며 실패 당시 mount의 실제 ACL을 복원한 증거는 아니다.
Source/dependency/설정/실제 credential 권한을 변경하지 않았다.
최종 보고 두 문서의 tracked archive 문서 구조·링크 검사 **2 PASS**; 사용자 미추적 handoff는 검사용 archive에 포함하지 않았다.

안전한 증거 파일은 Pi `/home/os/discordbot-phase10/`의
`full-sweep-approved-preflight.json`, `full-sweep-approved-start.json`, `full-sweep-approved-push.json`,
`full-sweep-approved-stop-inspection.json`과
`/var/tmp/phase10-retry-787b3178908c08ff-live-smoke-full-sweep-20260919-01/summary.json`이다.
원문 DB/개인 ID/음악 제목·URL/secret 값 없이 집계·identity·안전한 오류 분류만 보고했다.

Actual newest production encrypted backup → private Bot-Data publication/read-back/independent download →
decrypt/schema/count/data/metadata/semantic/application restore는 **BLOCKED BY H1 and incomplete live gates**.
실행·성공 identity 없음. Boot enable/4h backup timer enable/final bounded production observation도 진행하지 않았다.
Auto-update 및 manual source polling은 OFF를 유지한다. Audit0–10/Integrated Audit/PHASE11/V1삭제/legacy정리0.
최종 보고서만 갱신하고 중단하며 새 runtime 수정·push/pin 재시도는 이 실행에 포함하지 않는다.

## 10B continuation — FULL-SWEEP POLICY VERIFIED / NEW RUNTIME APPROVAL REQUIRED

2026-09-19 새 사용자 지시로 fail-first 검사를 HARD STOP / SOFT FAIL의 단일 bounded full-sweep로 변경했다.
일반 기능 실패는 독립 gate를 막지 않고 수집한다. 이 세션에서 production activation은 **0회**다.
현재 production은 정지한2c pin이며 새 정책 release를 활성화한 것으로 기록하지 않는다.
**PHASE 10B INCOMPLETE**. 아래는 정책 구현·검증과 다음 live sweep의 승인 경계다.

### Verified current state and candidate

- Actual current source `2c768ec98d1fc8b1325f88cdfa1558bc6972d551`, pin
  `r-2c768ec98d1fc8b1-3dac82a792fad576` 유지.
- 새 runtime source **`787b3178908c08ffa926f41c64ae73753c39799a`**.
  정책fa53f3f, 최신 stopped verifier c72428e, probe connection 정리787b317의 원자적 로컬 commits.
  Dependency 변경 없음: `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`.
  정확한 Git archive SHA256 `ce1760794f196620d372ee30b808ca9b5ed17168f33058ea3b1afd97049e5bb6`.
- Candidate **`r-787b3178908c08ff-3dac82a792fad576`**, stage **verified_not_activated**.
  Pi exact ARM64 full strict **862 PASS /9 intentional Node-less Watch skips/0 failures/0 errors/0 xfails**,
  155.342초. 동일9개 testcase name의 Windows PASS 대조 완료, 예상 밖 skip0.
  Manifest **`906c8bcad00c5e78f54a42dd67d2b56fc0c5022d6430c058c70dd4f1786314ad`**,
  17410 files/schema[5,5]/immutable inventory와 세 credential scope 검증 PASS.
  Windows exact archive full strict **871 PASS /0 skip/0 xfail**,
  65.39초, 기존 Python3.12 audioop deprecation warning1. 새 정책/actor/marker/DB-close 회귀34개 포함.
  관련 Music/Summary/observer258 PASS 뒤 최종 DB-close regression24 PASS. 최종 문서 링크/구조2 PASS.
- 중간 후보c72428e는 Windows870 PASS, Pi861 PASS/Node-less Watch9 skip/0 failures/0 errors,
  154.328초였으나 최종 후보가 아니다. 서비스에 활성화하지 않았으며 immutable 보존한다.
- Remote 재조회: `codex/rebuild-v2=686b946439ab5404cf194f8282f4559be245a1ea`,
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변. 이 세션 push0/force0/rebase0/history rewrite0.
  787b317까지 원격686b946 기준4 commits/15 new blobs·모든 새 commit tree/message 검사에서 secret/금지 artifact0.
  새 runtime push/pin 승인은 아직 받지 않았다. 최종 보고 문서 tail은 source 뒤 docs-only로 별도 기록한다.
- Fresh sudo read-only `sweep-stopped-preflight.json`: current/schema5/integrity/manifest17406 files,
  data/state/cache/backups/audit/config 및 기존 **보존본6개 전체 inventory 불변**.
  Canonical before=after **`6270821c287a066533f89e4f59e4aa8a74b89c14dfb5c199601e1bba4817e099`**,
  최신2c preservation과 동일. 다른 DB로 되돌리거나 후보를 replay하지 않았다.
  Favorites40/owners3, play counts53/settings1/users15, Watch0/0.
  Data checksum `d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`,
  metadata `4cae0601ec1209414019e6028e1b702101f464e9fd928c06a647f0c3d4ff797d` 유지.
  Config `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 유지.
- Production/staging/ops services inactive/MainPID0, boot·backup/update/manual timers disabled/inactive.
  Auto-update OFF. Pi 추가 Python/media process0, runtime listener0 확인. 다른 host writer 부재를 이 검사만으로
  단정하지 않는다. 세 credential scope exact/read-only/direct source access denied, 외부 login0.
  Public route `watch.lgw323.com → http://127.0.0.1:9000`1개, internal9001/9010/9011 public route0.
  실제 Chrome 검증과 구분한다. 미추적 gpt_handoff/zip은 건드리지 않았다.

### Why the external observer alone cannot implement this sweep

2c `MusicActor._stop_for_smoke`는 첫 기능 실패에서 admission을 영구 잠그며
`DiscordFeatures.ready()`도 false가 된다. Summary trigger만 observer에서 제거하면 Music URL 실패 뒤
검색·독립TTS가 거부되고 결국 readiness HARD STOP으로 Watch도 막힌다. Marker 제거는 정상 retry를
재활성화하므로 no-blind-retry 요구에 어긋난다. 따라서 외부 observer만의 변경으로 충분하다고 주장하지 않는다.
사용자 첨부3절의 “If this requires changing runtime code ... obtain the required approval before activation”에
따라 새 exact source/release 검증 후 push/pin 승인을 받는다. 2c 승인 범위를 임의로 확장하지 않는다.

### Policy and regression evidence

- Root-owned, group/other non-writable, exact release, started/expires 최대1800초 JSON marker와
  `--policy full-sweep --run-id UNIQUE`를 동시에 요구한다. 기본 runtime 및 strict observer 정책 유지.
- Summary503/429·일반 Music/TTS/UI/command 기능 실패는 safe category/status를 남기고 SOFT FAIL.
  새 명시적 검색·정지/퇴장·독립 TTS는 허용하고, 실패한 current media와 대기 작업의 자동 retry/autoplay는 막는다.
  실패 current가 있는 상태에서 다른 취득 경로를 실제 재생하려면 기존 정지/퇴장으로 먼저 명시적으로 정리한다.
  독립TTS 완료가 기존 실패 media를 자동 재취득하지 않는 회귀도 통과했다.
- DB typed corruption/unavailable, schema/ledger/quick-check, exact release/dependency/config,
  writer/credential scope/public route, restart/crash, readiness 연속3회, 기존 resource cap·child capacity,
  관찰된 task.retrying, diagnostic coverage loss와 operator emergency는 HARD STOP이다.
  보존은 stop → unique copy → fsync → 전체 inventory 일치이며 기존 보존본 overwrite/restore 없음.
  DB read-only probe는 성공·예외 모두 connection을 명시적으로 닫는다.
- Fake clock의 실제 observer loop에서 Summary503 → Music prepare 실패 → TTS 실패 뒤에도
  Watch ready를 유지하며 다음 표본을 관찰했다. 정지는 지정 deadline에서1회 발생했다.
  이 synthetic 증거를 실제 Chrome/audible PASS로 기록하지 않는다. 실제 외부 provider 재시도0.
- Deadline/finish는 controlled stop·새 preservation. 전30 gate PASS와 사용자 실제 audio/Chrome 확인 및
  이미 active인 replacement post-cutover guard를 모두 확인해야 서비스 중단 없는 finalization handoff 허용.
  자세한 operator 절차·dependency 처리·rollback은 [cutover runbook](phases/phase-10/cutover-runbook.md) 최신 절을 따른다.

### Single current full-sweep gate matrix

아래는 **새 full-sweep 후보**의 live 결과다. 승인 전이므로 과거2c PASS를 승계하지 않는다.
현재 선행 조건은 검증된 새 runtime의 push/pin 승인이다. Pi 격리 검증은 완료됐으며 실제 live는 미실행이다.

| # | Gate | Current result |
| --- | --- | --- |
| 1 | Bounded startup (70s) | NOT TESTED — new runtime approval pending |
| 2 | Gateway ready | NOT TESTED — new runtime approval pending |
| 3 | Command sync | NOT TESTED — new runtime approval pending |
| 4 | `/내정보` | NOT TESTED — new runtime approval pending |
| 5 | `/랭킹` | NOT TESTED — new runtime approval pending |
| 6 | `/요약` | NOT TESTED — new runtime approval pending |
| 7 | `💾 보관함` | NOT TESTED — new runtime approval pending |
| 8 | Dashboard / stored volume | NOT TESTED — new runtime approval pending |
| 9 | Music URL request | NOT TESTED — new runtime approval pending |
| 10 | Music search request | NOT TESTED — new runtime approval pending |
| 11 | Result selection | NOT TESTED — new runtime approval pending |
| 12 | Queue addition | NOT TESTED — new runtime approval pending |
| 13 | Human-audible Music | NOT TESTED — new runtime approval pending |
| 14 | Normal stop | NOT TESTED — new runtime approval pending |
| 15 | Voice disconnect | NOT TESTED — new runtime approval pending |
| 16 | Join TTS human audibility | NOT TESTED — new runtime approval pending |
| 17 | TTS not overwritten | NOT TESTED — new runtime approval pending |
| 18 | Music starts after TTS | NOT TESTED — new runtime approval pending |
| 19 | Consecutive TTS / pause intent (if applicable) | NOT TESTED — new runtime approval pending |
| 20 | Chrome Watch create | NOT TESTED — new runtime approval pending |
| 21 | Watch connect | NOT TESTED — new runtime approval pending |
| 22 | Viewer presence | NOT TESTED — new runtime approval pending |
| 23 | Refresh | NOT TESTED — new runtime approval pending |
| 24 | Reconnect | NOT TESTED — new runtime approval pending |
| 25 | Tab leave / return | NOT TESTED — new runtime approval pending |
| 26 | Hydration | NOT TESTED — new runtime approval pending |
| 27 | Synchronization | NOT TESTED — new runtime approval pending |
| 28 | Close | NOT TESTED — new runtime approval pending |
| 29 | Private admin close | NOT TESTED — new runtime approval pending |
| 30 | Actual Cloudflare public browser path | NOT TESTED — new runtime approval pending |
| 31 | Actual production encrypted backup / Bot-Data publication / read-back | NOT TESTED — all live gates prerequisite |
| 32 | Independent download/decrypt/schema/count/semantic/application restore | NOT TESTED — production backup prerequisite |
| 33 | Production boot /4h backup timer | NOT TESTED — restore prerequisite; disabled |
| 34 | Final bounded production observation | NOT TESTED — finalization prerequisite |

### Consolidated remediation and evidence boundary

| Group / stage | Safe category / policy | Independent continuation / blocked gates | Supported layer / repair evidence |
| --- | --- | --- | --- |
| A — full-sweep Music admission | validation policy limitation; code prepared | New mode permits explicit search/TTS; actual gates await approval | Existing fail-fast latch/ready coupling confirmed; focused and full strict tests |
| B — prior2c Summary | `external_temporary/http_server_error/503`; SOFT FAIL in new mode | Must continue Music/TTS/Watch; no dependent blocking | External provider response confirmed historically; current availability/quota unknown; one intended live request required |
| C — Watch/Chrome integration | insufficient live evidence | All browser lifecycle checks remain independently required | No new browser defect established; actual PC Chrome public path needed |
| D — observer workflow | old Summary/Music fail-first policy; replaced only for bounded mode | New guard classifies safety separately; no automatic request retry | Synthetic multi-failure loop and safety tests; actual live observer not yet exercised |
| E — audible Music/TTS/input | insufficient exact-release evidence | Prior Music no-response followed Summary stop; no isolated active-runtime failure proven | Need fresh URL/search, actual hearing/order, normal stop/disconnect and pause checks |

이번은 승인 대기 준비 결과이며 실행한 full-sweep의 완료 결과가 아니다. 원래 사용자 목적은 아직 남아 있다.
일반 feature bug를 live 중 하나씩 고치거나 provider/model/config/dependency를 바꾸지 않았다.
새 canonical preservation 생성0(서비스 시작0), 기존6개 identities는 바로 아래 보존 이력 표와 동일하다.
Actual backup/publication/restore/boot/timer/완료 후 observation0. Audit/PHASE11/V1 삭제/legacy cleanup0.
최종 검증을 완료했다. Exact new source787b317/pin r-787b3178908c08ff-3dac82a792fad576와
보고 docs-only tail의 일반 FF push 및 단일 full-sweep activation을 승인 요청한다.
Safe evidence: `sweep-stopped-preflight.json`, `retry-build-787b3178908c.json`,
local `full-sweep-final-windows.xml`, `full-sweep-cross-platform.json`.
**Final verdict: PHASE 10B INCOMPLETE — policy verified, production sweep awaiting required new-runtime approval.**
