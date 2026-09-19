# PHASE 10 Report — Production Cutover

## 10B continuation — SUMMARY FAILED / STOPPED / VERIFIED RETRY AWAITING PUSH-PIN APPROVAL

2026-09-19 승인된 d14 release의 smoke에서 `/요약`이 실패했다. 즉시 operator stop을 요청하여
서비스를 정지하고 최신 상태를 다섯 번째 고유 preservation에 보존했다. **PHASE10 INCOMPLETE**.
사용자 지시대로 정지 후 분석·격리 재현·수정을 계속했으며, 새 runtime은 아직 push/activate하지 않았다.

### Actual latest gates and protected state

- d14 사용자 PASS: `/내정보`, `/랭킹`, `💾 보관함`, footer 볼륨100% 표시.
  `/요약` FAIL: 기존 일반 오류 응답을 사용자에게 표시했다. 이 release의 Music/TTS 실제 청취,
  Music/TTS 순서, Chrome public Watch 및 private admin close는 미검증이다.
  이전496 Music 실제 청취 PASS를 새 d14 gate의 PASS로 이전하지 않는다.
- 사용자는 추가로 보고한 버튼 무응답이 **이전 음악 테스트**에서 발생했다고 확인했다.
  새 d14 smoke에서 재현됐다고 기록하지 않으며, 추가 live 재현은 하지 않았다.
- Guard 결과 `guard_stopped_pair`, trigger `operator_stop`, pair stopped/newest state preserved true.
  실제 관찰 **183.341초 / 191 poll records**. 마지막 관찰은 ready2/2, NRestarts0,
  DB probe 성공36/37·recent failures0, Discord/Watch RSS82588/68652 KiB, FD10/10,
  threads6/4, Music child0·cache5 files/6567679 bytes, Watch sessions/clients0/0,
  disk free106910105600 bytes, temperature64.45°C, throttling0이다.
  이 부분 관찰은 완료 후 production observation을 대체하지 않는다. Production backup은 아직 없다.
- Current pin **`r-d14eba80bdec9126-3dac82a792fad576`**, services inactive/MainPID0.
  Boot 및 backup/update/manual timers disabled, auto-update OFF.
  새 보존본 **`/var/lib/discordbot/phase10-retry-d14eba80bdec9126-live-smoke-guard-preservation/`**.
  Canonical/new copy DB SHA256 **`1d871bed4ba8b8fe4fd9426cfa15c8b373f700baca2f548f5cea571570252363`**.
  모든 file byte inventory 비교 PASS, 기존 네 preservation 불변, 정상 정지 후 WAL/SHM/journal 없음.
  Candidate replay/old DB restore/remigration/down-migration/V1 시작 없음.
- 최신 read-only DB integrity/schema5 PASS, favorites40/owners3, music_play_counts53,
  music_settings1, users15, Watch playlists/sessions0/0.
  Data checksum `d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`,
  metadata checksum `85c5820b80689a03889ce5d05ab02847c7a5ab85351eeba1d2bf3f8a64bc0de3`.
  Config SHA256 `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 불변.

### Evidence, reproduction and repair

- 실제 두 Summary 요청은 `external_temporary`, queue depth0으로 각각
  10:09:50.570048Z/5.505092초, 10:10:09.010178Z/4.098395초에 기록됐다.
  당시 telemetry에는 HTTP status가 없으므로 두 요청의 정확한 HTTP code는 확정하지 않는다.
- 같은 d14 release/configured model/credential scope의 **합성 요청 1회**는
  **HTTP503 / UNAVAILABLE / ExternalTemporaryError /5.321초**였다.
  DB 접근·Discord login·실제 대화 전송 없이 수행했고 모든 protected state가 불변이었다.
  이는 제공자 일시 실패의 독립 증거이며, 제공자 회복이나 두 live 요청의 정확한 HTTP503을 뜻하지 않는다.
  추가 provider 재시도, fallback/model/config/dependency 변경은 하지 않았다.
- `a1e9b5f`: Dashboard가 Discord HTTP edit 전에 기존 View를 stop하여 응답 대기 중 버튼 callback이
  끊기는 결함을 실제 SDK Message.edit/ViewStore와 지연·실패 transport로 재현했다.
  수정은 이전 callback을 HTTP 완료까지 유지하고, 성공 시 기존 View 종료와 공개 SDK add_view 등록을
  await 없이 연속 수행한다. 실패·취소 시 이전 등록을 유지한다. 버튼 문구·배치·기능은 그대로다.
  두 직접 regression은 수정 전 실패/수정 후 PASS. 이는 과거 보고와 부합하는 코드 결함 재현이며,
  과거 live HTTP 지연 원문은 수집하지 않아 그 요청의 정확한 transport 원인까지 확정하지 않는다.
- `868cea73`: Summary 실패의 allowlisted reason/HTTP status만 telemetry에 추가했다.
  응답 body·사용자 payload·credential은 출력하지 않으며 기존 공개 응답과 요청 횟수를 유지한다.
  기존 guard는 Summary 실패를 필터에서 누락했으므로 typed Summary dependency/delivery 실패도
  자동 정지·새 보존 대상으로 추가했다. Validation/authorization 응답은 이 실패 gate에서 제외한다.
  **이 변경은 upstream503을 고친 것이 아니다.** 다음 승인된 live gate에서 성공 여부를 확인해야 한다.
- `2c768ec`: stopped verifier를 최신 d14 pin/DB1d871… 및 다섯 preservation에 맞췄다.
  관련 Music/Summary216개, Summary/observer85개 PASS.
- 현재 workspace 전체 strict는 **836 passed /1 failed**였다. 실패1개는 별도 미추적
  `docs/rebuild/gpt_handoff/` 복사 문서의 깨진 상대 링크81개였다. 해당 사용자 파일과 zip은
  변경·삭제·stage하지 않았다. Test를 건너뛰거나 제외 규칙을 추가하지 않았다.
  실제 release와 동일한 **Git commit archive 전체**를 별도 Windows 디렉터리에 풀어 재검사하여
  **837 passed /68.71초 /skip0/xfail0**. RuntimeWarning/unraisable error 및 strict xfail 적용,
  기존 audioop deprecation1. 실제 운영 DB/외부 서비스를 쓰지 않는 기존 격리 fixture를 사용했다.

### Verified candidate and next approval gate

- Runtime source **`2c768ec98d1fc8b1325f88cdfa1558bc6972d551`**.
  Archive SHA256 `72e35897c5659f736dcf5e3df2c06903528d5d7e48638c8ccb8ebed2ae4ba50d`.
  Dependency/wheelhouse pin은 기존3dac82a… 그대로다.
  첫 non-root 도구 호출은 sudo 전 wheelhouse 경로 검사에서 PermissionError로 끝났으며
  parent admission/build에 진입하지 않았다. sudo로 시작하도록 호출을 수정한 뒤 격리 검증에 진입했다.
  이는 운영 재시작이나 동일 live 요청 재시도가 아니며 source archive를 변경하지 않았다.
- **Pi ARM64 exact-source full strict: 828 passed /9 skipped**, failures0/errors0/xfail0.
  Build/test/manifest155.334초. 9개 모두 Node.js 없는 Pi에서 의도된 Watch browser harness이며
  Windows837 결과의 동일 testcase 이름과 대조하여 **9개 모두 PASS**, 예상 밖 skip0 확인.
  시나리오: iframe-independent-presence, empty-player-protocol, hydrate-before-player,
  recoverable-return, terminal-stays-closed, page-lifecycle, bounded-reconnect,
  return-open-probe, select-before-player. 실제 Chrome public-path 확인은 별도 live gate로 남는다.
- 준비된 immutable release **`r-2c768ec98d1fc8b1-3dac82a792fad576`**.
  Manifest17406 files, SHA256 `e201e8291798bedb23444472bf6430147b34d2f7629d927f6327a0531f893bce`,
  schema range[5,5], immutable validation PASS.
  Dependency hash `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6` 유지.
  Discord/Watch UID999 및 Operations UID997의 configuration/secret format/exact scope/
  read-only mount PASS, 원본 credential 직접 접근 denied. Network login/DB open은 하지 않았다.
  Stage **verified_not_activated**, current d14 pin/DB1d871…/config/전체 protected inventory 및
  다섯 preservation 불변. 별도 service 조회도 production pair MainPID0/inactive/boot disabled,
  backup/update/manual services inactive와 세 timers inactive/disabled를 확인했다.
- 새 runtime range dd5d9aa→2c768ec: **3 commits /14 files /15 new blobs**,
  모든 commit tree/message/new blob 검사 PASS, forbidden artifact/secret/binary data finding0.
  전체 source ancestry의 기존 synthetic fixture/path finding8개는 원격 base와 동일, 새 finding0.
  최종 docs commit을 포함한 range는 승인 요청 전과 실제 push 직전에 재검사한다.
- 기존 승인 범위는 d14 runtime과 그 뒤 두 보고 문서뿐이다. 새 runtime push/production pin은
  Pi 검증 및 최신 보고를 마친 뒤 별도 단일 승인 대상으로 제시한다.
  원격 `codex/rebuild-v2=dd5d9aa17516ce1639db488964f113383eb8daf6`,
  `main=8432fdef40cddc131176fa875e350660dc897e12` read-back 일치, 새 push/activation 없음.
  승인 대상은 위 source2c768ec와 이후 phase report/current plan만 변경한 docs-only commit까지의
  일반 FF push 및 위 새 pin으로 최신 DB를 사용하는 live retry다. Source 이후 runtime/dependency
  변경이 없는지 push 직전 재검사하며 force/rebase/history rewrite는 하지 않는다.
  다음 시작도 compatibility→70초 readiness/Gateway/sync→commands/Favorites/volume→Music URL/search/
  실제 청취/stop·퇴장→**입장 TTS 사용자 실제 청취·덮어쓰기 없음·이후 Music**→필요 시 연속 TTS/pause→
  PC Chrome Watch create/connect/presence/refresh/reconnect/tab return/hydration/sync/close/
  private admin close→Cloudflare public path 순서로 확인한다. Provider 회복은 미확인이므로
  Summary 재실패 시 개선된 guard로 즉시 정지·새 보존하고 분석을 계속한다.
  필수 live gates → actual newest production backup/publication/read-back/independent restore →
  boot/4h backup timer → bounded observation 순서를 유지한다. Audit/PHASE11/V1 삭제는 하지 않는다.
- Safe evidence: `/home/os/discordbot-phase10/summary-failure-categories-d14eba80.json`,
  `summary-stopped-inspection-d14.json`, `tts-live-start.json`,
  `/var/tmp/phase10-retry-d14eba80bdec9126-live-smoke/summary.json`.
  Pi build: `/home/os/discordbot-phase10/retry-build-2c768ec98d1f.json`.
  Windows evidence: `scratch/phase10/summary-ui-full-windows.xml`, `summary-ui-exact-windows.xml`,
  `summary-ui-cross-platform-verification.json`, `tts-live-gates-stopped-summary.json`.

## Historical retry — APPROVED TTS RELEASE LIVE / REQUIRED SMOKE IN PROGRESS

2026-09-19 사용자가 source `d14eba80bdec912615d9bcc8ba22005b2aec3929`와 새 pin의 live retry를 승인했다.
**PHASE10 INCOMPLETE**. 사용자 실제 청취와 PC Chrome public-path 확인을 포함한 필수 smoke를 진행한다.

- Push 직전 source d14 이후 모든 commit을 검사하여 phase report/current plan만 변경한 docs-only
  `dd5d9aa17516ce1639db488964f113383eb8daf6` 한 개임을 확인했다. 전체 range2e008→dd5d9:
  4 commits / 7 files / 10 new blobs, 모든 commit tree/message/blob secret·금지 artifact 검사 PASS.
  일반 fast-forward push 완료와 원격 exact HEAD read-back 일치.
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변. Force/rebase/history rewrite 없음.
- Production pin **`r-d14eba80bdec9126-3dac82a792fad576`** 활성화. Application/runtime/dependency는
  검증된 source d14 그대로다. 운영 helper는 별도 작업 디렉터리에 두며 immutable release를 수정하지 않았다.
- 시작 전 canonical DB28291bf…와 config41edd03… 및 data/state/cache/backups/audit/config,
  네 preservation의 모든 file inventory hash 불변을 확인했다. Schema5 application compatibility,
  manifest17403 files/hash6ea4e46…/schema[5,5] 재검증 PASS.
  DB restore/promote/replay/remigration/down-migration 및 V1 시작 없음.
- 이전496 smoke marker는 root 소유·정확한 release·정지 보존 evidence·이전 guard 비활성을
  확인한 뒤 새 marker로 교체했다. 새 고유 감시 디렉터리를 사용하고 이전 evidence는 유지했다.
  별도 operator stop 요청 파일을 감시하여 사용자 실패 보고 시 추가 sudo 인증 없이 정지·새 보존한다.
- 시작 **10:08:21.626Z** → ready **10:08:46.483Z**, **24.821초 / 70초 PASS**.
  Discord/Watch active, 같은 release, Result success / NRestarts 0.
  Discord ready는 실제 Gateway ready 및 `tree.sync()` 완료 뒤에만 true인 구성을 확인했다.
  새 30분 bounded live guard 실행. 초기 diagnostics 오류0, 두 DB probe와 ready 정상.
- Cloudflare configuration은 `watch.lgw323.com → http://127.0.0.1:9000` 단일 route,
  internal port public route0. 실제 Chrome public-path gate는 아직 미확인이다.
- Commands3개/Favorites/volume 사용자 결과 대기. 이 release의 Music/TTS 실제 청취 및
  Chrome Watch/private admin close를 아직 PASS 처리하지 않았다. 기존496의 Music PASS는 과거 evidence다.
  필수 smoke가 모두 PASS하기 전 actual production backup/publication/read-back/restore를 실행하지 않는다.
  Boot/4h backup timer는 disabled, auto-update OFF. Audit/PHASE11/V1 삭제 없음.
- Safe evidence: `/home/os/discordbot-phase10/tts-live-start.json`,
  `/var/tmp/phase10-retry-d14eba80bdec9126-live-smoke/summary.json`.

## Historical preparation — TTS REPAIRED / VERIFIED RELEASE / PUSH-PIN APPROVAL PENDING

2026-09-19 승인된4963982 release의 사용자 smoke에서 Music URL/search/실제 청취까지 통과했으나,
사용자가 **봇 입장 안내 없이 바로 음악이 시작되는 TTS 실패**를 보고했다. 서비스를 정지·새 상태 보존했고,
사용자 지시대로 분석·격리 재현·수정·Windows/Pi 검증과 새 immutable release 준비까지 완료했다.
**PHASE10 INCOMPLETE**이며 새 commit push와 production pin/live 재시도 승인을 기다린다.

### Actual live gates and newest preservation

- 사용자 PASS: `/내정보`, `/랭킹`, `/요약`, 💾 보관함, footer 볼륨100%, 저장된 재생 상태 복원 청취,
  새 URL 요청, 검색어·선택·대기열 추가·실제 재생, ⏹️ 정지·음성방 퇴장.
- TTS FAIL: 봇이 사람이 있는 음성방에 들어올 때 입장 안내가 들리지 않고 음악으로 진행한다는 사용자 확인.
  TTS 생성/첫 PCM/Voice acceptance telemetry는 실제 청취 PASS로 취급하지 않는다.
- Watch Chrome create/connect/presence/refresh/reconnect/hydration/close 및 실제 public-browser gate는 미진행.
  Cloudflare configuration의9000 단일 route 확인은 보존하되 browser 성공과 구분한다.
- Production encrypted backup/Bot-Data publication/read-back/isolated restore, boot enable/4h timer와
  post-cutover observation은 **미진행**. Auto-update OFF. Audit0/1–10/Integrated Audit/PHASE11/V1 삭제 없음.
- 현재 pinned release는 `r-49639828a3c2f181-3dac82a792fad576` 그대로이며 Discord/Watch inactive,
  MainPID0/Resultsuccess.09:23:51.777Z는 정지 helper invocation identity다.
- 새 preservation:
  `/var/lib/discordbot/phase10-retry-49639828a3c2f181-operator-failed-20260919T092351777156Z/`.
  Canonical와 새 copy DB SHA256 **28291bf37128dd62815c818ac45865c8a504cc04a2b3dbb9a8a564d8226dab1d** 일치.
  정상 정지 후 WAL/SHM/journal 없음. Data/state/cache/backups/audit/config의 모든 file byte 비교 PASS,
  기존52d2ef…/fab61b…/fdc1aca… 세 preservation 및 config 불변. 이전 DB restore/replay/promote 없음.
- Safe evidence: `/home/os/discordbot-phase10/media-live-stop-20260919T092351777156Z.json`,
  stage `stopped_preserved_verified`.
- 최신 read-only 검사에서 schema 5 / integrity PASS, favorites 40 rows / 3 owners,
  music_play_counts 53, music_settings 1, users 15, watch_playlists 0 / watch_sessions 0.
  Data checksum `d18b9cda3f385875f1482bcdb08a6a9a85adc57f3feb6c1430e190a27c15b256`,
  metadata checksum `c41c3b85f39bcbfba1cd9145fb8fd65e2e9406e8e35a3df198545a51f020b0ad`.
  Config SHA256 `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 유지.
- 최초 유한 guard는1800.551초 정상 완료했다. 그 후 사용자 응답 시점에 새 `live-continuation` guard를
  설치했으며 시작 시 전체 startup 이후 safe journal을 재검토했다. 두 guard 사이 관찰 공백이 있었고,
  root fail-fast marker는 유지됐다. 이번 실패는 typed error 없이 안내가 덮이는 동작이므로
  자동 guard가 감지한 오류가 아니라 사용자 청취 보고로 정지한 것이다.

### Reproduced TTS ordering defects and repair

- Live safe event 순서: join-tts 성공 → TTS 취득/PCM/Voice acceptance → lookup 완료 → Music
  prepare/start/PCM/Voice acceptance. 해당 입장 TTS의 completed callback은 없었다.
  TTS acceptance 09:21:33.587308Z → lookup 완료 09:21:33.679284Z → Music acceptance
  09:21:33.761019Z로, 안내 시작 수락 뒤 **0.173711초** 만에 음악이 수락됐다.
  실제 순서를 사용한 network/DB 없는 deterministic regression은 수정 전 실패했다.
- 확인된 코드 결함: current song이 없는 입장 TTS 도중 lookup/추가가 완료되면 `_enqueue → _advance`
  경로가 TTS attempt를 음악 attempt로 교체한다. 중복 connect의 queued Music 진입도 같은 위험이 있었다.
  별도로 곡 없이 TTS가 끝나면 `tts` 상태가 남아 다음 안내 generation을 막는 결함도 재현했다.
- `a77f43e`: 안내 생성/시작/재생 동안 pending Music을 유지하고 안내 완료 뒤 시작한다.
  안내 종료 시 idle로 전환하고 다음 안내 또는 Music을 이어간다. 생성 실패 시 정상 운영에서는
  대기 중 Music을 계속하며, live-smoke failure latch와 기존3초/8초 정책은 유지한다.
- `d14eba8`: 연속 안내 종료 뒤에도 기존 곡의 pause intent/재생 위치를 보존한다.
  직접 regression8개: lookup 완료 교차, idle 연속 안내, generating/starting/playing 중
  enqueue·connect, generation 실패 후 Music, queued announcements 뒤 Music, 연속 안내 뒤 pause 유지.
  Music 관련51개 PASS. 최종 Windows 전체 strict **821 passed /63.91초**, skip0/xfail0,
  기존 audioop deprecation1. 실제 DB/Discord/provider 호출 없이 격리했다.
- `8261076`: stopped build verifier의 current pin/최신 DB 및 네 preservation guard 갱신.
  Runtime source **d14eba80bdec912615d9bcc8ba22005b2aec3929**.
  Archive SHA256 `15d7cd1aa44e43797e2b10b396e20a55c6abcbfe6b485a751f1830231810b600`.
  Dependency pin/wheelhouse는 기존 검증3dac82a… 그대로다.
- 종료 시 `gateway-stop`의 `DataIntegrityError` 1건도 safe category로 확인했다.
  합성 파일만 사용하는 실제 DiskCache + 구/신 actor 비교에서 이전496 source는 안내를 덮은 뒤
  actor 종료 후에도 TTS lease 1개가 남아 cache close가 같은 오류 유형으로 실패했다.
  수정 d14 source는 안내를 완료한 뒤 Music으로 이어지고 lease 0개 / cache close PASS /
  잔존 task 0개였다. 이는 cache lease 누수의 재현·해소 증거이며, live 오류의 원문 메시지나
  stack은 수집하지 않아 live 종료 오류의 정확한 발생 위치까지 확정하지 않는다.
  최신 canonical DB 무결성 검사는 별도로 PASS했다.

### Verified candidate and single approval gate

- **Pi ARM64 exact-source full strict: 812 passed / 9 skipped**, failures 0 / errors 0 / xfail 0.
  Build/test/manifest 검증 154.309초. 9개는 Node.js 없는 Pi의 의도된 Watch browser harness이며,
  Windows 821 결과의 동일 testcase 이름과 대조하여 **9개 모두 PASS**, 예상 밖 skip 0개 확인.
  시나리오: iframe-independent-presence, empty-player-protocol, hydrate-before-player,
  recoverable-return, terminal-stays-closed, page-lifecycle, bounded-reconnect,
  return-open-probe, select-before-player. 실제 Chrome live gate는 별도로 남는다.
- 준비된 immutable release **`r-d14eba80bdec9126-3dac82a792fad576`**.
  Manifest **17403 files**, SHA256 `6ea4e46a6239766f6c5bab07308e1dc5c386d7d8db1f128fac54c2d0e150de4f`,
  schema range **[5,5]**, immutable validation PASS.
  기존 wheelhouse SHA256 `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6` 유지.
- Discord/Watch UID 999와 Operations UID 997에서 configuration/secret format/scope exact/
  read-only mount PASS, 원본 credential 직접 접근 denied. Network login/DB open은 이 검사에서 하지 않았다.
- Build stage **`verified_not_activated`**. Current pin496 / canonical DB28291b… / config /
  data/state/cache/backups/audit 및 네 preservation의 전체 protected identity 불변.
  Build 후 별도 service 조회도 Discord/Watch/staging/MainPID 0/inactive/boot disabled,
  backup/update/manual services inactive 및 timers inactive/disabled를 확인했다.
- 새 runtime/guard **3 commits / 8 new blobs** 및 각 commit tree/message의 secret-artifact scan PASS.
  전체 source ancestry의 기존 synthetic fixture/path 판정 8건은 원격 base와 같고 새 finding 0건이다.
  최종 보고 문서 commit까지 포함한 range는 승인 요청 전과 실제 push 직전에 다시 검사한다.
  원격 `codex/rebuild-v2`는 `2e008c37936a7077bb9b81e6f280cdc138297d58`,
  `main`은 `8432fdef40cddc131176fa875e350660dc897e12`로 재확인했다. 새 push/activation 없음.
- 승인 대상은 위 runtime source의 새 pin과 보고 commit을 포함한 일반 fast-forward push다.
  Runtime source 이후 보고 commit은 phase report/current plan만 변경하며 release 내용은 바꾸지 않는다.
  DB/schema/config/dependency 변경 없음. Rollback은 우선 서비스 정지와 새 state 보존이며,
  이전 candidate/DB 자동 replay·restore, V1 시작, down-migration, history rewrite를 하지 않는다.
- 승인 후 최신 canonical DB로 compatibility → 70초 readiness/Gateway/command sync → commands3개 →
  Favorites/volume → Music URL/search/실제 청취/stop·퇴장 → **입장 TTS 실제 청취** → Chrome Watch
  create/connect/presence/refresh/reconnect/hydration/close → Cloudflare public 경로를 확인한다.
  모두 PASS한 뒤에만 actual encrypted backup → Bot-Data publication/read-back → isolated restore →
  boot enable/4h backup timer → bounded observation을 진행한다. 기존 smoke marker와 종료된 guard는
  새 시도 전에 상태를 확인하고 새 고유 guard를 설치하며, 이전 evidence를 덮어쓰지 않는다.
  실패하면 즉시 정지·새 보존하고 분석을 계속한다. PHASE10 COMPLETE/Audit/PHASE11 승인은 요청하지 않는다.
- Safe Pi evidence: `/home/os/discordbot-phase10/retry-build-d14eba80bdec.json`,
  `tts-stopped-inspection.json`, `tts-shutdown-categories.json`.
  Local ignored evidence: `scratch/phase10/tts-full-windows.xml`,
  `tts-cross-platform-verification.json`, `tts-cache-ownership.json`.

## Historical retry — APPROVED RELEASE LIVE / REQUIRED SMOKE IN PROGRESS

2026-09-19 사용자가 준비된 commit push와 새 production pin 재시도에 `진행`으로 승인했다.
**PHASE10 INCOMPLETE**이며 실제 사용자 기능 smoke를 진행 중이다. 아래 repair/build 절은 승인 전 이력이다.

- 최종 range368→`2e008c37936a7077bb9b81e6f280cdc138297d58`: 6 commits /29 new blobs,
  모든 commit tree/message 및 새 blob 검사 PASS. 금지 artifact/secret/운영 데이터 탐지0.
  기존 `codex/rebuild-v2`에 해당 exact commit까지 일반 fast-forward push 완료 및 원격 read-back 일치.
  `main=8432fdef40cddc131176fa875e350660dc897e12` 불변. Force/rebase/history rewrite 없음.
- 새 production pin **`r-49639828a3c2f181-3dac82a792fad576`** 활성화.
  Runtime source4963982와 push HEAD2e008c3 사이에는 검증 보고 문서만 있으며 runtime 변경은 없다.
  Manifest17402 files/hash961e33dd…/schema[5,5]를 재검증했다.
- 시작 직전 canonical DB `fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f`,
  config41edd03a… 및 canonical data/state/cache/backups/audit/config와 세 기존 preservation의
  전체 file inventory hash 불변을 확인했다. Schema5 application compatibility PASS.
  DB promotion/restore/candidate replay는 하지 않았다. 이후 정상 live write는 현재 canonical에 적용된다.
- Root-owned `/run/discordbot-live-smoke` marker를 **시작 전에** 생성했다.
  서비스 시작08:43:21.886Z → ready08:43:47.569Z, **25.648초 /70초 gate PASS**.
  Discord/Watch 모두 같은 새 release, active/Resultsuccess/NRestarts0.
  Discord readiness는 실제 Gateway ready와 `tree.sync()` 완료 후 deferred initialization을 요구한다.
- 저장된 Music 복원은 live `voice_connected → media_acquired → cache_leased → ffmpeg_started →
  first_pcm → playback_accepted → playback_ended/completed`를 통과했다.
  사용자가 게임 중 봇 입장과 **실제 음악 청취를 확인: audible Voice PASS**.
  같은 새 release의 **💾 보관함 열림 PASS**, UI footer **볼륨100% 표시 PASS**도 사용자 확인했다.
  이는 복원 playback에 대한 live 성공이며 새 URL/search 요청·선택·대기열 추가·stop 검사는 별도로 남는다.
  30분 유한 live guard를 설치했으며 첫 Music 실패 때 admission/retry를 막고 즉시 정지·새 보존한다.
- Cloudflare 현재 configuration event에서 `watch.lgw323.com → http://127.0.0.1:9000` 단일 route,
  internal port public route0 확인. Chrome 실제 연결은 아래 live 사용자 gate로 남아 있다.
- 08:58Z 확인: 두 서비스 active/Resultsuccess/NRestarts0, 851.701초 관찰에서 ready2/2,
  Music allowlisted error0/guard trigger 없음.
- 새 release의 commands/Music URL·search·선택·추가·stop/TTS/Chrome Watch 확인 대기.
  Actual production encrypted backup/Bot-Data read-back/isolated restore/boot enable/4h timer/
  bounded post-cutover observation은 아직 실행하지 않았다. Backup/update/manual timers inactive/disabled.
- Safe start evidence: `/home/os/discordbot-phase10/media-live-start.json`.
  Safe guard evidence: `/var/tmp/phase10-retry-49639828a3c2f181-live-smoke/summary.json`.

## Historical preparation — MEDIA REPAIRED / VERIFIED RELEASE AWAITING PUSH-PIN APPROVAL

2026-09-19 사용자 변경 지시에 따라 live 실패 뒤 정지·보존 상태에서 원인 분석, 격리 재현,
코드 수정과 검증을 계속했다. **PHASE10 INCOMPLETE**이며 새 production pin/live 재시도는 아직 미승인이다.
현재 canonical DB를 복원·승격·replay하지 않았고 V1을 시작하지 않았다. 아래 과거 실패 기록은 이력을 보존한다.

### Confirmed acquisition cause and repair

- 승인368 release의 Python3.12.3 / yt-dlp2026.7.4 / service UID / cwd / sandbox를 사용했다.
  운영과 같은 cache 경로에는 격리 디렉터리를 bind mount하여 실제 cache와 DB를 변경하지 않았다.
  대조 public clip은 acquire309288 bytes → PCM3840 bytes → fake VoiceClient → Opus96 bytes PASS.
  실제 실패 class는 metadata 성공 뒤 **download HTTP403 / child exit1**로 재현됐다.
- 기존 pin에서 WebM 선택도403, HLS audio 선택은 no_audio_format이었다. Deno2.9.7/EJS0.8.0을
  추가한 기존 pin도403이었다. 따라서 단순 M4A 선택 또는 JS runtime 추가만으로 해결되지 않았다.
- yt-dlp **2026.8.19**에서는 동일 실패 class가 JS runtime 활성화 전후 모두 acquire2525278 bytes,
  PCM3840 bytes, fake VoiceClient acceptance, Opus96 bytes까지 PASS했다. 종전 pin의 provider 경로
  compatibility 실패가 재현·해소됐으며, YouTube 내부의 구체적인403 정책까지 확정하지 않는다.
  실제 Discord audible Voice 성공을 이 격리 결과로 대체하지 않는다.
- 새 pin과 함께 기존 sealed inventory에 빠졌던 호환 EJS0.8.0, 공식 Deno2.9.7을 포함한다.
  Adapter는 release-local Deno를 명시하며 remote component download를 금지한다. 다른58 artifacts는
  hash 그대로 유지했고 기존 wheelhouse와 release를 보존했다. 이는 dependency 전체 최신화가 아니다.
- Provider stderr는 그대로 출력·보관하지 않는다. 오류에는 executable/start/I/O, child_nonzero,
  provider/auth/format, HTTP403/download, timeout, invalid/empty output, cache write/publish 등
  allowlisted reason과 -255..255 child exit code만 기록한다. Track/title/URL/user ID는 기록하지 않는다.
- Safe probe evidence: `/home/os/discordbot-phase10/media-boundary-01.json`부터 `04.json`까지.
  모든 비교에서 canonical/state/cache/audit/config 및 최신 preservation hash 불변, 서비스 정지 확인.
  FFmpeg exit255는 첫 PCM 확인 뒤 의도적으로 terminate/reap한 결과이며 provider 실패가 아니다.
- 참고: [upstream provider release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19),
  [EJS installation contract](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

### Independent fixes and regression

- `e1501fc`: discord.py2.7.1 Webhook.send에 unsupported delete_after를 보내지 않는다.
  followup은 wait=True로 받은 메시지를 bounded supervisor에서 삭제한다. HTTP 호출 전 signature
  오류에는 단일 fallback이 가능하고, 호출 이후 결과가 불확실한 실패에는 중복 응답을 보내지 않는다.
- `7da55db`: Music provider pin/runtime 및 위 안전한 failure boundary 진단.
- `a023fbf`: root-owned `/run/discordbot-live-smoke` marker가 있을 때 첫 Music 실패에서 admission과
  retry를 닫고 current/queue를 보존한다. root guard의 journal 확인 간격은0.25초, health는5초다.
  marker 해제 후 정상3초/8초 정책을 사용하며 실패 latch는 restart 전까지 유지한다.
- `75d5481`: stopped verifier가 최신 DB와 세 보존본 및 모든 보호 state/config inventory를 전후 비교한다.
  separate reviewed wheelhouse에서 exact source를 offline build/test하며 current를 활성화하지 않는다.
- `4963982`: 실제 SDK ViewStore를 통한 Favorites 의미/공용 목록/pagination/owner/expiry/교체 회귀6개.
- 기존 TTS absolute standalone worker와 Watch iframe-independent WS/presence/hydration/lifecycle/
  bounded reconnect/terminal close 구현은 유지했다.
- Windows 새 provider/EJS/Deno의 별도 test venv에서 전체 strict **813 passed /66.31초**,
  skip0/xfail0, 기존 audioop deprecation1. 테스트는 실제 DB/외부 service를 사용하지 않았다.
  Watch Node harness9 scenarios도 모두 PASS했다.

### Production state and approval boundary

- Current approved/pinned release는 여전히 `r-368c8ebf7cbff244-d026a47ed4f4b38a`다.
- Canonical DB SHA256 **fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f**.
  최신 preservation `/var/lib/discordbot/phase10-retry-368c8ebf7cbff244-favorites-resume-guard-preservation/`.
  기존52d2ef…/fab61b… 보존본도 유지한다. Schema5/integrity PASS, favorites40/3 owners, settings1,
  play_counts51, users15의 기존 안전한 검사 evidence를 유지한다.
- **Favorites gate PASS**: 사용자가 실제 💾 보관함 열림을 확인했다. 추가 production favorite를
  만들지 않았고 더 이상 blocker로 취급하지 않는다. 새 release live에서의 단순 회귀 확인은 별도다.
- Source/build candidate: `49639828a3c2f181e87a3cfffd5d5f80f47b359a`.
  Archive SHA256 `39eea24a22e4113d024ef874780de499b0b9741cc9c12a264fd36712675e457a`.
  New wheelhouse SHA256 `3dac82a792fad5769f4e6b32cdd0c294fbfbb4863500e8e232f85b47b3297cc6`.
- **Pi exact-source full strict: 804 passed /9 skipped, failure0/error0/xfail0**. Build+verification149.839초.
  Skip9개는 Node.js가 없는 ARM64 worker에서 의도된 shipped Watch browser harness이며,
  Windows813 전체 검사에서 동일9개가 모두 PASS함을 JUnit 이름으로 대조했다. 다른 미검증 skip 없음.
- Immutable release **`r-49639828a3c2f181-3dac82a792fad576`**, manifest17402 files, schema range **[5,5]**.
  Manifest SHA256 `961e33dd6acc82fa608efefbd3ed5a24cbaa2b6d0cfb011ddb32a3f6f2f078e9`.
  Discord/Watch UID999, Operations UID997의 credential scope exact/read-only mount PASS,
  원본 secret 직접 접근 denied. Network login/DB open은 credential 검사에서 하지 않았다.
  Build stage `verified_not_activated`, canonical 및 세 preservation 포함 protected state 불변.
- **Exact release media probe PASS**: 대조 clip/search3 결과/기존 실패 class/synthetic TTS.
  기존 실패 class acquire2525278 bytes → PCM3840 → fake Voice → Opus96,4.624초.
  Synthetic TTS8832 bytes → 동일 PCM/Opus,0.539초. 모든 child 회수, remaining0.
  같은 production cwd/cache path를 private mount로 격리했고 credentials/Discord login은 사용하지 않았다.
  실제 Voice 청취 및 실제 Discord TTS는 여전히 승인 뒤 live gate다.
- Safe evidence: `/home/os/discordbot-phase10/retry-build-49639828a3c2.json`,
  `media-wheelhouse-verification.json`, `media-boundary-05.json`.
- 최종 read-only 상태: Discord/Watch/staging inactive, MainPID0/NRestarts0/boot disabled,
  backup/update/manual timers inactive/disabled,9000/9001/9010/9011 listener0.
  Current pin368 유지. Config SHA256 `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`.
- 새 runtime range368→496의 모든5 commit tree와27 new blobs/message 검사 PASS:
  실제 secret/.env/DB/SQL/backup/private key/credential/운영 데이터 artifact0.
  전체 ancestry 검사760 blobs/1744 objects는 기존 승인 때 검토한8개 fixture/path false positive만 동일했다.
  최종 보고 문서 commit까지 포함한 range를 push 승인 요청 전에 다시 검사한다.
- 원격 `codex/rebuild-v2`는368c8eb 그대로, `main`은8432fdef40cddc131176fa875e350660dc897e12 그대로다.
  새 commit은 로컬에만 있으며 일반 fast-forward push와 이 검증된 release의 production pin 적용을
  **한 번의 사용자 승인 gate**로 요청한다. Rebase/force/history rewrite는 없다.
- Actual live gates: 70초 readiness, commands, Favorites/volume, URL/search audible Music, stop/disconnect,
  TTS, Chrome Watch 전체 behavior와 Cloudflare public path는 새 pin 승인 뒤 순서대로 수행한다.
  모두 성공한 뒤에만 actual production encrypted backup → Bot-Data publication/read-back →
  isolated restore → boot/4h backup timer → bounded observation을 진행한다. Auto-update는 OFF 유지.
- 실패 시 즉시 stop/preserve하되 Codex는 원인 분석·수정을 이어간다. 새 code activation 시에만
  다시 push/pin 승인을 요청한다. Candidate replay/old DB restore/down-migration/V1 시작은 금지한다.
  Audit0/Audit1–10/Integrated Audit/PHASE11/V1 삭제는 진행하지 않는다.

## Historical continuation — MUSIC PREPARATION FAILED / SERVICES STOPPED

2026-09-19 사용자 후속 지시에 따라 아래 stopped retry 상태에서 이어서 진행한다.
Cutover/DB 승격을 반복하지 않는다. Production source/commit/pin은 승인된368 그대로이며,
새 코드는 테스트6개만 추가했다. **PHASE10 INCOMPLETE**다. 사용자가 URL 재생 시 음성 채널 이탈과
준비중 표시를 보고했고, guard가 Music 준비 실패를 감지해 자동 정지·새 상태 보존을 완료했다.
07:32:48.839Z는 guard 완료 결과 파일의 mtime이며,07:35:50Z readonly 검증에서 정지·보존 일치를
확인했다. 사용자 지시대로 추가 수정·재생·재시작 없이 보고 후 중단한다.

### Confirmed failure sequence

| UTC | Safe event / interpretation |
| --- | --- |
| 07:32:39.758 | `music.request_received / ui_request`1회. 원문 URL·title·사용자 ID는 보고서에 기록하지 않음 |
| 07:32:40.063 | `music.voice_connected / voice_connection`, 이어서 lookup 시작 |
| 07:32:41.902 | lookup 성공 → prepare 시작 |
| 07:32:41.903 | media acquisition 시작. 별도로 `music.ui_failed / request / internal` 발생 |
| 07:32:43.874 | **`music.work_failed / prepare / external_permanent`**, 재시도 대기 시작 |
| 07:32:46.876 | 기존 actor의3초 대기 완료 → 두 번째 prepare/acquisition 실행 |
| 07:32:47.243 | 두 번째 **prepare / external_permanent** 실패. 다음 retry 대기 시작 |
| 07:32:48.839 이전 | Guard `music_failure`로 pair stop·보존 완료. 추가 retry 완료/세 번째 prepare 기록 없음 |

이번 요청의 확인된 실패 경계는 **metadata 조회 이후, cache에 사용할 media 준비/취득 단계**다.
`media_acquired`, `cache_leased`, `ffmpeg_started`, `first_pcm`, `playback_accepted` 기록은0회다.
오류 전후 내부 health/DB probe는 정상이고 NRestarts0이므로 서비스 crash/restart 증거는 없다.
음성 채널 이탈은 guard의 안전 정지와 함께 관찰되었으며, 이탈 자체를 최초 Voice transport 실패로
확정하지 않는다. 실제 audible audio는 FAIL; 검색어 재생·정상 stop/disconnect smoke는 미진행이다.

`external_permanent`는 subprocess 비정상 종료/실행 실패 등 여러 경로가 공유하는 코드다.
현재 수집된 안전한 evidence에는 child exit code나 허용 목록으로 분류한 stderr 원인이 없어
YouTube 제한/HTTP403/format/프로세스 실행 환경 중 하나를 원인으로 확정할 수 없다.
Watch의 별도 Cloudflare1010 증거를 Music 다운로드 원인으로 연결하지 않는다.

별도로 승인 source의 `MusicController.request` → `Responder.send`는 deferred followup에
`delete_after=5`를 전달한다. 설치된 Windows discord.py2.7.1의 실제 `Webhook.send` signature는
그 인자를 지원하지 않으며, network 없는 signature binding에서 **TypeError**를 확인했다.
이는 확인된 SDK API 계약 불일치다. `Responder`는 첫 send 실패 전에 finished를 설정하므로
catch 뒤 fallback send도 생략될 수 있다. 다만 live `request/internal` telemetry에는 exception type이
없어 그 기록과 이 TypeError의 동일성을 직접 확정하지 않는다. 이 API 불일치는 별도의 media 취득
실패 원인을 설명하지 않는다. 운영 코드 수정이나 새 release/push는 이번 실패 후 실행하지 않았다.

**Fail-stop 관찰의 한계:** agent/user의 추가 재생 요청은 없지만, 기존 actor는 첫 실패 후3초에
자동 재시도1회를 실행했다.5초 주기의 운영 guard가 이를 첫 실패 직후 차단하지 못했고, 두 번째
실패 뒤 두 서비스를 멈췄다. 따라서 자동 재시도0회라고 보고하지 않는다. 재시도 허용 정책과
최초 오류 차단 시점은 다음 별도 승인 작업에서 함께 조정해야 할 확인된 공백이다.

### Newest state preservation and final gates

- 최신 보존본: `/var/lib/discordbot/phase10-retry-368c8ebf7cbff244-favorites-resume-guard-preservation/`,
  mode0700. Canonical와 copy DB SHA256
  `fdc1aca74b5bb65ce9ebd511e32b83a6b31e249246dffafd962c2c0eb15ece9f`,143360 bytes 일치.
  Schema5/integrity PASS, favorites40/3 owners, music_settings1, music_play_counts51, users15, Watch0/0.
  정상 정지 후 WAL/SHM/journal sidecar 없음; 기존 DB를 복원하거나 sidecar를 삭제하지 않았다.
- Data1/143360 bytes, state1/695, cache1/279075, backups0/0, audit146/30225, config17/3667의
  inventory 및 모든 file byte hash copy 일치를 확인했다. 저장된 release도 승인368과 일치.
- 최신 semantic checksum `42ab8fe5d77a4d9677a16498816f486fa1c5d5d954f608a1976122e832f3c17f`,
  metadata checksum `3eab85922494f7e0dd52cbe963d66b1a1a26bdfe7ae18ca26f9c42cec59fa225`.
  Config hash41edd03a… 그대로. 이전52d2ef… 및fab61b… 보존본 DB hashes 모두 불변.
- Production/staging/ops6 services inactive/MainPID0, production pair Result=success/NRestarts0.
  Runtime/staging boot disabled, backup/update/manual timers inactive/disabled, ports9000/9001/9010/9011
  listeners0. Current pin은 승인368을 유지한다. Candidate replay/old restore/down-migration/V1 시작 없음.
- Safe failure evidence `/home/os/discordbot-phase10/music-failure-verification.json` 및
  `/var/tmp/phase10-retry-368c8ebf7cbff244-favorites-resume/{summary.json,samples.jsonl}`.
  Guard summary의 `last.services/health`는 정지 직전 sample이다. 최종 상태는 guard result와 후속
  readonly 검증의 inactive/MainPID0가 우선한다.
- Guard 관찰 실제1282.760초/222 samples. Health bad0/release mismatch0/probe error0/restarts0,
  DB recent failures0/telemetry drop0. Discord/Watch max RSS85056/68716KiB, FD15/12, threads8/4;
  Music child max1, Watch session/client max0. 이는 실패 전 smoke 관찰이며 post-cutover 성공 관찰이 아니다.

| Required live/final gate | Final outcome |
| --- | --- |
| Latest production integrity / exact approved release / Gateway / sync | PASS, 위 safe evidence 및25.567초 readiness |
| `/내정보`, `/랭킹`, `/요약` | 직전 동일368 시도에서 사용자 PASS. 이번 빠른 재확인의 별도 응답은 받지 못함 |
| Favorites | **사용자 보관함 열림 확인**. 최신 DB40/3 owners 유지. 목록의 개별 기존 항목 일치 확인은 별도 응답 없음. 실제 owner별 목록10/17/13개로 모두1 page; synthetic26/101 pagination PASS |
| Volume | 직전 동일368에서100% 표시 확인. 이번 재확인 별도 응답 없음 |
| URL Music / actual audible Voice | **FAIL — prepare/acquisition external_permanent**, 실제 오디오 성공 확인 없음 |
| Search Music / normal stop-disconnect / TTS | 실패 후 미진행 |
| Watch Chrome presence/refresh/reconnect/hydration/close/admin-close | 미진행; public browser/WSS PASS 아님 |
| Cloudflare public path | Route9000/origin ready PASS; Python public403/1010. 실제 Chrome 결과 미확인 |
| Actual canonical encrypted backup / Bot-Data read-back / isolated restore | 필수 smoke 실패로 미실행 |
| Backup timer / boot / post-cutover observation | 미실행·비활성 유지. Auto-update/manual polling OFF |

Audit0/PHASE11/V1 삭제는 진행하지 않았다. 아래는 이번 continuation의 시작 전 검증과 시작 이력이다.

- 07:03:38Z Pi readonly reconciliation PASS: runtime/staging/ops6 services inactive/MainPID0,
  backup/update/manual timers inactive/disabled, port9000/9001/9010/9011 listeners0.
- Current release368, canonical/latest preservation DB fab61b… 일치. Schema5/integrity/application
  readonly copy open/close PASS, 검사 전후 원본 hash 유지. Favorites40/3 owners, settings1,
  play-count rows51, users15, Watch0/0 유지. Data loss로 분류하지 않는다.
- Data checksum `bd3d4b0f3a4d808719f6e35bfc95390322c496b6694bdd7aeb51e349f9f6ca54`,
  metadata checksum `1ec0e7acf5d31a5474b9b1bd1b4dbaa352d6a48d93c43d5cba8f7bfc109e9619`.
  Safe evidence `/home/os/discordbot-phase10/favorites-resume-inspection.json`.
- V1 retained `MusicPlayerView`와 V2 `build_dashboard`의 serialized component 비교: idle `⭐`
  disabled, 재생 곡 있음 `⭐` enabled, `💾 보관함` 항상 enabled. 둘 다 secondary(gray) style이다.
  `music:favorite`와 `music:favorites`는 별도 저장/목록 callback이며 색상이 disabled를 뜻하지 않는다.
- `tests/integration/music/test_favorites_dispatch.py`의6 tests PASS: 실제 SDK ViewStore dispatch,
  V1/V2 current 없음/있음 wire projection, 임시 SQLite26/101 favorites 사용자 공용 조회,
  25-option stable pagination, private response ACK/owner/expiry, ready storm45회 및3회 replacement,
  stale stop 이후 최신 handler 유지, typed failure response/log privacy. 실제 DB/Discord/network 미사용.
- Related Music/contract/architecture **117 passed/7.31초**; full Windows strict **777 passed/64.58초**,
  skip0/xfail0, 기존 audioop deprecation1. 운영 source diff0. 기존 approved ARM64 release와
  762 pass/9 intentional Windows-covered skips 증거 유지; 새 runtime release/push를 만들지 않았다.
- 동일 release manifest·DB·config·route 재확인 뒤07:10:59.797Z 시작,
  07:11:25.369Z **25.567초/70초**에 양쪽 live/ready 동일368, NRestarts0 PASS.
  pin/DB 교체 없음. Safe result `/home/os/discordbot-phase10/favorites-resume-start.json`.
  새 finite guard: `/var/tmp/phase10-retry-368c8ebf7cbff244-favorites-resume/`.
- 사용자가 **보관함 열림**을 실제 확인했다. 따라서 현재 `💾 보관함`의 disabled/callback 불능으로
  판정하지 않는다. 나머지 표시·명령의 명시적인 확인을 요청했으나 추가 응답 없이 실제 URL
  Music 실패가 보고되었다. 사용자 응답에 없는 항목을 PASS로 추정하지 않으며 최종 결과는 위 표를 따른다.
- Public probe 분류: Windows 및 Pi의 Python HTTPS 요청은403, Windows 응답의 고정 code1010 확인.
  Origin9000은 HTTP200/ready=true. 현재 route는9000 그대로이며 내부 port public 노출0.
  [Cloudflare 공식1010 설명](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)의
  client browser signature 차단과 일치한다. Python probe 차단과 실제 Chrome smoke를 구분하며,
  임의 보안 설정/route 변경 또는 기존 과거 HTTPError의 동일 원인 확정은 하지 않는다.

## 10B retry — STOPPED AT FAVORITES CHECK / NOT PASSED

2026-09-19 새 세션은 첨부된 재개 지시와 repository evidence로 상태를 재구성했다.
시작 HEAD `5e2e57b`, branch `codex/rebuild-v2`, worktree clean. 아래 첫 실패 기록을 보존하며
**PHASE10은 미완료**다. 아래 최신 승인·실행 기록을 우선하며 첫 실패와 조사 이력을 보존한다.

2026-09-19 사용자가 exact368c8eb까지 일반 push와 release368 재시도를 명시적으로 승인했다.
현재 writes/failed-attempt/복구 evidence 보존, 70초 gate, live smoke 실패 시 정지·보존,
모든 smoke 성공 뒤 backup/restore와 boot/timer 순서 및 성공·실패 결과 보고 후 중단 조건을 유지한다.
최종 검사 후 **origin/codex/rebuild-v2를63c7722→368c8eb로 일반 fast-forward push 완료**했다.
원격 main은 `8432fdef40cddc131176fa875e350660dc897e12` 그대로다. Force/rebase/history rewrite 없음.
승인된 새 release로 현재 canonical DB를 사용해 시작했고 내부 readiness는25.363초에 통과했다.
사용자가 즐겨찾기 버튼의 계속된 비활성화를 보고하여 필수 smoke를 통과로 판정하지 않고
06:52:58Z(15:52:58 KST)에 두 서비스를 정상 정지했다. 최신 상태를 새 경로에 보존·검증했다.
**이번 재시도도10B 미완료이며, 사용자 지시에 따라 결과 기록 후 작업을 중단한다.**

### Latest retry execution and stop evidence

| Gate | Actual result |
| --- | --- |
| Config/schema/release compatibility | config41edd03a… / schema5 / approved immutable manifest PASS. Candidate 승격·DB 복원 없음 |
| Bounded readiness | 06:46:56.541Z start →06:47:21.904Z ready, **25.363초 /70초 한도**, 두 process live/ready 동일368 release, restart0 |
| Discord/Gateway/command sync | 내부 ready PASS. 승인 source의 ready는 Gateway `is_ready` 및 `tree.sync()` 완료 후 deferred started를 요구한다. 사용자 명령 응답도 확인 |
| `/내정보`, `/랭킹`, `/요약` | 사용자 세 항목 PASS 보고 |
| Favorites / volume | 사용자 즐겨찾기 버튼 계속 비활성 보고로 gate 중단. 볼륨100% 표시는 확인; 목록 열기/선택 및 볼륨 변경은 PASS로 판정하지 않음 |
| Music search/add/play/stop/actual Voice | 이번 순차 smoke에서 미실행. Startup `music.voice_connected`1회만 있으며 실제 오디오 전달/청취 성공을 뜻하지 않음 |
| TTS | 미실행 |
| Watch create/connect/presence/refresh/reconnect/close | 미실행 |
| Cloudflare | 시작 전 current invocation의 route1개가 `watch.lgw323.com → http://127.0.0.1:9000`; internal port route0. 외부 readiness 요청은 `HTTPError`로 실패했으나 status 미수집이어서 원인 미확정. 이번 공개 HTTPS/WSS PASS로 기록하지 않음 |
| Actual production encrypted backup / Bot-Data / isolated restore | 필수 smoke 미통과로 모두 미실행. 앞선 local recovery는 이 gate의 대체 증거가 아님 |
| Boot / backup timer / auto-update | runtime boot disabled, backup/update/manual timers disabled. 활성화하지 않음 |

Finite guard는1800초 계획 중 **330.637초/58 samples**에서 수동 종료했다. 전체58 samples에서
내부 health bad0/release mismatch0/probe error0/unexpected restart0, database recent failures0,
telemetry drop0, music child process0, Watch session/client0이다. 이는5분30초 관찰이며 장기 안정성
또는 미실행 기능 성공을 증명하지 않는다. Allowlisted journal에는 voice connection1회,
typed error code0만 있어 Music 음성 실패 원인은 이번 실행으로도 확정할 수 없다.

정지는 사용자 직접 sudo 인증 후 `retry-stop-favorites.py`로 실행했다.
`stopped_preserved_verified`, production/staging/operations6 services 모두 inactive/MainPID0,
production pair Result=success/NRestarts0 확인. Current pin은 승인368 release를 유지한다.
최종 추가 확인에서 backup/update/manual timers 모두 inactive/disabled이고,
9000/9001/9010/9011 TCP listeners는0개였다.

- 새 보존 경로: `/var/lib/discordbot/phase10-retry-368c8ebf7cbf-favorites-failed-20260919T065256492640Z/`.
- Canonical와 새 copy DB:143360 bytes, SHA256
  `fab61bdda1dd2c8b664c5fd19525d1cdd46f20c82d630a94ce2ed4caf6f5cc65` 일치.
  정상 종료 후 WAL/SHM/journal sidecar는 존재하지 않았다. 살아 있는 DB의 강제 copy/삭제는 하지 않았다.
- Data1 file/143360 bytes, state1/430, cache1/279075, backups0/0, audit146/30225,
  config17/3667의 파일 목록·byte hash copy 일치 검증 및 fsync 완료. 원문/credential은 전송·출력하지 않았다.
- 이전 failed-attempt DB는 `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af`
  그대로이며 overwrite 없음. 최신 canonical은 기존52d에서fab61b로 바뀌었고 최신 상태 그대로 보존했다.
  이전 candidate replay, pre-cutover restore, down-migration, V1 시작, blind retry는 하지 않았다.
- Safe results: `/home/os/discordbot-phase10/retry-start-368c8ebf7cbf.json`,
  `/home/os/discordbot-phase10/retry-stop-favorites-20260919T065256492640Z.json`,
  `/var/tmp/phase10-retry-368c8ebf7cbff244-smoke/{summary.json,samples.jsonl}`.
  Guard summary의 `observing`은 중단 직전 snapshot이며 최종 상태는 stop result가 우선한다.

즐겨찾기 원인은 아직 미확정이다. Source상 현재 곡 저장용 `⭐`는 current가 없으면 disabled이고,
목록을 여는 `💾 보관함`은 별도 enabled control이다. 사용자 표현만으로 두 버튼 중 무엇인지,
Discord에 실제 전송된 disabled 값 또는 callback 수신 여부를 확정하지 않는다. 기존40 rows/3 owners와
격리 UI 생성 검사는 전체 row 소실 가설을 배제했지만 live 버튼 성공의 증거가 아니었다.
향후 별도 지시가 있으면 정확한 버튼 구분과 안전한 component disabled/custom-id 종류 집계,
current dashboard 교체/SDK dispatch 경로를 확인해야 한다. 현재 실행에서는 추가 수정·재시작하지 않는다.

- Push 직전 전체 ancestry pattern 검사733 blobs, 새 range24 commits의 모든 tracked tree 및 새66 blobs 검사.
  실제 secret/env/DB/SQL/backup/key artifact 발견0;8개 pattern은 앞서 검토한 경로/fixture이며 추가 탐지0.
  넓은 data-directory 규칙의11개 항목은 `tests/integration/data/*.py` 소스였고 실제 데이터 artifact가 아니다.
  Commit message pattern0. Safe local evidence: `scratch/phase10/final-push-audit-368c8ebf7cbf.json`.
- Pi skip9개와 Windows junit testcase명을 정확히 대조했다. 모두 의도된 Node harness이며
  push 직전 Windows에서 **9 passed/0.85초**로 재실행했다. 예상하지 못한 skip/미대응 항목0.

- 05:26:42Z read-only Pi 검사 PASS. Production/staging/operations 6 services 모두 inactive,
  MainPID0, backup/update/manual timers inactive/disabled. Current는 승인된63 release다.
- Canonical과 failed-attempt copy SHA256 모두 `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af`,
  각각143360 bytes, sidecar 없음, readonly immutable application validation/schema5 PASS.
  검사 전후 hash 동일, canonical 열린 FD0. 검사 중 Python1은 검사 worker다.
- Favorites40 rows/3 owners 유지; 모든40 항목이 V2 Track 검증을 통과했다. 소유자별 목록 UI는
  10/17/13 항목으로 생성되고 비활성 control0. 원문/ID/title/URL은 evidence에 출력하지 않았다.
  따라서 row 부재/전체 소실 가설은 배제한다. 실제 사용자 클릭 경로의 성공은 아직 재검증 전이다.
- `music_play_counts`는 candidate50→current51 rows. 현재 semantic/metadata checksum은
  `edbc7f07930dcde468583f5c86894f585944397e798a9603a24c3c1a0f2b26a4` /
  `0fe3ded1a0ac86cfb52284f406a24c6d411bb296f910c28133c2bab2d809c91d`.
  적어도 일부 playback-start write가 존재한다. 실제 audible audio 성공으로 해석하지 않는다.
- Config canonical/preserved SHA256 `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40` 동일.
  Cloudflare current invocation config event: 기존 Watch hostname route1개, origin9000,
  내부9001/9010/9011 route0. 해당 app listeners 없음. 재설정하지 않았다.
- 사용자 추가 관찰: 즐겨찾기 버튼이 회색/비활성으로 보임, URL·검색어 모두 Music 실패,
  Watch는 PC Chrome. V1보다 단순해진 jukebox UI에 대한 불만도 기록했다.
- 수정 전 Windows full strict **746 passed**,58.62초. 새 SDK ViewStore 회귀 test에서
  dashboard replacement 등록 뒤 old View.stop이 같은 message/custom_id의 새 callback까지 지우는
  결함을 재현했다. stop 순서를 교정한 관련 lifecycle10 tests PASS. Live UI 복구는 미검증.
- Watch shipped JS harness에서 iframe에 종속된 연결/presence, 빈 videoId 전송,
  iframe 준비 전 state 수신 유실, browser return/page lifecycle 미처리를 재현했다.
  서버 단독 viewer reload에서는 저장 playback hydration 누락을 playing/paused2 cases로 재현했다.
  서버 hydration과 iframe 독립 연결, 유효한 video/state 전송, 최대5회 bounded reconnect,
  visibility/page lifecycle 검사를 수정했다.4001/4002/4003은 terminal 유지,4008은 재연결 대상이다.
  30초 create/5초 empty grace, capability/Origin/CSRF/CSP와 mailbox/peer pump는 유지한다.
  Shipped JS harness9 cases와 playing/paused hydration2 cases를 추가했다. Public browser smoke는 미검증이다.
- TTS child의 `-m discordbot...`는 immutable launcher의 parent sys.path를 상속하지 않아
  다른 working directory에서 module import 실패함을 로컬 executable regression으로 재현했다.
  standalone worker 절대경로와 isolated Python 실행으로 교정했다. 실제 production TTS는 여전히 NOT TESTED다.
- 기존63의 isolated provider/PCM probe는 첫 고정 test URL metadata 단계에서
  `external_permanent`로 실패했다(1.062초). 당시 분류만으로 vendor 원인 또는 기존 live 실패 원인을
  확정할 수 없다. 다른 고정 public short clip으로 같은63 adapters를 검사한 두 번째 probe는
  URL metadata1개/search3개, acquire309288bytes, FFmpeg first PCM3840bytes,
  fake VoiceClient acceptance, real Opus encode96bytes, stop/reap(child0)를5.139초에 통과했다.
  TTS import-only probe는 module missing(exit1)을 확인했다. 실제 Discord 음성 전달/청취 검증은 아니며,
  첫 live Music 실패의 단일 원인은 아직 미확정이다.
- Music request/enqueue/lookup/acquisition/cache lease/voice connect/FFmpeg/first PCM/accept/callback에
  고정 stage/result, typed code와 생성 work ID를 기록한다. raw exception/context/title/URL/ID는
  기록하지 않으며 synthetic 실패·cache hit/miss 회귀 검사로 확인한다.
- 사용자 명시적 요청에 따라 jukebox의 V1 cyan/idle gray, thumbnail, 상태·진행 막대와 stored volume,
  반복/자동재생/다음 곡 표시를 복원한다. 버튼 기능·배치와 사용자 공용 즐겨찾기 semantics는 유지한다.
- Windows 수정 후 전체 strict769 passed/56.66초(후속 cache 진단1 test 추가 전), 관련181 passed/10.73초.
  최종 코드 전체 strict **770 passed/56.82초**, skip0/xfail0. 기존 audioop deprecation warning1 외
  RuntimeWarning/unraisable 없음. Pi exact-source build는 다음 gate다.
- `verify-stopped-release.py`는 현재 DB/config/release와 모든 writer/timer stopped를 guard하고,
  operation lock 아래 offline wheel build, 격리 full strict(operations/architecture 포함), immutable manifest,
  설치된 production config의 세 credential scope를 검사한다. Source export에는 legacy test 지원만 포함하고
  실제 data/env/backup/log/key는 제외한다. Node가 없는 Pi의 JS harness skip은 Windows 실행 결과와 구분한다.
  이 도구는 pin/DB/config/service를 활성화하거나 변경하지 않는다.
- First retry source `080e19022393a3939d8ad4649523b205220a5232`: ARM64 offline build143.119초,
  full strict761 passed/9 skipped(Node 없는 Pi의 JS harness), failures/errors0,
  immutable manifest17338 files/schema5 PASS. Discord/Watch no-network credential scopes PASS.
  Operations scope는 검증 도구가 SSH credential의 source를 잘못 `/etc/discordbot/secrets/`로 지정해 실패했다.
  설치 규약의 `/etc/discordbot/backup-ssh/id_ed25519` 및 `known_hosts`로 도구를 수정하고 직접 회귀 검사를 추가했다.
  실제 config/secret을 이동하거나 수정하지 않았으며 기존 immutable080 release를 보존한다.
  경로 수정 후 Windows full strict **771 passed/61.80초**, skip0/xfail0; 새 exact-source Pi 검증 예정.
- 080 소스의 전체 ancestry1651 objects/730 blobs/6322658 bytes pattern scan에서8곳을 확인했다.
  승인63 이력의 경로 참조·synthetic fixture7곳과 이후 추가된 Cloudflare 보안 test의 가짜 credential URL1곳이다.
  실제 credential 발견0, current forbidden data/key/env/log path0, commit-message pattern0.

### Exact retry source — VERIFIED / PUSHED / PIN APPROVED

- Source `368c8ebf7cbff2444eec63cfd69a40de3b2e2f3e`.
- Immutable ARM64 release `r-368c8ebf7cbff244-d026a47ed4f4b38a`, build/full strict148.428초.
  **762 passed / 9 skipped / 0 failed / 0 errors**, skip은 Windows에서 통과한 Node browser harness만 해당한다.
- Manifest17338 files, SHA256 `b56ff2e95287e75f2126511d249bb112107c48bc66a3285c30ebf27b86e12946`.
  Dependency hash `d026a47ed4f4b38ad8b7d3ba4fb70d18a42f9abadce0ace763ca01329b80f394`, schema range5–5.
- Discord/Watch UID999, Operations UID997의 설치된 production config/no-network scoped credentials 모두 PASS.
  Readonly mount/exact inventory/direct source access denied. Network login 및 DB open은 scope검사에서 하지 않았다.
- Guard after: canonical52d2ef… / config41edd03a… 유지, current unchanged, services stopped.
- Final ancestry scan1667 objects/733 blobs/6391193 bytes: 앞서 분류한 같은8곳 외 추가 탐지0.
  Current forbidden path0, commit-message pattern0. Windows full strict771 pass/61.80초.
- 이번 재시도20 files 변경. 원격63 대비 누적35 files/24 commits(앞선 준비·실패 문서/검증 포함).
  검증 당시 원격은63c7722였으며, 최신 push 결과는 위 실행 기록을 따른다.
- Safe Pi evidence `/home/os/discordbot-phase10/retry-build-368c8ebf7cbf.json`.
  Source archive SHA256 `d0d8b62c6ad7ca95c043a585df707253d7f14a25a7004b70e0eef1c2428bfe4b`.
- 검토한 operator 도구: `retry-start.py`(70초 gate, 현재 DB 유지,
  실패 시 newest-state 보존), `retry-observe.py`(유한 health guard/안전 stage 집계),
  `retry-production-backup.py`(live smoke 성공 후 actual canonical encrypted publish/read-back/독립복원).
  `retry-start.py`와 finite guard는 위 최신 기록대로 실행했다. Production backup 도구는
  실제 smoke 성공 조건을 충족하지 못해 실행하지 않았다. 추가 stop helper의 보존 결과도 위에 기록한다.

### Current-write encrypted local recovery

`deploy/production/preserve-stopped-current.py`를 사용자 sudo 인증으로 실행했다.
Stopped canonical의 byte copy만 새 private run에서 열고 암호화/복원했다. 원본·기존 preservation을
read-write로 열거나 덮어쓰지 않았다. 서비스/pin/config/remote는 변경하지 않았다.

- Run: `/var/lib/discordbot/phase10-retry-recovery-20260919-01/`.
- Backup identity: `20260919T053045873783-7394973bc1d846738780e14e9a1092d3`.
- Ciphertext SHA256: `d2642f1eec1d8e69c33f21db944621e839f5ff9e4eb70d8b08b4f5f8bb8125bd`.
- Restored image SHA256: `3ec627743756665b0f20db53ce6bb141a813648a019044be5b03909dab1d062b`.
- Schema5/count/data/metadata reconciliation and isolated application open/close PASS.
- Canonical/preserved after SHA256 remains52d2ef… . Remote publication false.
  이는 재시도 보호용 local recovery이며 first actual production off-host backup gate를 대체하지 않는다.

Safe evidence: Pi `/home/os/discordbot-phase10/retry-inspection.json`, `retry-recovery.json`,
`retry-media.json`, `retry-media2.json`. 자동 승인 검토가 safe metadata 회수를 차단하여 사용자에게 범위를 명시했고,
사용자는 이번10B safe aggregates/identity/test/code/timing을 현재 작업과 phase10 문서에서 분석·기록하도록
명시적으로 승인했다. Secret/raw row/raw log는 전송하지 않는다. sudo는 agent가 연 SSH 창에서
사용자가 직접 입력한다. V1, original candidate, prior release/backup/history는 그대로 보존한다.

## Earlier 63c7722 attempt — FAILED LIVE SMOKE / SERVICES STOPPED

2026-09-19 사용자 명시적 승인으로10B를 실행했으나 실제 Music/Watch smoke가 실패했다.
**PHASE 10 INCOMPLETE / 10B FAILED LIVE SMOKE**다. 두 production 서비스는05:09:43Z 정상 중지됐다.
아래10A 완료 보고는 승인 전 증거로 보존한다. 이 절은 첫 시도 이력이며 현재 상태는 문서 첫 절을 따른다.

### Actual live results and remaining gate

| 검증 대상 | 실제 결과 |
| --- | --- |
| Discord Gateway / command sync | 양쪽 ready 통과. Discord ready 조건에 Gateway ready 및 완료된 command sync 포함. 아래 실제 명령 응답도 사용자 확인 |
| Engagement | 사용자 `/내정보`·`/랭킹` PASS |
| Summary / Gemini | 사용자 최소 범위 `/요약` PASS |
| Music / Voice / provider | **FAIL**: 노래 추가 후 계속 로딩되다가 종료됨. 정상 재생·정지·voice lifecycle은 미확인 |
| Favorites / volume | **FAIL**: 기존 즐겨찾기 조회 불가. 데이터 소실 여부나 원인은 미확정; volume 별도 결과 미확인 |
| TTS | Music 실패로 사용자가 건너뜀. **NOT TESTED** |
| Watch / public HTTPS-WSS | HTTPS/health 및 route는 PASS. **기능 FAIL**: 새로고침 문제, 실시간 사용자 표시 누락, YouTube 탭에서 돌아오면 연결 끊김. WSS 전체 정상·동기화 PASS로 간주하지 않음 |
| Watch private admin | 사용자 세션 강제종료 성공 확인. 나머지 초대/정리 전체 경로는 미확정 |
| Birthday | production start에서 scheduler 연결 코드 경로 확인. 독립 scheduler readiness 측정 미확정; 테스트 생일/XP 삽입 없음 |
| Production backup / off-host / isolated restore | 주요 live smoke 실패로 **NOT RUN**.10A 복구 증거는 보존하되 이번 실제 writes의 백업 성공으로 대체하지 않음 |
| Timer / boot | 이번 production boot enable/backup timer 활성화 **NOT RUN**, update/manual/backup timer inactive 유지 |
| Final Audit gate | Audit0–10/통합 Audit 및 PHASE11 **NOT STARTED**. V1/env/원본/backup/release/history 삭제 없음 |

Failure matrix에 따라05:09:42Z 감시를 먼저 중지하고 두 서비스를 정지했다.05:09:43Z 관련6개 service의
MainPID0/ActiveState inactive/Result success, 두 production unit NRestarts0을 확인했다.
05:11:16Z operation lock 아래 latest data/state/cache/backups/config/audit 전체를
`/var/lib/discordbot/phase10-precutover-63c7722/failed-attempt/`에 보존했다(root:root0700).
Canonical과 preserved DB SHA256은 모두 `52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af`다.
Graceful stop 후 WAL/SHM은 없었으며 agent가 삭제하지 않았다. Canonical은 그대로 남겨 두었다.
Candidate8d17018f…와 hash가 달라졌으므로 startup/smoke 이후 writes를 보존해야 한다.
보존본 자체의 추가 integrity/application 검사와 변경 의미 분석은 아직 하지 않았다.
보존 시 production backup directory는 첫 backup 전 상태이며 이번 writes를 담은 off-host 복구본은 없다.
기능 실패의 원인은 아직 확정하지 않았다. 안전한 journal 분류에서는 Watch 단발 database_unavailable1회 외
원인을 결정할 예외 종류/코드 위치를 확보하지 못했다. 오류 문구를 삼키는 UI 경로가 있어 로그 부재는 정상 증거가 아니다.
원본 candidate 자동 replay, schema down-migration, V1 시작, synthetic fallback, 운영 code 교체는 실행하지 않았다.
Cloudflare origin은 사용자가 변경한9000 그대로이며 두 서비스 정지로 public Watch는 현재 서비스되지 않는다.
새 운영 commit을 적용하려면 수정·검증 후 exact commit/release에 대한 별도 승인이 필요하다.

### Maintenance timeline and bounded observation

- Maintenance start04:44:21Z → first ready04:55:24.770327Z: **11분3.770초**.
- First full successful live smoke: **없음**. Maintenance success end: **없음**.
- 실패 후 안전 정지05:09:43Z까지 작업 구간: **25분22초**. 실제 운영 성공 downtime으로 보고하지 않는다.
  V1은 이 작업 이전부터 정지했으므로 기존 V1 중단 시간까지 측정한 수치가 아니다.
- 관찰04:59:45.637128Z–05:09:40.185469Z, **594.548초/114 samples**, 모든 표본 ready, unexpected restart0.
  계획600초를 채우기 전에 실제 기능 실패 때문에 operator가 observer를 중지했다.
  Summary JSON의 `observing`은 마지막 sample 상태이며 현재 worker가 실행 중이라는 뜻이 아니다.
- Discord RSS82,148–85,736KiB/FD9–15/threads6–9, Watch RSS68,624–70,224KiB/FD9–13/threads4–5.
  실사용 부하가 섞인 짧은 관찰이며 증가만으로 누수 여부를 확정하지 않는다.
- 온도55.65–60.05°C, throttling samples0, disk free delta-692,224bytes.
  Watch probe failed1→1/Discord0→0; 최초 Watch 오류는 관찰 시작 전04:59:35Z였다.
  resource/ready 통과가 사용자 기능 성공을 보장하지 않았으며 post-cutover 안정성 PASS로 사용하지 않는다.

### Execution and preservation evidence

- Repository 문서/계약/Git 재확인: HEAD `53c79e7`, 시작 worktree clean. 운영 pin은63c7722 그대로다.
- Writer 최종 확인: 사용자가 이후에도 V1 실행 없고 보존본이 최신이며 다른 token owner 없음을 재확인했다.
  PC Python process0, Pi는 문서의 synthetic PID43017/43018 외 새로운 bot writer가 없었다.
- 04:39:45Z precheck PASS: authoritative 원본 hash, Pi candidate hash, source/prepared/staging config hash,
  기존 Pi encrypted recovery artifact hash,63c7722 release manifest/commit/schema identity 일치.
  source 원본은 hash만 확인했으며 SQLite로 열지 않았다.
- 단계별 실행: exact 명령표의 한 block씩 별도 SSH 명령으로 실행/검증한다. 전체 cutover 자동 실행 도구는 만들지 않는다.
  사전 검사 evidence는 `/var/tmp/phase10b-00-precheck.txt` (`step_exit=0`).
- **실제 production DB 승격 및 Discord/Watch 첫 시작 완료.** 아래 단계는 각각 결과를 확인한 뒤 다음 단계를 실행했다.
- Maintenance 시작 **2026-09-19T04:44:21Z**, 전체 관련 서비스 중지 확인04:44:23Z.
  Update/manual/backup timer와 synthetic peer는 중지·비활성화했다.
- 04:45:20Z synthetic data/state/cache/backups/config/marker 보존 완료:
  `/var/lib/discordbot/phase10-precutover-63c7722` (root:root2700,04:48:07Z에0700 확정).
  두 mode 모두 root 외 접근 금지다. Audit/operation lock 보존, WAL/SHM 삭제 없음.
- 04:48:07Z production config digest `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`
  설치 및5개 secret·전용 backup SSH credential·backup drop-in 설치 완료. Source candidate는 그대로 보존했다.
  Config root:discordbot0640, secret source root:root0600/부모0700, systemd-analyze verify PASS.
- 04:49:01Z Discord/Watch/Operations의 설치 경로 scoped preflight3개 PASS. 네트워크 login/DB open 없이
  형식·정확한 mount 이름·readonly mount 확인. Runtime/operations UID의 unmounted source 접근 거부 확인.
- 04:51:22Z exact63 stopped activation PASS, 모든 writer 정지 유지.
- 04:52:32Z 승인된 candidate → canonical `/var/lib/discordbot/data/bot_database.db` promotion PASS.
  직후 SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`, schema5와
  runtime UID readonly application validation PASS. Staging marker는 private preservation으로 옮겼다.
- First start **04:54:59.943605Z**, both ready/live **04:55:24.770327Z** (**24.827초**,70초 내).
  Exact release `r-63c77229d1a6e76a-d026a47ed4f4b38a`, Discord PID47277/Watch PID47279, NRestarts0.
  단계 전용 guard가70초 deadline과 restart/identity를 검사했으며 전체 전환 자동화는 아니다.
  Production startup부터 실제 writes/Discord 외부 효과가 발생할 수 있으므로 원본 candidate 자동 replay 금지.
- Cloudflare는 **사용자가 직접 변경 완료**를 확인했다. Connector의 최신 config event에서도
  기존 `watch.lgw323.com` route1개 → `http://127.0.0.1:9000`, internal9001/9010/9011 route0 확인.
  공개 HTTPS TLS 검증0(성공), HTTP200, `/health/ready`의 `ready=true` 확인.
  Pi listener9000/9001/9010/9011은 모두127.0.0.1이었다. 이후 실제 Watch 기능 실패로 서비스를 중지했다.
- 사용자 live smoke 결과는 위 표에 기록했다. Music/Watch 실패로 후속 성공 절차를 중단했다.
- 04:59:45.637128Z부터10분 한정 maintenance 감시 시작. 실제 production 서비스 재시작/identity 불일치는 즉시,
 5초 간격3회 연속 ready 실패는 pair stop. 이 감시는 post-cutover 완료 후 관찰을 대체하지 않는다.
- 04:59:35.433430Z Watch `database.probe_failed` / `database_unavailable`1회 기록. 후속 ready 회복,
  05:01:15Z까지18 samples/ready failure0. SQLite busy/I/O 등 원인은 미확정이며 corruption으로 단정하지 않는다.
- **Production backup / off-host publication / isolated restore / boot enable / backup timer는 아직 NOT RUN.**
  최초 production backup 전 backup_age=-1은 예상 초기값이며 RPO PASS 증거가 아니다.
- 성공한 maintenance end/full live smoke completion은 없다. V1의 기존 정지 기간과 이번 전환 시간은 구분한다.
- 실행 중 오류2개는 production 설치 전 해결했다: (1) Windows CRLF로 `set -euo pipefail` 실패;
  shell2행에서 종료되어 side effect 없음을 확인하고 LF 전송으로 수정. (2) preservation 부모의 setgid 상속으로
  mode2700 검사 실패; 설치 전 정지, 별도 빈 경로에서 GNU chmod 동작 확인 후 `chmod g-s`로0700 확정했다.
  실패 결과를 성공으로 덮어쓰지 않고 `03-install` 실패와 `03b-install` 성공을 별도 보존했다.
- Evidence: Pi `/var/tmp/phase10b-00-precheck.txt`~`phase10b-07-start.txt` 단계별 결과,
  `phase10b-start-gate-result.json`, `phase10b-live-monitor/`의 allowlisted 측정치. Secret/DB 내용/raw log는 보고하지 않는다.
  실패 중지/보존은 `phase10b-09-failure-stop.txt`, `phase10b-10-preserve-failure.txt` (`step_exit=0`).
- V1/source/env/schema0 원본/기존 encrypted backups/releases/history 보존. 운영 code pin 변경·새 push 없음.
- 명령표의 LF 전송/보존권한 교정은 local docs commit `bca8df9`로 기록했다. Runtime/source63은 변경하지 않았다.
- 이번 tracked 변경은 운영 결과 문서다. Staged diff/whitespace 검사를 수행했고 application 전체 test는
  다시 실행하지 않았다. 실제 DB를 test fixture로 사용하지 않았다. 이전10A의746 passed 증거는 아래에 보존한다.
- 사용자에게 즐겨찾기의 정확한 응답 유형, 음악 입력 방식, Watch 기기/브라우저를 요청했다.
  이 정보와 격리 재현으로 원인을 좁혀야 하며 UI 실패를 token/Cloudflare/데이터 손실로 추측하지 않는다.
- 종료 후 별도 Final Audit(Audit0–10 및 통합 Audit) 지시를 기다린다. Audit0/PHASE11 자동 시작 금지.

## Preserved PHASE 10A completion evidence

Updated: 2026-09-19. **10A COMPLETE / 10B NOT AUTHORIZED.**
준비 단계의 완료이며 PHASE 10 전체 완료나 production 성공을 뜻하지 않는다.
Production canonical promotion/login/service start/public route 변경/production backup timer는 실행하지 않았다.

## Phase 10A Status

| 최종 승인 자료 | 판정 / identity / 한계 |
| --- | --- |
| Authoritative DB source | PC `docs/rebuild/bot_database.db`; 최신성 사용자 확인. SHA256 `4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25` 재확인, 원본 SQLite open 없음 |
| Candidate DB | Pi `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`; SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b` 재확인. schema5/semantic/count/복구 PASS 증거 재사용, 재migration 없음 |
| Approved source/release | commit `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`, release `r-63c77229d1a6e76a-d026a47ed4f4b38a`; ARM64 build PASS. 해당 commit까지 일반 FF push 완료, main 보존 |
| Config/secrets | 기존 production-candidate와 세 credential scope 검증 유지. 새 별도 설치 준비 config digest `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`; exact 경로·권한·mount·보존 순서 확정. 현재 staging config 불변 |
| Corrected staging observation | 실제 synthetic pair에63 적용, **300.171초/31 samples**, 같은 release, live/ready PASS, NRestarts 증가0. 정상 주기 lifecycle journal0; failure/cancel/deadline/retry와 probe stable code 보존을 별도 Pi fault worker로 확인 |
| DB probe/health anomaly classification | 기존24h +12/+17, HTTPError1의 원인/status 소급 미확정. 새 `database_unavailable` 분류는 주입 증거이며 과거 원인을 뜻하지 않음. 손상 증거 없음, readiness/rollback trigger 아래 명시 |
| Watch tunnel | 실행 중 connector의 최신 config event에서 `watch.lgw323.com → http://localhost:8000` 확인. ingress2개, 내부9001/9010/9011 route0. 10B에서 기존 route origin만 `http://127.0.0.1:9000`으로 변경 |
| Off-host readiness | private Bot-Data 전용 SSH key, 실제 encrypted upload/download/decrypt 및 d54 runtime drill PASS 유지. 설치/drop-in/timer/retention/실패 정책 확정. 지속 production RPO·Git 총용량은 미측정 |
| Exact activation/promotion/rollback sheet | [최종 명령표](final-command-sheet.md) 준비 완료. 실제 release/DB/config hash, operation lock, 보존·설치·승격·first start와 단계별 실패 절차 고정, 입력 placeholder 없음 |
| Downtime plan | 승인 뒤30–60분 예상(실측 아님). Codex 단계별 실행, 사용자 직접sudo 및 Discord/browser smoke 확인. V1은 기존 확인상 이미 정지 상태 |
| Live smoke effects | command sync/dashboard/생일 due 알림 가능. `/내정보`, `/랭킹`, `/요약`, Music1곡, TTS, Watch create/connect/close, 실제 production backup/isolated restore는10B에서만 실행 |
| Remaining risks | 실제 token/guild/channel 권한·provider 부하 미검증, 과거 transient 원인 불명, short observation 한계, V1 music_state 부재, 새 V2 writes 이후 원본 복구 시 데이터 손실 판단 필요, Git history 증가 |
| Production / PHASE11 | **NOT AUTHORIZED / NOT RUN**. auto-update/manual timer 비활성화 유지. V1/env/history/backup 삭제 없음 |

## Corrected-release Actual Pi Observation

증거: `/var/tmp/phase10-corrected-63c7722/progress.json` stage `complete`, 같은 디렉터리 samples/summary.
PC ignored 보존본 `scratch/phase10/corrected-release-result.json`, `corrected-release-samples.jsonl`.
prebuilt63을 기존 synthetic pair에 적용했으며 production credential/DB/login을 사용하지 않았다.
작업 중 synthetic backup timer만 일시 정지 후 원래 active 상태로 복원했다. Update/manual은 계속inactive다.
관찰 UTC **2026-09-19 04:08:13.576–04:13:13.584**, observer elapsed **300.171초**.
service restart 전후 PID 변경은 명시적 release 적용 때문이며 관찰 중 PID43017/43018은 일정했다.

| 실제 측정 | Synthetic Discord | Watch |
| --- | --- | --- |
| Health | 9010, 31/31 ready, HTTP errors0 | 9011, 31/31 ready, HTTP errors0 |
| Release | r-63c77229d1a6e76a-d026a47ed4f4b38a | 동일 |
| NRestarts | 0→0 | 0→0 |
| RSS KiB 범위 | 52,524–52,660 | 68,276–68,584 |
| FD / threads | 7 / 2→3 | 9 / 3→4 |
| DB probe | 관찰 종료까지60 ok, failed0 | 관찰 종료까지60 ok, failed0 |
| 관찰 구간 journal entries | 2 | 2 |
| 3개 주기 task 정상 started/succeeded | 0 | 0 |

관찰 전후 `Services.smoke`의 ready/live pair 검증과 synthetic canonical schema/application validation PASS.
31개 sample 모두 ready이나10초 표본 사이 무중단을 입증하지는 않는다. 자원 범위에는 첫 probe/executor
thread 생성이 포함된다. 이전24h의 각 service 약379,000 journal entries와 달리 정상 주기 로그가 사라졌다.
global journal 사용량은 양쪽 모두 도구 표시 **3.2G**(반올림)였고 실제 journal byte 증가0을 뜻하지 않는다.
관찰+후속 점검/fault worker 구간 disk free delta **-118,784 bytes**; sample 첫/끝 차이는-110,592 bytes.
global disk 차이를 journal에만 귀속하지 않는다. 온도56.2–68.85°C, throttling samples 모두0.
첫 sample만 양쪽 backup_age=-1/RPO gauge1이었다. 코드상 최초5초 probe 전 초기값이며 이후30개는
age 정상/RPO gauge0, 마지막age 약773초였다. 이5분은 새 scheduled backup 실행/RPO 지속 증거가 아니다.

별도 transient `discordbot-phase10-telemetry-fault.service`는 approved63의 실제 TaskSupervisor/Probe를
사용하되 fake DB dependency와 PrivateNetwork로 실제 DB/API/secret에 접근하지 않았다.
실제 journal에 `task.failed`, `task.cancelled`, `task.deadline_exceeded`, `task.retrying`,
`database.probe_failed` 각1회와 **`database_unavailable`**1회를 확인했다. 주입 후 readiness false도
worker assertion을 통과했다. 자연 발생 장애를 재현하거나 기존24h 실패의 원인을 확정한 증거가 아니다.

## Anomaly Classification and Cutover Triggers

| 항목 | 확인된 category / readiness / 손상 evidence | 10B 처리 기준 |
| --- | --- | --- |
| 기존 synthetic probe +12 | probe read 실패 집계만 있음; 당시 stable code 없음. 수집된 ready false0이나 사이 순간 저하 가능 | 신규 failure 시 code/time/health status 기록. 단발은 제한 재확인;5초 간격3회 연속 ready false/error면 pair stop·조사 |
| 기존 Watch probe +17 | 위와 동일. SQLite busy/I/O/deadline 중 하나로 추측하지 않음 | 동일 기준. data_integrity나 schema/digest 이상은 즉시 stop/reconcile |
| 9010 HTTPError1 | HTTPError category 확정, status 미저장.503이라고 단정 불가. 해당 ready payload 미수집 | status와 양쪽 live/ready를 제한 확인;70초 startup gate 초과 또는 maintenance 중 예상 밖 restart면 stop |
| 신규 injected probe | database_unavailable + ready false. 구체적인 SQLite busy 대 I/O 구분은 이 code로 불가능 | error message/SQL/사용자 값 없이 code만 기록. 원인조사는 별도 안전한 진단으로 진행 |

기존 migration/restore/schema/integrity 검증과 이번 synthetic validation에 데이터 손상 증거는 없었다.
과거 모든 transient가 무해했다는 뜻은 아니다. 첫 검증 backup 이후 age<=6h, remote publication 실패,
identity split, audit/fsync uncertainty, writer 충돌을 성공 선언 중단/복구 검토 trigger로 둔다.
세부 [monitoring 및 rollback 절차](final-command-sheet.md#7-monitoring-stop-triggers)를 따른다.

## Final Config / Route / Installation Evidence

`prepare_install_sheet.py`를 Pi에서 interactive sudo로 실행해 **별도 준비 경로만** 생성했다.
`/var/tmp/phase10-install-sheet-result.json` stage `prepared_not_installed`, production_activated=false.
원본 user-entered config digest는 `5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3`,
새 준비 config는 `/var/lib/discordbot/phase10-install-plan-63c7722/config.json`이다. 변경은 검증된
backup_remote opt-in object 하나이며 최종 digest는 위 표와 같다.5개 secret 및 SSH2개 source는
root-owned regular/nonempty/0600 검사를 통과했다. 값은 출력·기록하지 않았다. 기존 scoped offline 검증을
반복하지 않았으며10B 실제 목적지 설치 뒤 다시 scope preflight를 수행한다.
PC authoritative hash와 Pi verified candidate hash는 그대로다. 새로운 source/writer는 보고되지 않았다.

Cloudflare read-only helper는 **현재 cloudflared InvocationID**의 마지막 config update event만 읽었다.
event_time_unix_us `1789357096890474`, matching hostname1/ingress2/internal port route0;
현재 origin은 `http://localhost:8000`이다. dashboard/API를 독립 검증했다는 뜻은 아니며10B 편집 직전에
대상을 다시 확인한다. DNS/route/connector는 변경하지 않았다. 설정의 token/다른 hostname/raw 로그는 출력하지 않았다.

## Implemented / Validation / Approval Boundary

추가 도구는 synthetic bounded observation, allowlisted connector route 조회, 별도 설치 config 준비에 한정한다.
기존 immutable63 runtime/DB schema/dependency는 변경하지 않았다. Windows 전체 strict 결과는 아래 최종 기록을 따른다.
직접 guard/config/문서 검증 **13 passed**. 최종 전체 strict **746 passed, 0 xfailed, 60.71초**이며
기존 audioop deprecation warning1개다. 작성 중 문서 anchor 오류1개를 수정한 뒤 전체 검사를 다시 통과했다.
실제 사용자 DB/API/systemd에 접근하는 pytest는 없다.
Pi63 ARM64 build/운영 tests/manifest/세 scope 검증은 기존 **138.196초 PASS** evidence를 유지한다.
off-host actual upload/download/decrypt를 불필요하게 반복하지 않았다. 이번 로컬 commits는 push하지 않는다.

실행 순서는 [최종 명령표](final-command-sheet.md), 기능 smoke/배경은 [runbook](cutover-runbook.md),
데이터 identity는 [migration contract](production-migration-contract.md), 입력 가이드는
[config guide](config-migration-guide.md)를 따른다. 과거 증거는 아래에 보존하며 최신 판정은 이 요약을 따른다.

## Baseline / Production Source Data

Repository branch `codex/rebuild-v2`, 시작 HEAD `4692caa`. PHASE 3/8/9 계약과 current plan/trace/decisions,
deploy runbooks 및 migration registry를 재구성했다. 시작 시 worktree clean. Windows baseline strict
**688 passed, 0 xfailed**를 재실행했다. 원본 DB/real network를 사용하는 테스트는 없다.
operator가 “이후 V1 실행 없음, 보존본이 최신”이라고 확인하여 `docs/rebuild/bot_database.db`를 authoritative
source로 확정했다. `.env`를 읽거나 복사하지 않았다.

## Original Preservation / Migration / Data Compatibility

[Production migration contract](production-migration-contract.md)에 source/candidate/restored SHA256,
ledger 1–5 checksums, counts, semantic/V1 reader 증거를 기록했다. source 65,536 bytes의 before/after hash
동일. candidate 143,360 bytes, schema 5, integrity/repeat/semantic/old-reader PASS.
six-table counts: users 15, favorites 40, music_settings 1, music_play_counts 50, Watch 양쪽 0.
PII/content row를 보고서에 저장하지 않았다. 실제 Watch nonempty 검증은 synthetic 증거만 있다.
원본은 hash/byte-copy만 했으며 SQLite는 새 working copy만 받았다. migration candidate는 PC isolated
path에 보존되어 있고 Pi canonical은 교체하지 않았다.

## Backup / Restore Evidence

PC `scratch/phase10/candidate-20260915-01/` 아래 실제 candidate encrypted backup과 independent
isolated restore PASS. Identity `20260915T015843161244-45854a29b85740c9b605da6163980095`.
source schema 0의 separate working copy도 `preservation-recovery/pre-migration.enc`로 암호화하고
별도 restore하여 counts/data/metadata/version 일치를 검증했다. backup identity/digests/복구 파일 위치는
migration contract에 있다. Windows private 계정 ACL 차이 때문에 첫 recovery가 파일 열기 전에 실패했고,
후보 경로에 operator의 최소 접근만 추가한 뒤 성공했다. secret 권한을 일반 사용자에게 열지 않았다.

사용자가 hidden prompt로 기존 DB key를 직접 입력했다. key ID `production-key-1`, 값 출력 없음.
key path `scratch/phase10/credentials/db_key`는 operator private ACL이며 Git ignored다.
schema 5 복구는 decrypt, checksum, schema, semantic, application isolated open/close를 모두 통과했다.
PC 검증 reference release는 `r-0376f14868461d16-d026a47ed4f4b38a`다. 아래의 새 ARM64 후보 release도
별도 빌드했지만 production으로 activate하지 않았다.
Pi에서도 사용자 입력 key의 scoped mount로 approved artifact 복구, 새 암호화 backup/재복구와 runtime UID
open/close를 통과했다. 증거는 `/home/os/discordbot-phase10/recovery-progress.json`, stage
`verified_not_promoted`다. 격리 후보는 `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`다.
schema 5와 위 six-table counts, data/metadata semantic reconciliation PASS. 새 Pi backup identity는
`20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71`이며 digests는 migration contract에 기록했다.
candidate digest/current pointer/canonical inode 보존 검사를 통과했고 production promotion/login은 없었다.
worker의 0.304초는 격리 복구·재백업 작업 시간이며 end-to-end 운영 RTO가 아니다.
이 rehearsal은 production canonical timer나 자동 off-host 복구 검증을 대체하지 않는다.

## Config / Secrets / Security

[직접 입력 가이드](config-migration-guide.md), invalid-placeholder template, hidden double-entry tool,
network/DB startup 없는 scoped preflight를 추가했다. V1 template의 모든 변수에 destination 또는
직접 매핑 없음/현재 typed default를 표시했다. Summary retention 등 기존 Phase 구현과 V1 template 차이,
raw Discord log/admin UI 미연결도 숨기지 않았다. production placeholder를 config/secret 단계에서 거부하는
guard와 regression을 추가했다. valid-looking 값의 실존/권한/API 인증은 live gate다.

사용자 요청에 따라 파일별 편집 대신 한 번 실행하는 한국어 `setup-production.py`를 추가했다.
세 기존 secret은 숨김 두 번 입력, 다섯 ID와 origin은 한국어 안내, Watch control/capability는 안전한
독립 무작위 키 자동 생성이다. 후보 생성/owner/mode/기본 validation을 수행하고 기존 후보/staging을
덮어쓰지 않는다. echoed getpass fallback과 noninteractive 실행을 거부한다. **사용자 직접 입력 완료 확인**을 받았다.
Pi `/home/os/discordbot-phase10/`에 wizard/config template/enter_secret/preflight를 전달했다.
Pi 임시 synthetic 디렉터리에서 owner/mode, exclusive-create, staging sentinel 보존을 실제 검증했다.
현재 `/etc/discordbot/config.json` 및 staging credentials는 그대로다. 새 release로 production candidate의
필수 config/ID/secret basic format, root-owned source files/modes와 실제 세 systemd credential mount 검증이
통과했다. 모든 probe는 PrivateNetwork=yes로 실행했고 DB와 실제 API login을 시작하지 않았다.
Discord: discord_token/gemini_key/control_key; Watch: capability_key/control_key; Operations: db_key.
모든 mount는 정확한 이름 목록, read-only, root:root 0440 + 기존 loader가 검증하는 service UID ACL이었다.
Discord/Watch UID 999, Operations UID 997. 모든 서비스에서 원본 secret 경로 직접 접근은 거부됐다.
검증 command의 argument에는 경로/식별자만 있으며 secret 값은 없었다. 구조/권한 PASS는 실제 token/API key
인증 또는 guild/channel 실존·권한 PASS가 아니다. 같은 UID의 적대적 완전 격리를 주장하지 않는다.
안전한 증거: Pi `/home/os/discordbot-phase10/verification-progress.json`, stage `verified_not_activated`.

## Source / Release Identity

Origin `https://github.com/lgw323/Bot.git`. 사용자가 exact commit
`d54ff3696c1a81d48a88008110d044d0e14edc89`의 새 `refs/heads/codex/rebuild-v2` 일반 push를 승인했다.
2026-09-19 전체 ancestry 1,415 objects / 661 blobs / 5,275,062 bytes를 검사했다. 민감 파일명 검사 결과 0,
내용 pattern 7곳은 credential 경로 참조 3곳과 synthetic fixture 4곳으로 분류했다. 실제 secret/key/data를
발견하지 않았다. pattern 검사가 모든 형태의 비밀을 수학적으로 배제한다는 뜻은 아니다. PC `.env`는 읽지 않았다.
승인된 exact commit만 push했고 remote ref hash 일치를 재조회했다. main은 전후
`8432fdef40cddc131176fa875e350660dc897e12`로 동일하다. force/history rewrite 없음.
당시 초기 production pin은 `d54ff36`이었다. 후속 사용자 승인으로 아래 `63c7722`까지 변경했다.
자동 업데이트 비활성화와 이후 새 commit 수동 검토·승인 정책은 유지한다. Bot-Data push는 별도 승인된 backup drill이다.
PHASE 10 guard 포함 commit `672694d3f0c5418ece99aecd0e886a42c53961ab`를 allowlisted git archive로
전달하여 offline ARM64 build/operations strict tests/manifest validation/publish까지 **133.961초**에 통과했다.
candidate release **`r-672694d3f0c5418e-d026a47ed4f4b38a`**, schema range [5,5], wheel lock SHA256
`d026a47ed4f4b38ad8b7d3ba4fb70d18a42f9abadce0ace763ca01329b80f394`.
source archive SHA256 `7a53f8a3ae9f0ed4234dd937a4d6b821c77e9fe41e2254bd4b29f2cf39c2f100`.
빌드는 외부 네트워크가 없는 transient unit에서 기존 sealed wheelhouse만 사용했다. current pointer와
staging config digest는 전후 동일하다. 새 release의 production pair activation/live smoke는 아직 미실행이다.

후속 off-host runtime 연결/전환 guard를 포함한 소스는 commit
`d54ff3696c1a81d48a88008110d044d0e14edc89`, allowlisted archive SHA256
`fadf41bf1befdf0d4859f0f8203b2b1d2ac1035c0e57c798f53765e617b1fb0f`다.
2026-09-18 실제 ARM64 offline build/operations strict/manifest [5,5] PASS, 소요 137.568초.
새 release는 `r-d54ff3696c1a81d4-d026a47ed4f4b38a`다. 실제 runtime `backup_once`의 opt-in 경로로
격리 production copy backup → Bot-Data publish/read-back → independent download → decrypt/semantic/count
비교를 통과했다. 증거 `/home/os/discordbot-phase10/offhost-wiring-progress.json`, stage
`verified_not_activated`. candidate config/current pointer/canonical inode 보존, production_enabled false.
새 release activation 또는 production timer 검증은 아니다.

## Pi staging / Longer observation

2026-09-15 01:45:12 UTC 재확인: real Watch PID 2417, synthetic Discord PID 2406, NRestarts 둘 다 0,
same release `r-0376f14868461d16-d026a47ed4f4b38a`, ready true. 실제 discord-bot PID 0 / inactive.
boot ID `77ce3f22-660f-45f6-a3d5-1a6e40650dbe`. cloudflared active PID 939, NRestarts 1(Phase 9 재부팅 이후
상태), connector 설정 변경 없음. four-hour synthetic backup timer active, 마지막 trigger 09:00 KST,
당시 다음 trigger 13:00 KST; backup Result success, update timer inactive. temperature 60.6°C.
이전/현재 PID 일치만으로 사이의 모든 시간을 실제 관찰했다고 주장하지 않는다.

처음 snapshot의 synthetic `database_recent_failures=2`, 후속 snapshot은 0이었다.
후속 누적 probe metric은 ok 15877 / failed 15, 당시 readiness 1, last DB latency 약 0.000769s,
backup age 약 7163s, RPO exceeded 0. 이 누적 실패의 개별 원인/발생 시각은 확인되지 않았다.
실패 수가 0이었다거나 장기 안정성이 증명됐다고 표시하지 않는다.

`deploy/staging/observe.py`: 24h/60s cadence의 finite root observer, 외부 통신 없이 loopback HTTP,
systemd, proc/sysfs 및 파일 개수/bytes만 읽는다. RSS/FD/threads/restart, probe success/failure/latency,
backup age/trigger, audit count, disk/cache growth, load/temp/throttling availability를 fsync된 JSONL/summary로 남긴다.
secret/DB contents/raw journal은 읽지 않는다. synthetic marker가 없거나 production이 시작되면 중단한다.
throttling sysfs가 없으면 unavailable로 기록하며 throttling 없음으로 간주하지 않는다.

첫 unit `phase10-observation-20260915`의 결과는 `/var/lib/discordbot` 상위 권한 때문에 operator가
바로 읽지 못했다. 두 번째 창은 PowerShell의 `&&` 구문 오류로 실행되지 않았다. shell chaining을 없앤
`finish_candidate_checks.py`로 격리 복구와 기존 evidence 집계를 실행했고, interactive sudo 후 성공했다.
새 경로 `phase10-observation-20260915-02`에는 samples가 없지만 **첫 observer는 실제 24시간 완료**했다.
안전한 집계는 `/home/os/discordbot-phase10/observation-review.json`에 보존했다.

| 관찰 항목 | 실제 결과 |
| --- | --- |
| 기간 / 표본 | elapsed 86,400.135초, 1,438개; first-to-last 86,400.013초, 최대 간격 60.555초 |
| 프로세스 | synthetic PID 2406 / Watch PID 2417 유지, 둘 다 NRestarts 0 |
| RSS | synthetic 52,864→52,868 KiB; Watch 68,944→69,064 KiB |
| FD / threads | synthetic FD 7, threads 3; Watch FD 9→9 (최대 12), threads 4 |
| DB probe 실패 누적 | synthetic 15→27 (+12), Watch 17→34 (+17); recent failures 각각 최대 2 |
| 표본의 마지막 DB 실행 시간 최대 | synthetic 0.079287초, Watch 0.397054초; 전체 요청의 최대/percentile은 아님 |
| Health 수집 | 9010 누락 1회, 9011 누락 0회; 수집된 응답의 not-ready 0회 |
| Backup | 최대 age 약 14,396.34초 (<4h), RPO exceeded 0; timer trigger 값 7개 (초기값 포함) |
| 온도 | 54.55–63.9°C |
| Disk / cache / audit | free 113,764,929,536→112,809,566,208 bytes; cache 0; audit files 88→100 |

DB probe 실패 원인은 기존 증거로 분류할 수 없다. 추가 집계에서 9010 누락은 `HTTPError` 1회로
좁혔지만 HTTP status는 당시 저장하지 않아 503이라고 단정하지 않는다. 1,438개 throttling 표본은 모두
numeric 0이었다(표본 사이 상태는 미관찰). 큰 disk 감소 구간 5개의 backup/audit bytes 증가는 0이었다.
2026-09-18 journal 사용량은 2.5GiB. 관찰 window의 metadata 집계는 Watch INFO 379,222건,
synthetic Discord INFO 379,218건이었다. 후속 MESSAGE는 메모리에서 allowlist category로만 변환했고
원문을 출력·보존하지 않았다. 45초 제한으로 일부만 집계한 각 서비스 309,526건 전부가
server-maintenance/telemetry-drain/database-probe의 정상 started/succeeded였다. 전체 기간의 메시지
분류가 완료됐다고 주장하지 않는다. 주기 작업당 이벤트 2개가 발생하는 코드와 일치한다.
로그가 disk 증가에 기여하는 원인은 확인했지만 free-space 감소 전부를 byte 단위로 귀속하지 않았다.
후속 로컬 수정 `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`는 세 주기 작업의 정상 lifecycle만 journal에서 제외하고 metrics/bounded task history와
실패·취소·deadline/retry 기록은 유지한다. DB probe 실패는 message/context 없이 stable error code만
추가한다. 기존 readiness 기준/주기/timeout은 유지한다. 수정본의 Pi build/운영 테스트/세 scope 검증도 138.196초에 PASS했다. 새 release는
`r-63c77229d1a6e76a-d026a47ed4f4b38a`, schema [5,5]이며 current/staging config는 전후 동일하다.
당시 서비스 적용은 미실행이었다. 후속 실제 bounded 관찰은 위 최종 증거에 기록했다. 과거 DB 실패 원인은 소급 미확정이다. allowlisted archive SHA256은
`8948ad0da780f81336d7bb30f7fc41fc3485602f5cd91c757d658221fb5cec69`이며 Pi로 전달했다.
별도 `verify_candidate.py`로 검증했으며 처음 잘못 지정한 run 경로는 실행 전 guard가 거부했다.
수정한 경로로 성공했다. 이후 sudo 입력 완료 답변은 별도로 요구하지 않고 safe progress로 확인한다.
63c7722 ancestry의 1,434 objects / 667 blobs를 검사했고 이전 7개 fixture/path 외 새 탐지는 없었다.
사용자가 exact `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`까지 기존 branch 일반 fast-forward
push와 초기 production 예정 commit 변경을 명시적으로 승인했다. push 직전에 전체 ancestry의
1,434 objects / 667 blobs / 5,314,031 bytes 및 역사적 파일명·commit 메시지를 재검사했다.
민감 파일명/commit 메시지 탐지 0, 기존 credential 경로 3곳과 synthetic fixture 4곳 외 새 내용 탐지 0.
추가 1 commit·6 files의 diff도 재검토한 뒤 `d54ff36..63c7722` 일반 fast-forward push를 완료했다.
원격 `refs/heads/codex/rebuild-v2`는 exact 승인 commit과 같고, main은
`8432fdef40cddc131176fa875e350660dc897e12`로 보존됐다. force/history rewrite는 수행하지 않았다.
이후 로컬 문서 commits는 승인된 push 범위에 포함하지 않았다. production 예정 release는
`r-63c77229d1a6e76a-d026a47ed4f4b38a`; auto-update 비활성화 및 별도 10B 최종 승인 경계 유지.
**24h 관찰 완료와 무결점 soak PASS는 다르며**, production/provider 부하는 미검증이다.

## Live Integration / Watch / Cloudflare

Gateway, command sync, `/내정보`, `/랭킹`, `/요약`/Gemini, Music/provider/voice/TTS,
Watch browser/public route 실제 smoke는 모두 NOT RUN. 최소 visible action과 startup side effect를
[cutover runbook](cutover-runbook.md)에 명시했다. 기존 친구 서버에 메시지를 전송하지 않았다.
사용자 선택 origin은 **`https://watch.lgw323.com`**. 제시 경로는 existing Cloudflare tunnel →
`http://127.0.0.1:9000`; signed control 9001과 health 9010/9011은 public 금지.
hostname 선택은 기록했고 DNS/public route 생성·변경은 10B final approval까지 실행하지 않는다.
2026-09-19 read-only DNS 조회에서 해당 이름의 A/AAAA 응답이 이미 존재함을 확인했다.
DNS만으로 route를 판단하지 않았다. 후속 current connector config event 검토 결과는 위 최종 증거를 따른다.

## Backup / Off-host Status

Pi timer는 여전히 synthetic DB 대상이다. Production candidate의 PC 및 Pi isolated encrypted recovery는 완료했다.
2026-09-17 사용자가 private `https://github.com/lgw323/Bot-Data.git`을 destination으로 선택하고,
source 인증과 분리한 write deploy key 등록/Private 상태를 확인했다. `git_backup.py`와 별도 수동 drill은
기존 `db-backup` branch에 암호화 artifact/allowlisted metadata만 fast-forward publish/read-back한다.
최신 8개 + 최근 7개 UTC 날짜별 1개 retention은 현재 V2 tree만 정리하며 Git history와 legacy는 보존한다.
과거 object의 실제 저장 용량은 계속 증가하므로 물리 삭제 보장이라고 주장하지 않는다.
11개 offline synthetic Git test가 통과했고, **actual Pi upload/download/isolated decrypt PASS**다.
Pi `/home/os/discordbot-phase10/offhost-progress.json`의 stage는 `verified_not_enabled`다.
Remote commit `1d6d6f5317d27581425e70cabb1a94c111f2c753`, active V2 recovery point 1개.
Identity `20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71`, artifact SHA256
`3dcaf8eafd9cb33309531e556593dc4a968b3696df2f9236b254625ce1b43766`로 Pi 원본과 read-back/download가 일치했다.
복구 DB SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`, schema 5와
six-table counts도 앞의 Pi 후보와 일치했다. 업로더는 SSH scope만, no-network 복구 worker는 DB key만 받았다.
증거와 plaintext isolated restore는 `/var/lib/discordbot/phase10-offhost-20260917-01/`에만 보존했다.
실제 remote pruning은 아직 대상이 없어 실행되지 않았다. retention 삭제/legacy 보존은 synthetic Git test로 검증했다.

후속 `4abaaa2`는 정확한 repository/ref opt-in을 loader/backup entrypoint에 연결했고 remote read-back
성공 후에만 latest를 갱신한다. transport는 총 90초 deadline, 실패 때 이전 latest/로컬 artifact를 보존한다.
현재 Pi config는 여전히 `backup_remote:null`; ARM64 격리 runtime wiring은 PASS, 실제 설치는 10B gate다.
두 번째 remote identity `20260918T002700190443-9da027cd4df542f3912d600d3499dbb0`, SHA256
`c40ef426984524686e1d6fcfee5b6e5cfafbacff3697aa838e09b7955612d956`, remote commit
`94886cab51fd0bf4cdc0ec55f21f05c0c1bd6e55`. schema 5/count/data/metadata reconciliation PASS.
실제 recovery point는 이제 2개이며 retention 삭제는 여전히 synthetic 증거만 있다.
키는 remote에 저장하지 않으며 manual drill만으로 지속 off-host RPO <=6h를 입증하지 않는다.

사용자가 encrypted candidate artifact와 metadata의 정확한 Pi 전송 경로를 승인했다(“ㄱㄱ”).
`/home/os/discordbot-phase10/recovery-input/` (0700)에 파일 두 개(0600)만 전송했고 `.enc` SHA256이
PC 증거와 일치했다. plaintext DB/키는 전송하지 않았다. 최초 전송은 자동 승인 검토가 해당 payload/경로의
명시적 승인 부족으로 거절했고, 사용자 확인 후 승인 범위 그대로 수행했다.
`restore_candidate.py`의 새 private recovery path에서 decrypt/schema/semantic, 재backup/restore,
runtime UID open/close를 완료했다. actual key/path/permissions의 격리 검증이며 canonical timer 검증은 아니다.

## Cutover Timeline / Actual Downtime / Production Smoke

10B 승인·canonical promotion·production login·production timer activation: **NOT RUN**.
Actual downtime, post-cutover health, live production smoke 결과: **N/A**.
30–60분은 미실측 maintenance 계획값이다. V1은 source 보존 이후 이미 실행되지 않았다는 operator 확인만
있으며, 이 세션에서 V1을 종료하거나 삭제하지 않았다.

## Rollback Readiness / Remaining Risks / PHASE 11 Gate

source schema 0 preservation+verified encrypted restore, schema 5 candidate+backup/restore를 PC에 보존했다.
Pi previous immutable releases와 staging DB/config는 유지했다. code-only rollback은 live schema compatibility가
필요하고 V2 writes 뒤 pre-cutover DB로 돌아가면 데이터 손실/reconciliation 판단이 필요하다. down-migration,
동시 V1/V2 writer, 불확실한 promotion 재시도 금지. operator가 2026-09-17 V1 music_state 보존본은
없다고 확인했다. 기존 active queue/voice channel/재생 위치는 미이전이며 synthetic snapshot을 대신 사용하지 않는다.

남은 위험: 실제 API 인증/resources/permissions, live providers 및 command UI, 지속 off-host durability,
기존24h probe/HTTP 실패 원인, power-loss와 실부하 capacity, production RPO/RTO,
미이전 V1 config overrides/log admin UI. Synthetic 수정본 관찰과 설치·복구 명령표는 완료했지만 위 위험은 남는다.
V1 code/scripts/env/legacy compatibility/history/backups/releases를 보존한다. PHASE 11은 별도 지시 전 시작하지 않는다.

## Tests / Commits / Decision Required

직접 regression과 wizard tests PASS. 중간 full strict는 700 passed / 1 failed였으며 실패는 작성 중인
cutover-runbook 문서의 missing-link 검사 하나였다. 문서 완료 후 최종 Windows strict는
setup까지 **705 passed, 0 xfailed, 33.28s**, 후속 host verification/restore 도구 추가 뒤에는
**711 passed, 0 xfailed, 34.37s**다. 기존 Python `audioop` deprecation warning 1개가 남았다.
RuntimeWarning/PytestUnraisableExceptionWarning은 error로 처리했고 xfail_strict=true였다.
기능 코드의 unrelated refactor/schema/dependency upgrade 없음. 작은 responsibility commits로 기록하며
실제 data/key/artifact는 코드 저장소에 stage하지 않는다. 승인된 코드 commit의 push를 완료했고,
승인된 Bot-Data에는 encrypted artifact/allowlisted metadata만 일반 push했다.

후속 entrypoint/observation 집계는 Pi에서 실제 실행 성공했다. 복구/집계 도구는 `6fd1660`에 커밋했다.
직전 Git staging의 자동 승인 검토 사용량 차단은 새 요청에서 정상 승인 경로로 재검토되어 해소됐다.
우회하지 않았다. off-host adapter 추가 뒤 Windows full strict는 **722 passed, 0 xfailed, 47.83s**이며
기존 audioop warning 1개만 남았다. 실제 외부/운영 DB를 테스트가 사용하지 않는다.
runtime wiring의 중간 full strict 실패 2개는 synthetic settings fixture의 새 optional field 누락이었다.
fixture를 명시적 `backup_remote=None`으로 보완한 뒤 725 passed, 최종 stopped activation/host 검증 도구까지
**732 passed, 0 xfailed, 48.96s**다. 실제 Pi 검증 성공과 Windows synthetic 테스트 성공은 구분한다.
코드 커밋은 `6fd1660`, `4f15a34`, `4abaaa2`, `b1562d7`, `d54ff36`으로 책임별 분리했다.
후속 로그 수정 `63c7722`는 독립 commit이며 사용자 별도 승인 후 exact commit만 push하고 production 예정 pin을 갱신했다.
수정 전 회귀 2개가 예상 실패했고 수정 후 관련 54개 및 전체 strict **735 passed, 0 xfailed, 52.97s**다.
기존 audioop deprecation warning 1개만 남았다. readiness/DB schema/실제 사용자 동작은 변경하지 않았다.
2026-09-17 후속 remote source ref 재조회는 자동 승인 검토 사용량 한도로 거절되어 갱신하지 못했다.
2026-09-18 SSH 상태 조회는 정상 승인 경로로 성공했고 차단된 조회를 우회하지 않았다.

Source publication/update policy는 승인·실행 완료다. 실제 시작 시각은10B 승인 뒤 잡으며30–60분을 계획한다.
수정본 synthetic 관찰, 기존 이상 분류/위험 공개, route read-only 검토 및 exact config/off-host/promotion/
rollback 명령표를 완료했다. 최종 상태는 **10A COMPLETE / 10B NOT AUTHORIZED**다.
실제 production 전환 및 PHASE11은 실행하지 않았다. 최종 질문은 다음과 같다.

**“이 상태로 실제 production cutover(PHASE 10B)를 진행할까요?”**
