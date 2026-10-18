# Production config / secrets 직접 입력

PHASE 10A 준비용이다. `.env`를 자동 읽거나 복사하지 않는다. 저장소의 실제 V1 템플릿 이름은
`envtemplate.txt`다. 아래 표는 그 템플릿과 현재 V2 composition을 비교한 결과다.
실제 값은 operator가 SSH/editor 또는 hidden prompt에서 직접 입력한다. 채팅에는 입력 완료와 경로만 알린다.

## Mapping

| V1 변수 | V2 목적지 / 현재 처리 |
| --- | --- |
| DISCORD_TOKEN | `/etc/discordbot/secrets/discord_token`, Discord만 mount |
| GOOGLE_API_KEY | `secrets/gemini_key`, Discord만 mount |
| DB_ENCRYPTION_KEY | `secrets/db_key`, Operations만 mount; 기존 backup을 읽을 키를 보존 |
| DB_BACKUP_REMOTE_URL | 자동 이전 없음. `backup_remote:null`은 local-only. 사용자 선택 Bot-Data/db-backup의 새 typed opt-in과 별도 deploy key는 cutover runbook 참조; 실제 설정은 아직 null |
| MASTER_USER_ID | `master`: 정수, 기존 최고관리자 |
| LOG_CHANNEL_ID | 자동 1:1 이전 없음. `admin_channel`은 private Watch control 채널이다. V1 raw error log 채널과 같은 의미로 간주하지 않는다. 현재 Discord log/admin UI 미연결은 Phase 8 잔여 범위 |
| MUSIC_CHANNEL_ID | `music_channels:[[guild_id, channel_id]]`; 같은 전용 jukebox 채널, guild를 명시 |
| SUMMARY_CHANNEL_ID | `main_channels:[[guild_id, channel_id]]`; Summary 수집과 생일 목적지가 공유하는 메인 채널 |
| WATCH_TOGETHER_URL | `public_origin`: 승인된 HTTPS authority, trailing slash/path/query 없음 |
| GEMINI_MODEL | `gemini_model`; 템플릿 기본값 `gemini-flash-latest`, 실제 API 지원은 live smoke에서 확인 |
| DEBUG_MODE | 직접 설정 없음. V2 structured local logging/metrics 사용 |
| MUSIC_PLAYBACK_BACKEND | 직접 설정 없음. 현재 V2 download/cache 경로, V1 direct rollback 스위치를 자동 이식하지 않음 |
| MUSIC_CACHE_MAX_BYTES / MUSIC_TRACK_MAX_BYTES / MUSIC_CACHE_MAX_AGE_SECONDS | JSON 외부 입력 항목 없음. 현재 Music typed cache limits 사용; V1 `.env` overrides가 있었다면 차이를 operator가 별도 확인 |
| TEMPERATURE / MAX_RESPONSE_TOKENS | Gemini adapter 현재 고정값 0.5 / 25000; config로 노출되지 않음 |
| DEFAULT_MAX_REQUEST_TOKENS | 직접 매핑 없음. V2 bounded prompt/request 정책; 이 값을 JSON에 임의 추가하지 않음 |
| DEFAULT_SUMMARY_HOURS / TIMEZONE_OFFSET_HOURS | Query 기본 6시간 / SummaryConfig 기본 +9시간; JSON 외부 입력 없음 |
| LOG_RETENTION_HOURS / INITIAL_LOAD_HOURS | 현재 SummaryConfig 24시간 / 3시간. V1 template 12시간 / 6시간과 다름; 승인된 Phase 5 구현의 상태를 그대로 표시하며 조용히 1:1 변환하지 않음 |
| MAX_LOG_COUNT / MAX_HISTORY_FETCH / PRUNE_INTERVAL_MINUTES | 현재 source당 1000 / page 100 / prune 600초. V1 template 1000 / 500 / 30분과 직접 1:1 매핑되지 않음 |
| 새 control_key | Discord와 Watch가 공유하는 내부 서명키, 최소 32자; 위 두 서비스만 mount |
| 새 capability_key | Watch capability 서명키, 최소 32자; Watch만 mount |
| 새 key_id | 비밀이 아닌 backup key 식별자. 이번 recovery 검증은 `production-key-1`; 실제 설치에도 동일 키/ID 관계 유지 |

기존 custom override가 중요한 경우 전환 전 차이를 검토한다. 이것은 새 설정/제품 동작 변경 승인이 아니다.
guild/channel의 실제 존재·permission·intents는 구조 검사로 증명할 수 없다. 최종 승인 뒤 최소 live smoke로 확인한다.

## 명령 하나로 직접 입력

한 번 실행하는 [setup-production.py](../../../../deploy/production/setup-production.py)와
[config.template.json](../../../../deploy/production/config.template.json)을 Pi의
`/home/os/discordbot-phase10/`에 준비했다. SSH 터미널에서 아래 한 줄만 실행한다.
사용자가 여러 파일을 만들거나 편집할 필요가 없다.

```sh
python3 /home/os/discordbot-phase10/setup-production.py
```

필요하면 도구가 먼저 기존 `os` sudo 비밀번호를 요청한다. 그 다음 순서는 다음과 같다.

1. 기존 Discord token — 숨김 입력, 같은 값 다시 확인.
2. 기존 Gemini API key — 숨김 입력, 같은 값 다시 확인.
3. **기존** DB encryption key — 숨김 입력, 같은 값 다시 확인. 새 키를 생성하지 않는다.
4. 최고관리자 Discord 사용자 ID.
5. 친구들이 봇을 사용하는 서버(guild) ID.
6. 요약·생일 알림에 함께 사용할 메인 텍스트 채널 ID.
7. 음악 전용 jukebox 텍스트 채널 ID.
8. 개인 관리 서버의 private Watch 알림·강제 종료 텍스트 채널 ID.
9. Watch origin — Enter 기본값 **`https://watch.lgw323.com`**.
10. Watch control key — 도구가 자동 생성, 사용자 입력 없음.
11. Watch capability key — 별도 무작위 키 자동 생성, 사용자 입력 없음.

secret은 48-byte randomness의 독립 Watch 키를 포함해 값/요약/log에 표시하지 않는다. hidden input이
불가능하면 echoed fallback을 거부한다. redirect/pipeline 실행도 거부한다. ID는 Discord 개발자 모드의
ID 복사로 얻은 정수다. 관리자 채널은 기존 LOG_CHANNEL_ID와 의미가 같다고 자동 가정하지 않는다.

도구는 별도 `/etc/discordbot/production-candidate/`를 exclusive-create하고 config root:discordbot 0640,
candidate directory 0750, secrets root:root directory 0700 / files 0600을 설정·검사한다. 기존 후보가
있으면 덮어쓰지 않는다. 입력 도중 Ctrl+C는 파일을 만들지 않고, 쓰기 도중 실패한 후보는
`.setup-incomplete` 표시와 함께 남겨 운영자 확인을 요구한다. 완료 출력은 준비 완료/PASS 상태뿐이다.
PASS는 기본 config 형식·누락·파일 content 일치·owner/mode 검사다. live login/API 인증/systemd mount는
다음 별도 검사이며 이 도구에서 시작하지 않는다. 현재 staging config/secrets와 DNS를 변경하지 않는다.

PC에서 직접 입력한 db_key는 copy rehearsal 전용 private 경로에 그대로 있다. Pi로 자동 복사하지 않았으므로
기존 키를 이 도구에 다시 직접 입력한다. `.env` 자동 읽기/복사는 없다.

## Login 없는 사전 검증

[preflight.py](../../../../deploy/production/preflight.py)는 config/credential만 검사하며 DB, Gateway,
Gemini, listener를 시작하지 않는다. **PHASE 10 guard가 포함된 검토된 release**의 `app/src`를 사용해야 한다.
현재 설치된 `r-0376f14868461d16-d026a47ed4f4b38a`에는 새 guard가 없다.

먼저 root-owned source files가 regular/nonlink/0600이고 root directory가 0700인지 metadata만 확인한다.
실제 값이나 전체 config를 출력하지 않는다. 세 번의 transient probe를 다음 정확한 scope로 실행한다.

| Probe service | User | LoadCredential 이름 |
| --- | --- | --- |
| discord-bot | discordbot | discord_token, gemini_key, control_key |
| watch-web | discordbot | capability_key, control_key |
| operations | discordbot-deploy | db_key |

Discord probe 예시(정해진 `REVIEWED_RELEASE`를 먼저 검토/입력한다; 값은 secret이 아니다):

```sh
sudo systemd-run --wait --pipe --collect --unit=discordbot-production-preflight-discord \
  -p User=discordbot -p Group=discordbot -p PrivateNetwork=yes -p NoNewPrivileges=yes \
  -p RuntimeMaxSec=30 -p ProtectSystem=strict -p ProtectHome=yes \
  -p LoadCredential=discord_token:/etc/discordbot/production-candidate/secrets/discord_token \
  -p LoadCredential=gemini_key:/etc/discordbot/production-candidate/secrets/gemini_key \
  -p LoadCredential=control_key:/etc/discordbot/production-candidate/secrets/control_key \
  "$REVIEWED_RELEASE/.venv/bin/python" -I "$REVIEWED_RELEASE/app/deploy/production/preflight.py" \
  --source "$REVIEWED_RELEASE/app/src" --config /etc/discordbot/production-candidate/config.json \
  --credentials /run/credentials/discordbot-production-preflight-discord.service \
  --service discord-bot --require-mounted
```

Watch/Operations도 표의 별도 unit 이름/User/LoadCredential 조합으로 검증한다. mounted directory에
정확히 허용된 파일만 있고, loader의 owner/mode/ACL 및 nonempty/basic format 검사와 read-only mount를
통과해야 한다. 추가로 다른 service namespace에서 secret source와 타 서비스 mount 접근이 거부되는지
Phase 9 security probe 방식으로 확인한다. systemd의 `LoadCredential` 경로만 argument에 있고 값은 없음을
확인한다. journal 검사는 operator가 로컬에서 수행하고 원문을 공유하지 않는다.
템플릿/가짜 값 거부는 기본 검사이며 유효한 token/API key 또는 Discord resource를 인증한 결과가 아니다.

최종 배치는 10B 승인 뒤에만 `/etc/discordbot/config.json`, `/etc/discordbot/secrets/`로 한다.
현 staging 원본도 private snapshot으로 보존한다. source secret 파일을 하나의 모든 서비스용 credential
directory로 mount하지 않는다. runtime 같은 UID에 대한 완전한 적대적 격리를 새로 보장한다고 주장하지 않는다.
