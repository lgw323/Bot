# PHASE 10A → 10B cutover runbook

**10A COMPLETE / 10B NOT AUTHORIZED / NOT EXECUTED.**
실행 순서·고정값·config/credential 권한·보존 위치·DB 승격·상황별 rollback은
[최종 command sheet](final-command-sheet.md) 한 곳에서 관리한다. 이전 초안의 placeholder 명령은 폐기했다.
실제 실행 전 최종 승인 질문은 **“이 상태로 실제 production cutover(PHASE 10B)를 진행할까요?”**다.

승인된 commit은 `63c77229d1a6e76a0edbc7d9249a8fceb5b0938c`, release는
`r-63c77229d1a6e76a-d026a47ed4f4b38a`다. 현재 Pi synthetic pair도 이 release다.
Production DB source/candidate는 [migration contract](production-migration-contract.md),
완료 evidence와 한계는 [10A report](phase-10-report.md)를 따른다. Migration/off-host drill을 반복하지 않는다.

기존 production-candidate 입력과 scoped 검증은 완료했다. 별도 install-plan config는 off-host opt-in만
추가한 준비본이며 현재 staging config는 그대로다. Canonical은 여전히 synthetic이고 Discord production은 inactive다.
Auto-update/manual timer는 disabled, 기존 synthetic backup timer만 active다. Source push 승인과10B 승인은 별개다.

Maintenance는 승인 뒤30–60분 예상이며 실측이 아니다. Codex가 명령을 단계별로 검증하며 실행하고,
사용자는 sudo를 직접 입력하고 live Discord/browser smoke를 확인한다. 입력 완료 답변은 요구하지 않는다.
V1은 기존 사용자 확인상 이미 꺼져 있다. 새로운 writer가 있었다면 후보 최신성을 다시 판단해야 한다.
Production 로그인 자체에 아래 visible effects가 있으므로 승인 전 시작하지 않는다.

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
총 repository 용량은 미측정이며 장기 운영의 모니터링 항목으로 남긴다. 현재 artifact 크기에 따른 제한된 추정은 최종 명령표를 따른다. history 정리는 별도 승인 대상이다.

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
아직 바꾸지 않았다. isolated `verify-offhost-release.py`의 d54ff36 결과는 PASS다. 별도 최종 준비 config와 exact 설치/drop-in 명령표 검토를 완료했으며 실제 설치는10B 승인 뒤다.

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
