# PHASE 10A → 10B cutover runbook

**NOT AUTHORIZED / NOT EXECUTED.** 10A 시작은 10B 승인이 아니다. 아래 unresolved 항목을 채우고
검토 가능한 최종 command sheet로 확정한 뒤 마지막에 사용자에게
**“이 상태로 실제 production cutover를 진행할까요?”**라고 묻는다. 아직 그 승인 질문을 올릴 준비가 안 됐다.

## 고정 대상과 미결정 항목

| 항목 | 검토된 값 / 필요한 결정 |
| --- | --- |
| Authoritative source | PC `docs/rebuild/bot_database.db`, hash는 [migration contract](production-migration-contract.md) |
| Current Pi canonical | `/var/lib/discordbot/data/bot_database.db`, 아직 synthetic |
| Production candidate | PC `scratch/phase10/candidate-20260915-01/candidate.db`, Pi에는 아직 전송 안 함 |
| Production runtime paths | `/opt/discordbot/releases/REVIEWED_RELEASE`, `/opt/discordbot/current`; data/state/cache/backups/audit는 `/var/lib/discordbot/` 아래 |
| Current staging release | `r-0376f14868461d16-d026a47ed4f4b38a` |
| Final release / commit | PHASE 10 guard 포함 immutable ARM64 build/validation 후 manifest와 40-hex commit을 확정해야 함 |
| Config/secrets | `/etc/discordbot/production-candidate/` 입력·scope probe 후 검토; 실제 목적지는 `/etc/discordbot/config.json`, `/etc/discordbot/secrets/` |
| Key identity | rehearsal `production-key-1`; 실제 Pi 입력 파일과 동일 키 관계를 decrypt로 확인해야 함 |
| Public Watch | 사용자 선택 `https://watch.lgw323.com` → existing tunnel → `http://127.0.0.1:9000` |
| Source publication | 제안: `origin` (`https://github.com/lgw323/Bot.git`)의 `refs/heads/codex/rebuild-v2`, normal push만. Exact HEAD와 diff 검토 후 별도 승인 |
| Update policy | remote/ref 승인과 immutable commit 재현 검증 전 disabled 유지 |
| Off-host | destination 승인 또는 명시적 local-only 재해 위험 수락 필요 |
| Maintenance | operator 시간/공지 수단 미확정. 자동 메시지 전송 안 함 |

placeholder가 남은 명령은 실행하지 않는다. 변경 가능한 변수들은 final approval sheet에 정확한 값과 digest로
고정한다. 최종 gate 전 이 문서를 단순 copy/paste 실행 스크립트로 취급하지 않는다.

## Gate A: 전환 전에 마칠 준비

1. 원본 시간 관계 확인은 완료했다. 전환 당일 V1이 그 뒤 재실행되지 않았는지 다시 확인한다.
   Windows/기존 host의 V1 token owner/writer도 포함하며 Pi에 V1 프로세스가 없다는 사실만으로 대신하지 않는다.
2. [migration contract](production-migration-contract.md)의 실제 candidate backup/isolated restore PASS와
   원본 hash를 확인한다. 새로운 source/writer가 있으면 기존 후보를 폐기 표시하고 새로운 run으로 다시 검증한다.
3. [config guide](config-migration-guide.md)대로 operator가 값을 직접 입력한다. 세 scope의 no-network
   credential mount/permission/placeholder 검사와 실제 guild/channel 의미를 검토한다. Pi offline 후보
   restore로 실제 설치 key/path/permissions를 증명한다. 아직 현재 canonical에 연결하지 않는다.
4. PHASE 10 commit을 sealed ARM64 wheels로 별도 immutable release에 build하고 manifest/inventory/tests를
   검증한다. 필요하면 synthetic pair로 Phase 9 방식의 activation/rollback을 재검증한다. production config를
   넣고 일반 deploy pipeline을 실행하면 조기 login이 일어나므로 그렇게 사용하지 않는다.
5. 현재 longer synthetic observer의 실제 기간·중간 실패·restart·DB latency·backup trigger를 읽는다.
   완료되지 않은 24시간을 완료라고 기록하지 않는다. 오래 관찰하지 못한 위험은 마지막 승인 화면에 명시한다.
6. off-host destination, retention, 실패 기록 및 remote restore drill을 승인·검증하거나, 사용자가 local-only
   host/storage loss 위험을 명시적으로 수락한다. `backup_remote`에 임의 URL을 넣으면 현재 loader가 거부한다.
7. source ref publication과 update policy를 별도로 결정한다. push 승인 전 local commit만 한다.
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
4. 검증된 암호화 schema 5 artifact와 JSON metadata를 private Pi candidate backup 경로에 전달하고
   approved key를 systemd scoped mount하여 새 isolated DB로 restore한다. wire 전송은 encrypted artifact만
   사용한다. metadata/digest/schema/count/semantic을 PC evidence와 대조하고 Pi runtime user로 open/close한다.
   이 후보와 hash/소유자/group/mode를 final command sheet에 기록한다. destination이 기존에 있으면 중단한다.
5. 현재 synthetic DB·state·config·credential source를 별도 private rollback 위치에 보존한다. production
   Music checkpoint는 V1 파일 유무/최신성을 별도로 확인한다. synthetic checkpoint를 production으로 재사용하지
   않는다. V1 snapshot이 없으면 active queue/voice restore는 미검증/미이전으로 기록하고 operator가 확인한다.
6. 검토된 production config/secrets를 실제 목적지에 설치한다. config root:discordbot 0640,
   secrets root:root 0700 directory / 0600 regular files, scope는 기존 LoadCredential 유지.
   final release의 no-network preflight를 다시 통과시키고 systemd-analyze verify를 실행한다.
7. stopped 상태와 operation lock 아래서 `ReleaseStore.validate(REVIEWED_RELEASE)` 후
   `ReleaseStore.activate(REVIEWED_RELEASE)`로 code+venv pointer를 원자적으로 바꾼다. 승인된 bootstrap
   전환 wrapper는 release 검증/lock/audit를 함께 수행해야 한다. shell `ln -sf`로 대체하지 않는다.
   wrapper/정확한 release가 미확정이면 승인 질문을 올리지 않는다.
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
    연결한다. 기존 DNS/route가 있으면 내용을 검토하고 충돌 시 멈춘다. 9001/9010/9011은 공개 금지.
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

## Off-host 선택과 retention 제안

현재 remote adapter가 없다. 선택지만 제시하며 임의 외부 서비스/과거 Git force-push 방식을 복원하지 않는다.

| 선택 | 구현/증명해야 할 조건 |
| --- | --- |
| 사용자 PC/NAS의 SSH/SFTP private destination | `.enc` + identity/checksum metadata만 전송, temporary upload 후 atomic publish, 원격 digest/read-back restore, 별도 auth와 항상 켜짐/접근 가능성 |
| 승인된 private object storage | 동일 조건 + 명시적 bucket/account/access scope/retention; 새 adapter 구현·검증 필요 |
| Local-only risk acceptance | Pi/storage 손실 복구 불가를 사용자가 명시적으로 수락; off-host PASS로 표기하지 않음 |

외부 보존 제안은 최근 8개 + 일별 7개이며 사용자가 목적지/용량과 함께 확정해야 한다. key는 backup
destination에 저장하지 않는다. upload 실패는 nonzero/audit/age로 표시하고 remote latest 성공으로 처리하지
않는다. 수동 PC 복사 1회는 지속적인 off-host 자동 backup/RPO 검증이 아니다.

## Rollback 및 PHASE 11

서비스 시작 전 실패는 모두 stopped 상태에서 preserved pre-cutover DB/config/release로 복구 가능한지
검토한다. V2가 write한 뒤에는 먼저 변경량/새 writes를 보존하고, 이전 V2 release의 ledger 5 reader
호환성을 검증한다. V1 rollback은 compatibility evidence만으로 자동 실행하지 않는다. preserved schema 0
DB/verified envelope와 retained V1 환경을 대상으로 operator reconciliation을 한다. source가 최신이었어도
cutover 이후 writes를 잃을 수 있으므로 recovery point를 명시한다. down-migration/dual writers 금지.

V1 코드/scripts/env, old credentials/backups/releases, legacy compatibility, historical migration은 삭제하지
않는다. 7일은 최소 보존 계획이며 자동 PHASE 11 승인이 아니다. 장기 production 관찰 및 별도 사용자 지시를 기다린다.
