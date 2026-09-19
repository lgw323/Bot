# PHASE 10B exact command / reconciliation sheet

**10A preparation only — 10B NOT AUTHORIZED.** 아래 명령은 검토용이며 아직 실행하지 않았다.
최종 승인 뒤 Codex가 단계별 결과를 확인하며 실행한다. 한꺼번에 붙여 넣는 자동 전환 스크립트가 아니다.
사용자는 sudo 인증과 Discord/browser smoke 확인을 담당한다. 비밀번호·secret은 기록하지 않는다.
모든 shell block은 **Pi의 Bash**용이다. Windows PowerShell에서 직접 실행하지 않는다.
예상 maintenance 30–60분은 계획값이며 실제 시작/종료 UTC를 별도로 기록한다.

## 0. Exact identities and writer gate

- Approved commit: `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`.
- Current synthetic and proposed production release: `r-63c77229d1a6e76a-d026a47ed4f4b38a`.
  10A bounded synthetic activation을 완료했으므로 expected-current도 **63c7722**다.
- Candidate: `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`.
  SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`.
- User-entered config: `/etc/discordbot/production-candidate/config.json`, SHA256
  `5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3`.
- Prepared config: `/var/lib/discordbot/phase10-install-plan-63c7722/config.json`, SHA256
  `41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40`.
  원본 config에 아래 backup_remote object만 추가했다. 별도 준비본이며 현재 config에 설치하지 않았다.
- Staging config: `/etc/discordbot/config.json`, SHA256
  `14694c675aeac241f4cfd90d47c8429558f17b48d2f344f26aae6a5f57c58471`.
- Fixed preservation directory: `/var/lib/discordbot/phase10-precutover-63c7722`.
  이미 있으면 재사용/덮어쓰기하지 않고 중단하여 이전 전환 결과를 조사한다.

사용자 확인상 V1은 보존본 생성 후 실행되지 않았다. 최종 승인 시 그 이후에도 PC/다른 host에서
V1을 실행하지 않았는지 확인한다. Pi process 조회만으로 token owner 부재를 단정하지 않는다.
새 writer/source가 있으면 이 sheet를 실행하지 않는다. 재이관 여부부터 재검토한다.
PC authoritative 원본은 SQLite로 열지 않고 다음 hash만 확인한다(PowerShell):

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot\docs\rebuild\bot_database.db'
Get-Process python,pythonw -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path
```

Expected: `4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25`.
V1이 이미 꺼져 있는 기간과 이번 maintenance 시간을 구분한다. 사용자 승인 없이 공지 메시지를 전송하지 않는다.

## 1. Stop admission / preserve under the operation lock

Pi SSH에서 `sudo -i`로 직접 인증한 **같은 Bash session**을 아래에서 계속 사용한다.
환경 변수는 실제 고정값이며 대입이 필요한 placeholder가 아니다.

```sh
set -euo pipefail
umask 0077
ps -eo pid,comm
E=/opt/discordbot/releases/r-63c77229d1a6e76a-d026a47ed4f4b38a
R=/var/lib/discordbot/phase10-precutover-63c7722
P=/var/lib/discordbot/phase10-install-plan-63c7722
test "$(readlink -f /opt/discordbot/current)" = "$E"
test ! -e "$R"
test -f /var/lib/discordbot/STAGING_SYNTHETIC_ONLY
printf '%s  %s\n' 14694c675aeac241f4cfd90d47c8429558f17b48d2f344f26aae6a5f57c58471 /etc/discordbot/config.json | sha256sum -c -
printf '%s  %s\n' 5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3 /etc/discordbot/production-candidate/config.json | sha256sum -c -
printf '%s  %s\n' 41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40 "$P/config.json" | sha256sum -c -
printf '%s  %s\n' 8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b /var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db | sha256sum -c -
install -d -o root -g root -m 0700 "$R"
date -u +%FT%TZ > "$R/maintenance-start.txt"
systemctl show discord-bot.service watch-web.service discordbot-staging-discord.service discordbot-backup.timer discordbot-update.timer discordbot-manual.timer -p Id -p ActiveState -p UnitFileState -p MainPID > "$R/unit-state-before.txt"
systemctl disable --now discordbot-update.timer discordbot-manual.timer discordbot-backup.timer
systemctl stop discordbot-update.service discordbot-manual.service discordbot-backup.service
systemctl disable --now discordbot-staging-discord.service discord-bot.service watch-web.service
for u in discordbot-update.service discordbot-manual.service discordbot-backup.service discordbot-staging-discord.service discord-bot.service watch-web.service; do
  test "$(systemctl show "$u" -p ActiveState --value)" = inactive
  test "$(systemctl show "$u" -p MainPID --value)" = 0
done
for u in discordbot-update.timer discordbot-manual.timer discordbot-backup.timer; do
  test "$(systemctl show "$u" -p ActiveState --value)" = inactive
done
```

Python process 목록은 실제 실행 파일 소유자를 확인하는 보조 증거다. 사용자 최신성 확인을 대체하지 않는다.
완료된 observation transient가 inactive/not-found인지 확인한다. `discordbot-phase10-corrected-review.service`
또는 다른 observer가 실행 중이면 먼저 종료를 기다린다. 알 수 없는 bot/ops process는 PID와 실행 파일만
확인하고 cmdline/env는 출력하지 않는다. 이 시점부터 다른 operator의 조작도 금지한다.
stop 실패, failed 상태, 잔존 PID나 진행 중인 backup이 있으면 중단하고 원인을 확인한다.
`reset-failed`로 실패를 숨기지 않는다. 아래 명령은 동일 flock inode를 쓰며 ops 내부 lock과 중첩하지 않는다.

```sh
test -f /var/lib/discordbot/operations.lock
(
  flock -n 9
  test ! -e /var/lib/discordbot/data/bot_database.db-wal
  test ! -e /var/lib/discordbot/data/bot_database.db-shm
  test ! -e /etc/discordbot/backup-ssh
  test ! -e /etc/systemd/system/discordbot-backup.service.d/offhost.conf
  cp -a /etc/discordbot "$R/etc-discordbot"
  cp -a /var/lib/discordbot/STAGING_SYNTHETIC_ONLY "$R/STAGING_SYNTHETIC_ONLY"
  readlink -f /opt/discordbot/current > "$R/release-before.txt"
  sha256sum /var/lib/discordbot/data/bot_database.db > "$R/staging-db-before.sha256"
  for d in data state cache backups; do
    mv "/var/lib/discordbot/$d" "$R/staging-$d"
    install -d -o discordbot-deploy -g discordbot -m 2770 "/var/lib/discordbot/$d"
  done
  sync -f "$R"
  sync -f /var/lib/discordbot
) 9<>/var/lib/discordbot/operations.lock
```

DB/WAL을 먼저 삭제하지 않는다. sidecar가 있으면 stopped DB와 함께 보존하고 checkpoint 원인을 조사한다.
data/state/cache/backups 원본을 private preservation 아래로 옮겨 synthetic checkpoint/backup latest가
production에 섞이지 않게 한다. audit/operation lock은 이동하거나 되돌리지 않는다.
도중 실패 시 부분적으로 옮겨진 경로를 조사하며 보존 완료로 간주하지 않는다. 빈 DB를 새로 만들어 진행하지 않는다.

## 2. Exact production config / credential installation

```json
{"kind":"git-ssh","repository":"git@github.com:lgw323/Bot-Data.git","ref":"refs/heads/db-backup"}
```

준비한 config의 `backup_remote`는 위 object다. source Bot.git 인증과 별도 key를 사용한다.
GitHub deploy key는 repository write 권한이며 branch ACL은 아니다. adapter가 db-backup ref를 고정한다.

```sh
(
  flock -n 9
  install -o root -g discordbot -m 0640 "$P/config.json" /etc/discordbot/config.json
  install -d -o root -g root -m 0700 /etc/discordbot/secrets /etc/discordbot/backup-ssh
  for s in discord_token gemini_key control_key capability_key db_key; do
    install -o root -g root -m 0600 "/etc/discordbot/production-candidate/secrets/$s" "/etc/discordbot/secrets/$s"
  done
  for s in id_ed25519 known_hosts; do
    install -o root -g root -m 0600 "/etc/discordbot/backup-ssh-candidate/$s" "/etc/discordbot/backup-ssh/$s"
  done
  install -d -o root -g root -m 0755 /etc/systemd/system/discordbot-backup.service.d
  install -o root -g root -m 0644 "$E/app/deploy/production/offhost-backup.service.conf" /etc/systemd/system/discordbot-backup.service.d/offhost.conf
  sync -f /etc/discordbot
  sync -f /etc/systemd/system
) 9<>/var/lib/discordbot/operations.lock
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/discord-bot.service /etc/systemd/system/watch-web.service /etc/systemd/system/discordbot-backup.service
printf '%s  %s\n' 41edd03aa0c022e7d52bbe8da0814029ab3477eb66824fba438f67a78fd85f40 /etc/discordbot/config.json | sha256sum -c -
```

| Consumer | UID/group | LoadCredential source → mount name |
| --- | --- | --- |
| discord-bot | discordbot:discordbot | `/etc/discordbot/secrets/discord_token` → discord_token; gemini_key → gemini_key; control_key → control_key |
| watch-web | discordbot:discordbot | `/etc/discordbot/secrets/capability_key` → capability_key; control_key → control_key |
| backup / manual ops below | discordbot-deploy:discordbot | `/etc/discordbot/secrets/db_key` → db_key; `/etc/discordbot/backup-ssh/id_ed25519` → backup_ssh_key; `/etc/discordbot/backup-ssh/known_hosts` → known_hosts |

systemd가 `/run/credentials/<unit>/`에 read-only mount한다. source는 root:root 0600, 부모는0700이다.
scope 밖의 secret은 전달하지 않는다. config 부모 `/etc/discordbot`은 root:discordbot0750, config0640이다.
known_hosts는 검증한 candidate를 그대로 설치하고 host mismatch 시 자동 갱신하지 않는다.
backup 전용 drop-in은 LoadCredential 2줄과 TimeoutStartSec300 / TimeoutStopSec130이다.
update/manual timer는 비활성화한 채 유지하며 backup 전용 timeout을 적용하지 않는다.

네트워크 없는 preflight를 **설치된 경로**에 실행한다. 실제 값은 출력하지 않는다.

```sh
for scope in discord-bot watch-web operations; do
  user=discordbot
  creds=()
  case "$scope" in
    discord-bot) names='discord_token gemini_key control_key' ;;
    watch-web) names='capability_key control_key' ;;
    operations) user=discordbot-deploy; names=db_key
      creds+=(-p LoadCredential=backup_ssh_key:/etc/discordbot/backup-ssh/id_ed25519 -p LoadCredential=known_hosts:/etc/discordbot/backup-ssh/known_hosts) ;;
  esac
  for name in $names; do creds+=(-p "LoadCredential=$name:/etc/discordbot/secrets/$name"); done
  systemd-run --wait --pipe --collect --unit="phase10-installed-$scope" -p "User=$user" -p Group=discordbot -p PrivateNetwork=yes -p ProtectSystem=strict -p ProtectHome=yes -p NoNewPrivileges=yes -p RuntimeMaxSec=30 "${creds[@]}" "$E/.venv/bin/python" -I -B "$E/app/deploy/production/preflight.py" --source "$E/app/src" --config /etc/discordbot/config.json --credentials "/run/credentials/phase10-installed-$scope.service" --service "$scope" --require-mounted
done
```

## 3. Pointer activation / reuse verified candidate / validate before first start

```sh
sudo -u discordbot-deploy "$E/.venv/bin/python" -I -B "$E/app/deploy/production/activate-stopped.py" --target r-63c77229d1a6e76a-d026a47ed4f4b38a --expected-current r-63c77229d1a6e76a-d026a47ed4f4b38a --approve-cutover-activation
ops() {
  systemd-run --wait --pipe --collect --unit=phase10-approved-ops -p User=discordbot-deploy -p Group=discordbot -p UMask=0077 -p ProtectSystem=strict -p ProtectHome=yes -p NoNewPrivileges=yes -p ReadWritePaths=/var/lib/discordbot -p RuntimeMaxSec=300 -p TimeoutStopSec=130 -p LoadCredential=db_key:/etc/discordbot/secrets/db_key -p LoadCredential=backup_ssh_key:/etc/discordbot/backup-ssh/id_ed25519 -p LoadCredential=known_hosts:/etc/discordbot/backup-ssh/known_hosts "$E/.venv/bin/python" -I -B "$E/app/deploy/launch.py" operations "$@" --config /etc/discordbot/config.json --credentials /run/credentials/phase10-approved-ops.service
}
test "$(systemctl show discordbot-staging-discord -p ActiveState --value)" = inactive
ops promote --destination /var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db --expected-sha256 8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b --approve-promotion
printf '%s  %s\n' 8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b /var/lib/discordbot/data/bot_database.db | sha256sum -c -
sudo -u discordbot "$E/.venv/bin/python" -I -B -c 'import sys,asyncio; from pathlib import Path; sys.path.insert(0,"/opt/discordbot/releases/r-63c77229d1a6e76a-d026a47ed4f4b38a/app/src"); from discordbot.operations.adapters.cli import validate_candidate; asyncio.run(validate_candidate(Path("/var/lib/discordbot/data/bot_database.db")))'
mv /var/lib/discordbot/STAGING_SYNTHETIC_ONLY "$R/retired-staging-marker"
```

Promotion은 자체 ExclusiveLock, candidate SHA/schema5 검사, atomic replace/fsync/audit를 수행한다.
외부 flock 안에서 호출하지 않는다. hash 불일치나 post-replace 오류는 불확실한 상태로 보고 중단한다.
위 validation은 readonly application inspect이며 migration을 다시 실행하지 않는다.
이 시점까지 Discord production login은 없다.

## 4. First production start / bounded gate / public smoke

**이 시점부터 실제 Discord에 영향이 발생한다.** 같은 DB로 시작해도 command sync, jukebox dashboard/
메시지 정리, birthday due 알림, Watch stale cleanup이 발생할 수 있다. production write 유무를 추측하지 않는다.

```sh
systemctl start discord-bot.service watch-web.service
"$E/.venv/bin/python" -I -B -c 'import sys; from pathlib import Path; sys.path.insert(0,"/opt/discordbot/releases/r-63c77229d1a6e76a-d026a47ed4f4b38a/app/src"); from discordbot.operations.adapters.build import CommandRunner; from discordbot.operations.adapters.deployment import Services; s=Services(CommandRunner(),Path("/opt/discordbot"),(9010,9011)); s.ready("r-63c77229d1a6e76a-d026a47ed4f4b38a",timeout=70); s.smoke("r-63c77229d1a6e76a-d026a47ed4f4b38a")'
systemctl show discord-bot.service watch-web.service -p ActiveState -p MainPID -p NRestarts -p Result
```

70초 안에 양쪽 같은 release/live/ready가 확인되지 않으면 stop 후 아래 reconciliation을 수행한다.
제한 시간을 늘려 성공 처리하지 않는다. 최초 probe 전 backup_age=-1은 초기값이다. 시작 직후를 지속
RPO PASS로 간주하지 않으며 첫 backup 완료 후 age<=21600초를 확인한다.

Cloudflare의 기존 connector에서 **기존 published application route `watch.lgw323.com`**을 다시 읽는다.
여전히 `http://localhost:8000`이면 service만 `http://127.0.0.1:9000`으로 변경하고 저장한다.
기존 hostname/DNS/tunnel을 새로 만들지 않는다. 9001/9010/9011은 공개하지 않는다. 차이가 있으면 변경을 멈춘다.
Cloudflare API credential은 준비하지 않았으므로 UI에서 대상을 확인한다. raw token/config는 보고하지 않는다.
HTTPS/WSS/Origin과 [runbook의 최소 smoke](cutover-runbook.md#사용자에게-보이는-최소-live-smoke)를 확인한다:
`/내정보`, `/랭킹` 각1회, 최소 범위 `/요약`1회, Music 짧은1곡, 합의된 짧은 문장 TTS,
Watch create/connect/close·관리자 종료, favorites 조회. 실제 음성/초대/요약 메시지가 발생한다.
테스트 생일/XP/즐겨찾기를 production DB에 추가하지 않으며 사용자들에게 자동 연락하지 않는다.

## 5. First verified production backup / isolated restore / enable only approved services

```sh
ops backup
test ! -e /var/lib/discordbot/state/phase10-first-production-restore.db
ops rehearse --destination /var/lib/discordbot/state/phase10-first-production-restore.db
ops health
systemctl enable discord-bot.service watch-web.service
systemctl enable --now discordbot-backup.timer
systemctl show discordbot-backup.timer -p ActiveState -p NextElapseUSecRealtime
systemctl show discordbot-update.timer discordbot-manual.timer -p ActiveState -p UnitFileState
date -u +%FT%TZ > "$R/maintenance-end.txt"
```

새 production backup identity, remote read-back 성공, 독립 restore 검증과 canonical 비접촉을 확인한 뒤에만
enable한다. 기존 off-host drill을 준비 단계에서 반복하는 대신 10B에서 새 canonical을 보호하는 절차다.
backup timer는 UTC 00/04/08/12/16/20시, Persistent=true, RPO 목표<=6h다.
전체 파일을 암호화한 artifact와 strict metadata만 upload한다. remote 실패 시 local latest는 갱신하지 않고,
생성된 암호화 artifact와 이전 latest를 보존하며 nonzero/audit failure로 종료한다. 무한 retry는 없다.
SSH key는 backup 전용이며 auto-update/manual timer는 disabled를 유지한다.
Retention은 최신8개+7UTC일별 최신, 중복 제거 최대14개다. Git 과거 및 V1 이력은 남으므로 용량 상한이 아니다.
이번 약25KB/artifact를 하루6회 만들면 payload만 약150KB/일이나 실제 데이터 증가와 Git overhead는 제외한 값이다.
remote 총용량은 미측정이며 장기 용량을 보장하지 않는다. history 삭제/force push는 별도 승인 대상이다.
precutover·schema0/5 recovery evidence는 자동 retention 밖에 최소7일 및 PHASE11 승인까지 보존한다.

## 6. Failure matrix — stop first, preserve writes, no down-migration

| Failure point | Exact release / data recovery point | V1 / service outcome |
| --- | --- | --- |
| Before preservation or DB promotion | 63c7722; untouched synthetic canonical or `$R/staging-data/bot_database.db` | Production never started. Restore only completed preservation paths, keep all services stopped during inspection |
| After promotion, before first start | 63c7722 + SHA8d17018f… candidate; synthetic fallback in `$R/staging-data` | No intentional production writer yet; preserve promoted file, can restore synthetic environment below. V1 remains off |
| Startup/readiness failure | 63c7722 + failed canonical with WAL/SHM and state; original verified candidate retained | Startup itself may write. Stop both, preserve outcome, diagnose. No automatic candidate replay or V1 start |
| Live smoke failure | Same 63c7722 + post-smoke canonical/state | Discord messages/audio may already exist. Stop unsafe feature/pair as necessary; inspect writes before recovery. Reverting DB does not retract external messages |
| Any new V2 production writes | Same release + preserved newest DB/WAL; latest successful encrypted production backup, whose identity must be recorded | Restoring 8d17018f… or original schema0 loses new writes. User reconciliation approval required; do not pretend zero-loss rollback |
| audit/fsync/activation/promotion uncertain | Read actual current pointer, canonical digest/sidecars and audit while stopped | No blind retry, no assumed rollback. Compare target/candidate/preserved identities, readonly integrity+schema check; resolve audit/durability before start |

No older production V2 release has live evidence. Do not switch to 0376 or d54 as a production fallback.
The safe known **synthetic** fallback uses the same validated63 release, preserved synthetic DB/config/state.
V1 fallback data is the PC schema0 original SHA4e8f333b… or verified schema0 encrypted recovery
`scratch/phase10/candidate-20260915-01/preservation-recovery/pre-migration.enc`.
Clean Pi has no independently verified V1 runtime installation. V1 restart requires separate review of its retained
environment/token owner and explicit acceptance of recovery point/data loss. Never run V1 and V2 writers together,
never down-migrate the production schema5 file to make V1 run.

All post-start failures begin with these commands, followed by investigation (not automatic restoration):

```sh
systemctl disable --now discordbot-backup.timer discordbot-update.timer discordbot-manual.timer
systemctl stop discordbot-backup.service discordbot-update.service discordbot-manual.service
systemctl disable --now discord-bot.service watch-web.service discordbot-staging-discord.service
systemctl show discord-bot.service watch-web.service discordbot-staging-discord.service -p ActiveState -p MainPID -p Result
readlink -f /opt/discordbot/current
```

If stop/PID verification fails, do not move data. When **all are stopped**, first preserve complete failure state:

```sh
(
  flock -n 9
  test ! -e "$R/failed-attempt"
  install -d -o root -g root -m 0700 "$R/failed-attempt"
  for d in data state cache backups; do cp -a "/var/lib/discordbot/$d" "$R/failed-attempt/$d"; done
  cp -a /etc/discordbot "$R/failed-attempt/etc-discordbot"
  cp -a /var/lib/discordbot/audit "$R/failed-attempt/audit"
  readlink -f /opt/discordbot/current > "$R/failed-attempt/release.txt"
  sync -f "$R"
) 9<>/var/lib/discordbot/operations.lock
```

Copy data includes WAL/SHM; don't open the failed original read-write to checkpoint it away. Investigate a copy.
When outcome is known and **operator chooses synthetic-only fallback**, the following restores exact pre-cutover
environment while retaining all failed data. No production data is discarded and production login stays off:

```sh
test "$(readlink -f /opt/discordbot/current)" = "$E"
test -d "$R/failed-attempt"
(
  flock -n 9
  test ! -e "$R/detached-production"
  install -d -o root -g root -m 0700 "$R/detached-production"
  for d in data state cache backups; do
    test -d "$R/staging-$d"
    mv "/var/lib/discordbot/$d" "$R/detached-production/$d"
    cp -a "$R/staging-$d" "/var/lib/discordbot/$d"
  done
  mv /etc/discordbot "$R/detached-production/etc-discordbot"
  cp -a "$R/etc-discordbot" /etc/discordbot
  if test -e /etc/systemd/system/discordbot-backup.service.d/offhost.conf; then
    mv /etc/systemd/system/discordbot-backup.service.d/offhost.conf "$R/detached-production/offhost.conf"
  fi
  cp -a "$R/STAGING_SYNTHETIC_ONLY" /var/lib/discordbot/STAGING_SYNTHETIC_ONLY
  sync -f /var/lib/discordbot
  sync -f /etc
) 9<>/var/lib/discordbot/operations.lock
systemctl daemon-reload
printf '%s  %s\n' 14694c675aeac241f4cfd90d47c8429558f17b48d2f344f26aae6a5f57c58471 /etc/discordbot/config.json | sha256sum -c -
sha256sum -c "$R/staging-db-before.sha256"
```

**Default post-rollback state is stopped.** No automatic synthetic/service/timer start is bundled here.
If public origin was changed, restore the same Watch route service to `http://localhost:8000` via the same UI;
this restores prior routing only, not V1 availability. Don't leave public9000 routed to synthetic Watch.
Any later synthetic restart requires route isolation first. Original config, backups, audit, source/V1 assets and
failed production writes remain retained. PHASE11 cleanup is not authorized.

## 7. Monitoring / stop triggers

- Same-release/live/ready must pass startup70s. Split identity, data_integrity, failed promotion/fsync/audit,
  competing writer, unexplained canonical digest/schema mismatch: immediately stop and reconcile.
- First isolated `database_unavailable`/deadline or one HTTPError: record code/time/status, repeat bounded
  health checks; don't label corruption. Ready false/error for3 successive5s checks or any unexpected restart
  during maintenance: stop pair and inspect. Continuous recovery loops are not allowed.
- New probe failure rate, dropped telemetry, FD/thread/RSS monotonic growth, disk headroom decline: compare
  actual load and bounded samples. Don't extrapolate5min stability to long-term capacity.
- After first verified production backup, backup_age must be known and<=6h. Remote publish failure or RPO
  breach suspends success declaration/timer activation and requires recovery review; no older-DB automatic restore.
- Prior24h +12/+17 failures and HTTPError1 remain causally unclassified. Stable codes are available only after63.
  `database_unavailable` is a category, not proof of SQLite busy vs I/O. No data-corruption evidence was observed
  in schema/integrity validations, but that does not prove every past transient was harmless.
