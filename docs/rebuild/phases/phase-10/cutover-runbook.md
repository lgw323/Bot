# PHASE 10A → 10B cutover runbook

**NOT AUTHORIZED / NOT EXECUTED.** 10A 시작은 10B 승인이 아니다. 아래 unresolved 항목을 채우고
검토 가능한 최종 command sheet로 확정한 뒤 마지막에 사용자에게
**“이 상태로 실제 production cutover를 진행할까요?”**라고 묻는다. 아직 그 승인 질문을 올릴 준비가 안 됐다.

## 고정 대상과 미결정 항목

| 항목 | 검토된 값 / 필요한 결정 |
| --- | --- |
| Authoritative source | PC `docs/rebuild/bot_database.db`, hash는 [migration contract](production-migration-contract.md) |
| Current Pi canonical | `/var/lib/discordbot/data/bot_database.db`, 아직 synthetic |
| Production candidate | Pi `/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db`, SHA256 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`; PC 암호화 artifact에서 격리 복구, 아직 미승격 |
| Production runtime paths | `/opt/discordbot/releases/REVIEWED_RELEASE`, `/opt/discordbot/current`; data/state/cache/backups/audit는 `/var/lib/discordbot/` 아래 |
| Current staging release | `r-0376f14868461d16-d026a47ed4f4b38a` |
| Reviewed candidate release / commit | `r-63c77229d1a6e76a-d026a47ed4f4b38a`, commit `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`; offline build/운영 tests/manifest/세 credential scope PASS, activation 미실행. 실제 isolated remote backup 증거는 선행 d54ff36 기준 |
| Config/secrets | `/etc/discordbot/production-candidate/` 사용자 입력·3개 scope probe PASS; 실제 목적지는 `/etc/discordbot/config.json`, `/etc/discordbot/secrets/` |
| Key identity | `production-key-1`; Pi 사용자 입력 key로 approved artifact decrypt·재백업·재복구 PASS |
| Public Watch | 사용자 선택 `https://watch.lgw323.com` → existing tunnel → `http://127.0.0.1:9000` |
| Source publication | 사용자 승인 후 2026-09-19 exact 63c7722까지 `origin` (`https://github.com/lgw323/Bot.git`)의 `refs/heads/codex/rebuild-v2`로 일반 fast-forward push/remote hash 확인 완료; main 보존 |
| Update policy | 초기 production 63c77229d1a6e76a0edbc7d9249a8fceb5b0938c 고정, auto-update 비활성화; 이후 새 commit은 별도 검토·수동 승인 |
| Off-host | 사용자 선택 private `https://github.com/lgw323/Bot-Data.git`, `db-backup` branch; 전용 deploy key 등록, 실제 upload/download/decrypt drill PASS; d54ff36 runtime 연결 ARM64 격리 검증 PASS; 실제 설치는 10B gate |
| Maintenance | operator 시간/공지 수단 미확정. 자동 메시지 전송 안 함 |

Pi candidate/config/scoped credential 검증은 완료했다. candidate config SHA256은
`5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3`다.
Pi 복구 결과와 새 encrypted backup identity는 [migration contract](production-migration-contract.md)를 따른다.
이 digest들은 검증 시점의 identity다. 전환 직전 재검증하며 값이 달라지면 자동 진행하지 않는다.

placeholder가 남은 명령은 실행하지 않는다. 변경 가능한 변수들은 final approval sheet에 정확한 값과 digest로
고정한다. 최종 gate 전 이 문서를 단순 copy/paste 실행 스크립트로 취급하지 않는다.

관리자 작업은 operator가 SSH에서 직접 interactive sudo로 인증한다. passwordless sudo를 설정하거나
비밀번호를 저장하지 않는다. 2026-09-19 사용자 요청에 따라 입력 뒤 “완료” 답변을 별도로 요구하지 않고,
해당 commit의 안전한 progress 파일과 systemd 상태로 시작·완료를 확인한다. 진행 파일의 commit이 다르면
이전 run 성공을 새 작업 성공으로 취급하지 않는다.

## Gate A: 전환 전에 마칠 준비

1. 원본 시간 관계 확인은 완료했다. 전환 당일 V1이 그 뒤 재실행되지 않았는지 다시 확인한다.
   Windows/기존 host의 V1 token owner/writer도 포함하며 Pi에 V1 프로세스가 없다는 사실만으로 대신하지 않는다.
2. [migration contract](production-migration-contract.md)의 실제 candidate backup/isolated restore PASS와
   원본 hash를 확인한다. 새로운 source/writer가 있으면 기존 후보를 폐기 표시하고 새로운 run으로 다시 검증한다.
3. [config guide](config-migration-guide.md)대로 operator가 값을 직접 입력한다. 세 scope의 no-network
   credential mount/permission/placeholder 검사와 실제 guild/channel 의미를 검토한다. Pi offline 후보
   restore로 실제 설치 key/path/permissions를 증명한다(이번 isolated run PASS). 실제 API 인증과
   guild/channel 접근 권한은 미검증이다. 아직 현재 canonical에 연결하지 않는다.
4. PHASE 10 commit을 sealed ARM64 wheels로 별도 immutable release에 build하고 manifest/inventory/tests를
   검증한다. 필요하면 synthetic pair로 Phase 9 방식의 activation/rollback을 재검증한다. production config를
   넣고 일반 deploy pipeline을 실행하면 조기 login이 일어나므로 그렇게 사용하지 않는다.
   로그 수정 로컬 commit `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`는 별도 ARM64 build/운영 테스트/세 scope 검증을 통과했다.
   release `r-63c77229d1a6e76a-d026a47ed4f4b38a`를 사용자 승인으로 초기 production 후보로 확정했고
   exact source commit을 공개했다. 서비스 적용·재관찰과 config/rollback sheet 검토 및 10B 승인은 남는다.
5. 첫 synthetic observer의 24h/1,438개 samples를 회수했다. restart 0, backup RPO 초과 0이지만
   DB probe 실패 +12/+17, 9010 health 누락 1회, disk free 약 0.96GB 감소를 관찰했고 과도한 주기 작업 정상 로그가 기여함을 확인했다.
   throttling 1,438개 표본은 모두 0, health 누락은 status 미수집 HTTPError 1회다. [관찰 결과](phase-10-report.md)의 한계를 최종 승인 화면에 명시하고
   미분류 실패를 장기 안정성 PASS로 해석하지 않는다. 새로운 production 부하 관찰을 대신하지 않는다.
6. 선택된 private Bot-Data destination의 retention, 실패 기록 및 remote restore drill을 검증한다.
   새 소스에 명시적 opt-in `backup_remote`/credential wiring을 구현했지만 Pi의 기존 release/config는
   그대로다. d54ff36의 격리 entrypoint/manifest는 통과했으며 config/drop-in의 최종 설치 검토는 남는다.
   한 번의 성공을 자동 off-host RPO PASS로 표시하지 않는다.
7. 63c7722 source publication/pin 변경은 별도 사용자 승인 후 완료했다. auto-update는 비활성화한다.
   이후 commit도 별도 검토·수동 승인을 받아야 하며 이번 source 승인은 10B 전환 승인이 아니다.
8. 예상 작업 창은 **30–60분의 보수적 계획값**이며 실측 downtime/RTO가 아니다. 문제 시 maintenance를
   연장하거나 rollback/reconciliation한다. V1은 operator 확인상 이미 실행되지 않으므로 기존 중단 시간과
   이번 전환 작업 시간을 구분해 기록한다.

## Gate B: 최종 승인 뒤의 실행 순서

각 단계의 시작/끝 UTC, 결과, release/digest/backup identity만 audit에 남긴다. secret/row/raw vendor log 금지.

1. 최종 승인과 maintenance 시작을 기록한다. 승인된 operator 공지 후 모든 V1 writer/token owner 정지 확인.
   이미 정지되어 있으면 확인만 한다. V1 파일/환경/systemd/cron 경로를 지우거나 재배치하지 않는다.
2. Pi timer의 기존 enabled/active 상태를 기록하고 update/manual/backup timer와 진행 중인 oneshot을
   정상 종료한다. staging observer와 synthetic peer도 종료한다. 양쪽 real services와 writer가 완전히
   멈췄는지 확인한다. 합의된 operation lock을 확보하는 전환 절차를 사용하고 새 작업을 admit하지 않는다.

   ```sh
   sudo systemctl stop discordbot-update.timer discordbot-manual.timer discordbot-backup.timer
   sudo systemctl stop discordbot-update.service discordbot-manual.service discordbot-backup.service
   sudo systemctl stop phase10-observation-20260915-02.service
   sudo systemctl stop discordbot-staging-discord.service discord-bot.service watch-web.service
   sudo systemctl show discordbot-staging-discord.service discord-bot.service watch-web.service -p ActiveState -p MainPID -p Result
   ```

   absent transient observer에는 상태를 확인한 뒤 해당 stop을 생략한다. PID/lock/writer 미확인이면 중단한다.
3. 최종 source의 hash를 확인하고 immutable 보존/새 working copy/암호화 schema 0 recovery와 schema 5
   migration/old-reader/semantic/복구 검증을 확정한다. 이번 후보 이후 writer가 없고 digest가 같으면 이미
   검증된 후보를 재검증해 사용한다. source original을 SQLite로 열지 않는다.
4. 기존 10A Pi 격리 후보/backup을 재사용할 경우 위 digest와 source/writer 상태를 다시 검증한다.
   새 후보가 필요하면 검증된 암호화 schema 5 artifact와 JSON metadata를 private Pi candidate backup 경로에 전달하고
   approved key를 systemd scoped mount하여 새 isolated DB로 restore한다. wire 전송은 encrypted artifact만
   사용한다. metadata/digest/schema/count/semantic을 PC evidence와 대조하고 Pi runtime user로 open/close한다.
   이 후보와 hash/소유자/group/mode를 final command sheet에 기록한다. destination이 기존에 있으면 중단한다.
5. 현재 synthetic DB·state·config·credential source를 별도 private rollback 위치에 보존한다. production
   Music checkpoint는 operator가 2026-09-17에 **없음**으로 확인했다. 기존 active queue/voice channel/
   playback position은 미이전이다. synthetic checkpoint를 production으로 재사용하지 않는다.
   DB에 있는 favorites/play counts/music settings 보존과 snapshot 부재를 구분해 최종 승인 화면에 표시한다.
6. 검토된 production config/secrets를 실제 목적지에 설치한다. config root:discordbot 0640,
   secrets root:root 0700 directory / 0600 regular files, scope는 기존 LoadCredential 유지.
   final release의 no-network preflight를 다시 통과시키고 systemd-analyze verify를 실행한다.
7. 검토된 `activate-stopped.py`는 operation lock, exact expected-current, release manifest/schema,
   real/synthetic writer와 operation service/timer의 inactive 상태를 검증한 뒤 pointer만 원자적으로
   바꾼다. audit 실패 등 switch 이후 불확실성에서는 재시작/자동 rollback/retry하지 않는다.
   이 도구를 포함한 최종 ARM64 release identity를 확정한 뒤 아래 command sheet를 고정한다.

   ```sh
   sudo -u discordbot-deploy /opt/discordbot/releases/REVIEWED_RELEASE/.venv/bin/python -I /opt/discordbot/releases/REVIEWED_RELEASE/app/deploy/production/activate-stopped.py --target REVIEWED_RELEASE --expected-current r-0376f14868461d16-d026a47ed4f4b38a --approve-cutover-activation
   ```

   승인된 후보 REVIEWED_RELEASE는 `r-63c77229d1a6e76a-d026a47ed4f4b38a`다.
   최종 config/rollback command sheet와 10B 승인 전에는 실행하지 않는다. CLI flag는 사용자 최종 승인 자체를 대체하지 않는다.
8. [real restore](../../../../deploy/runbooks/real-restore.md)의 `ops` wrapper를 검토한 production config에
   연결한 뒤 **검증된 Pi isolated candidate**만 promote한다. 이 command는 자신의 operation lock을 얻는다.
   외부 lock을 다시 중첩하지 않는다. 시작 전 real services 외에 synthetic peer가 멈췄는지도 별도 확인한다.

   ```sh
   ops promote --destination "$REVIEWED_PI_CANDIDATE" --expected-sha256 "$REVIEWED_PI_CANDIDATE_SHA256" --approve-promotion
   ```

   canonical WAL/SHM이 남으면 DB와 함께 보존하고 checkpoint 원인을 조사한다. 삭제해 검사를 우회하지 않는다.
   post-replace fsync/audit failure는 uncertain이다. 실패 시 재시도/서비스 시작 대신 실제 canonical 재검증.
9. production DB 확인 뒤 `STAGING_SYNTHETIC_ONLY` marker를 production 상태로 오해하지 않도록 별도 보존
   경로로 옮기고 synthetic service의 boot enable을 해제한다. V1 자산은 보존한다.
10. **여기서 처음으로** `sudo systemctl start discord-bot.service watch-web.service`를 실행한다.
    70초 bounded readiness gate, 양쪽 같은 release/schema 5, Gateway/core 초기화, Watch stale cleanup,
    loopback listener와 restart count를 확인한다. 단일 curl 실패를 즉시 데이터 손상으로 단정하지 않지만
    bound를 늘리거나 무한 retry해서 성공 처리하지 않는다.
11. 아래 최소 live smoke를 승인된 채널에서 실행하고 결과를 기록한다. 실패가 데이터 정합성과 관련되면
    더 쓰지 않고 rollback 판단으로 이동한다.
12. canonical DB 경로/key/archive/operation lock/audit/metrics를 검증한 production `ops backup` 및
    새 isolated `ops rehearse`가 통과한 뒤에만 four-hour backup timer와 real service boot enable을 승인대로
    활성화한다. 초기 RPO는 <=6h, 자동 backup retention은 검증된 8개. 준비한 pre-cutover evidence는
    자동 retention 대상 밖에 최소 7일, PHASE 11 승인까지 보존한다. update/manual은 승인된 policy만 활성화한다.
13. 기존 Cloudflare connector를 유지하며 **승인된** `watch.lgw323.com` route만 public loopback 9000에
    연결한다. 2026-09-19 DNS 조회에서 A/AAAA가 이미 존재했으므로 기존 tunnel/origin route를
    먼저 읽어 검토하고 충돌 시 멈춘다. DNS 응답만으로 올바른 route라고 가정하지 않는다. 9001/9010/9011은 공개 금지.
    HTTPS/WSS/Origin/browser create-connect-close를 확인한다.
14. post-cutover observation/audit와 운영자 확인 뒤 success 또는 rollback/stopped-reconciliation을 선언한다.
    실제 downtime은 첫 maintenance/서비스 중단부터 필수 smoke 성공까지 실측한다.

## 사용자에게 보이는 최소 live smoke

최종 승인 전 실행하지 않는다. 시작 자체도 command sync, dashboard 초기화/음악 채널 정리,
재시작 상태 복원, birthday scheduler의 due 알림 등 visible effect를 일으킬 수 있음을 먼저 알린다.

| 기능 | 최소 동작 / 확인할 영향 |
| --- | --- |
| Gateway / commands | 한 token owner만 login, guild/intents/command sync 확인 |
| Engagement | `/내정보`, `/랭킹` 각 1회; 응답 privacy/문구와 기존 XP/생일 의미 확인 |
| Summary / Gemini | 승인된 메인 채널의 최소 시간 범위로 `/요약` 1회; 실제 대화가 Gemini로 전달되고 공개 결과가 생김 |
| Music / provider / voice | 전용 jukebox에서 기존 UI/검색 흐름으로 짧은 1곡 search/play/stop, 음성 connect/disconnect; 실제 오디오와 UI 메시지/정리 발생 |
| Favorites / volume / snapshot | 기존 즐겨찾기 조회, volume 표시와 snapshot 경로 확인; production 데이터에 임의 테스트 즐겨찾기 추가 금지 |
| TTS | 기존 TTS 경로로 짧은 합의된 문장 1회; 실제 합성 오디오, interruption/resume 확인 |
| Watch | 세션 1개 create/browser connect/close; 초대 및 private admin control 메시지 생성·정리, administrator 종료 확인 |
| Birthday / health | scheduler readiness 확인; 테스트 생일/XP 값으로 production DB를 수정하지 않음 |
| Operations | verified encrypted backup/isolated restore, age<=6h, audit/lock, pair readiness |

## Off-host: Bot-Data와 전용 SSH key

2026-09-17 사용자가 기존 private `https://github.com/lgw323/Bot-Data.git`을 선택했다.
전용 deploy key를 등록했고 저장소 Private 상태도 사용자 확인을 받았다. connector metadata 조회는
404여서 API로 privacy/access를 독립 확인하지 못했다. Pi SSH 인증은 실제 drill에서 검증했다.

`git_backup.py`는 remote `git@github.com:lgw323/Bot-Data.git`과 `refs/heads/db-backup`을 고정한다.
기존 branch가 없으면 자동 생성하지 않고 멈춘다. remote tree는 checkout하지 않으며 기존 legacy 경로를
그대로 보존한다. `v2/backups/<identity>.enc`와 strict allowlist JSON metadata만 추가하고, 기존 head를
parent로 한 일반 fast-forward push를 사용한다. force push/rebase/orphan/history rewrite는 없다.
독립 fetch의 artifact digest/metadata가 같아야 publication 성공이다. 충돌/인증 실패/불확실한 push는
자동 retry하지 않고 operator reconciliation으로 남긴다. 평문·key·DB row는 Git에 전달하지 않는다.

현재 tree에는 최신 8개 + 최근 7개 UTC 날짜별 최신 1개를 중복 제거해 최대 14개 복구 지점을 선택한다.
정리 대상은 V2 namespace뿐이며 **Git 과거 commit에는 이전 암호화 artifact가 남는다**. 따라서 이 정책은
복구 목록 retention이지 물리 삭제/저장소 크기 상한이 아니다. 과거 V1 backup/history도 삭제하지 않는다.
repository 용량/증가율과 외부 장기 보존 비용은 actual remote gate에서 확인해야 한다. history 정리는 별도 승인 대상이다.

키 준비는 Pi SSH에서 다음 한 줄을 한 번 실행한다. 기존 후보 디렉터리가 있으면 덮어쓰지 않는다.

```sh
python3 /home/os/discordbot-phase10/setup-backup-ssh.py
```

도구는 sudo 인증 후 `/etc/discordbot/backup-ssh-candidate/` (root:root 0700)에 별도 Ed25519 key를 만든다.
private key 0600은 출력하지 않으며 public key만 사용자 SSH 화면에 보여준다. 자동 실행을 위해 passphrase는
없고 root source와 systemd read-only credential scope로 보호한다. GitHub `Bot-Data → Settings → Deploy keys
→ Add deploy key`, title `DiscordBot V2 backup (Pi)`, 공개키 붙여 넣기, `Allow write access` 선택 순서다.
이 key를 source repository에 재사용하지 않는다. Deploy key는 repository 단위 권한이며 branch 전용 권한은
아니다. [GitHub 공식 deploy key 안내](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)를 따른다.
known_hosts는 [GitHub 공식 Ed25519 host key](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)를
2026-09-17 확인해 고정했다. host key mismatch에서 자동 수락/ssh-keyscan 대체를 하지 않는다.

검증용 `drill-offhost-backup.py`로 approved Pi encrypted artifact 1개를 업로드하고 새 경로로 다운로드했다.
업로더 unit은 backup SSH credential만, 후속 no-network restore unit은 DB key만 받는다. canonical DB,
현재 release/config와 timers는 바꾸지 않았다. `offhost-progress.json`은 `verified_not_enabled`이며
remote commit `1d6d6f5317d27581425e70cabb1a94c111f2c753`의 실제 decrypt/schema/application 검증 PASS다.

새 source runtime의 opt-in 설정은 아래 exact object만 허용한다. staging 및 현재 candidate의 null 설정은
아직 바꾸지 않았다. isolated `verify-offhost-release.py`의 d54ff36 결과는 PASS다. 10B 설치 sheet에
반영할 config/drop-in의 최종 검토는 아직 남는다.

```json
{"kind":"git-ssh","repository":"git@github.com:lgw323/Bot-Data.git","ref":"refs/heads/db-backup"}
```

Operations credential mount는 db_key에 backup_ssh_key/known_hosts를 추가하고 runtime Discord/Watch
scope는 유지한다. root private source `/etc/discordbot/backup-ssh/` 설치는 최종 승인 뒤다.
`deploy/production/offhost-backup.service.conf`는 backup.service 전용이며 update/manual/ops wrapper에는
동일 LoadCredential 두 줄만 추가하고 기존 build timeout을 유지한다. config만 바꾸고 credential을
누락하면 fail-closed한다. 전송 실패 때 이전 latest를 보존하며 bounded worker를 drain한 뒤 operation lock을
반납한다. 현재 production auto-backup은 비활성화 상태이며 지속 off-host RPO도 미검증이다.

## Rollback 및 PHASE 11

서비스 시작 전 실패는 모두 stopped 상태에서 preserved pre-cutover DB/config/release로 복구 가능한지
검토한다. V2가 write한 뒤에는 먼저 변경량/새 writes를 보존하고, 이전 V2 release의 ledger 5 reader
호환성을 검증한다. V1 rollback은 compatibility evidence만으로 자동 실행하지 않는다. preserved schema 0
DB/verified envelope와 retained V1 환경을 대상으로 operator reconciliation을 한다. source가 최신이었어도
cutover 이후 writes를 잃을 수 있으므로 recovery point를 명시한다. down-migration/dual writers 금지.

V1 코드/scripts/env, old credentials/backups/releases, legacy compatibility, historical migration은 삭제하지
않는다. 7일은 최소 보존 계획이며 자동 PHASE 11 승인이 아니다. 장기 production 관찰 및 별도 사용자 지시를 기다린다.
