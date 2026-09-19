# Production migration contract

PHASE 10A는 copy rehearsal와 준비만 허용한다. 최종 10B 승인 전 canonical 교체, production login,
공개 route 변경, production timer/update 활성화는 금지한다. additive migration 1–5만 사용하고
V1·기존 schema/backup/reader와 history를 제거하거나 down-migrate하지 않는다.

## Source와 보존

2026-09-15 operator 확인: **보존본 이후 V1 실행 없음, `docs/rebuild/bot_database.db`가 최신**.
source original은 SQLite로 열지 않는다. regular standalone 파일임을 확인하고 sidecar가 있으면 중단한다.
새 writer/더 최신 파일이 확인되면 이 후보의 승인 효력을 폐기하고 source부터 다시 확정한다.

source SHA256 `4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25`, 65,536 bytes.
hash/read-only byte copy → 새 run의 read-only preservation → 별도 temporary working copy →
기존 DataRecovery의 migrated_copy → 독립 schema/data validation → V1 reader 비교 순서다.
preservation은 OS readonly와 digest 검증으로 보호한 파일이며 하드웨어 WORM이라고 주장하지 않는다.

## 재현 명령

Windows repository root의 operator shell에서 실행한다. `scratch`는 Git ignored다. 이미 존재하는 run,
backup/restore destination에 덮어쓰지 않는다. `.env`는 입력이 아니다.

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m scripts.prepare_production_candidate prepare --source docs/rebuild/bot_database.db --authoritative-source-confirmed --output scratch/phase10/NEW_RUN
.\.venv\Scripts\python.exe -m scripts.prepare_production_candidate preservation --output scratch/phase10/NEW_RUN --key-file scratch/phase10/credentials/db_key --key-id production-key-1 --release REVIEWED_RELEASE
.\.venv\Scripts\python.exe -m scripts.prepare_production_candidate recovery --output scratch/phase10/NEW_RUN --key-file scratch/phase10/credentials/db_key --key-id production-key-1 --release REVIEWED_RELEASE
```

placeholder NEW_RUN/REVIEWED_RELEASE를 실제 검토된 값으로 바꾼다. 이 도구에는 promotion 기능이 없다.
key는 [hidden input 도구](../../../../deploy/production/enter_secret.py)에서 직접 입력한다.
Windows에서는 생성한 계정의 private ACL 때문에 다른 계정이 읽지 못할 수 있다. 가능한 한 같은 operator
계정으로 실행한다. 이번에는 run root에 operator의 traverse/create, candidate/preservation에 read,
evidence에 modify만 추가했다. key를 agent 계정에 공개하거나 workspace 전체 권한을 확대하지 않았다.

## 검증 계약

- legacy six tables의 count, 전체 semantic checksum과 metadata checksum 보존.
- migration ledger version/checksum 1–5, integrity check, 반복 migration 멱등성.
- XP/level/voice time, birthdays, favorites(사용자 공용), volume/play counts의 V1/V2 reader 비교.
- empty Watch 실제 자료는 빈 상태만 검증한다. nonempty Watch는 synthetic regression 범위다.
- schema 5 candidate → 현재 암호화 envelope의 `.enc`/identity metadata → decrypt/checksum → 별도 restore
  → schema 5 application open/close와 semantic reconciliation. canonical은 열거나 교체하지 않는다.
- schema 0 preservation의 **다른 working copy**도 DataRecovery envelope로 backup/restore하여 V1 복구
  지점을 보존한다. schema 0 artifact는 schema 5 전용 Operations `rehearse`에 넣지 않는다.
- source/candidate SHA256은 image identity다. SQL restore 후 SQLite page 배치 때문에 파일 SHA256은
  달라질 수 있다. restore 자체 digest를 별도 기록하고 data/schema/metadata 일치를 검증한다.
- 실제 row/user ID/content는 evidence/report/test 출력에 포함하지 않는다. 테스트는 synthetic tmp DB만 사용한다.

## Actual candidate / recovery

PC run: `scratch/phase10/candidate-20260915-01/`. 아래 Pi 검증에는 승인된 암호화 artifact만 전송했다.
candidate SHA256 `a38bd20adc5a42058262bfcf3c8ed6837610a4e5489573724c7d440f834388bc`, 143,360 bytes.

| Table | Before | After |
| --- | ---: | ---: |
| users | 15 | 15 |
| favorites | 40 | 40 |
| music_settings | 1 | 1 |
| music_play_counts | 50 | 50 |
| watch_sessions | 0 | 0 |
| watch_playlists | 0 | 0 |

legacy global rows 3 보존, member reader 12, favorite owners 3, music guild 1, invalid calendar birthdays 0.
integrity/semantic/repeated migration/old-reader PASS. 실제 원본 before/after hash 동일.

| Version / Identity | Checksum |
| --- | --- |
| 1 legacy-nullable-pairs | `4e70188b3ff476c130be765c012c1111e10c8541fb405682e4efb4395ae84063` |
| 2 legacy-guild-query-indexes | `0cc61e732304ed421d2793ae2ea1c15a19809ba5434325cfa52a88d00bae29a2` |
| 3 engagement-event-ownership | `042b6dd5f21fb2b2891008945e793274a310510a4d960b7e2b17a9c2179e9f83` |
| 4 watch-process-ownership | `57a05fb3bee88ce0aae0f09d093d1467b24edf84e9d33b9661d271ec99f999c9` |
| 5 music-logical-playback-start | `775cfb10f51012358156da8100f391ae71fb4bfefc97adeeeed44cfcf0bcf5ce` |

Verified schema 5 encrypted backup:
`backups/20260915T015843161244-45854a29b85740c9b605da6163980095.enc` (+ matching JSON metadata).
Artifact 25,593 bytes, SHA256 `be2bc99031d64c6a6c59303bbaedb33b9647190a42fbf40921d3ccc53c850454`.
Restored `restore/restored-candidate.db`, SHA256
`57bc6be639f5c78b172cb268cd4735fb4f0c025778dbe88a3da069474df8d102`.
schema 5, decrypt/checksum/semantic/application isolated open-close PASS.

Verified pre-migration artifact: `preservation-recovery/pre-migration.enc`, 22,049 bytes,
SHA256 `08d5fed9f83158b45ea4ee11bf59f46601225d2758c4cb0dc99804fec7ed9cbe`.
Restored schema 0 file: `preservation-recovery/restored-v1.db`, SHA256
`c072e070aab23e5e41828bffb667954a88151a64d489e1af9f9cdc5c3c3791b7`.
Independent decrypt/restore preserves counts, data checksum, metadata checksum and version 0.

## Actual Pi isolated recovery (2026-09-16)

사용자가 위 schema 5 `.enc`와 matching JSON metadata의 전송을 승인했다.
Pi input은 `/home/os/discordbot-phase10/recovery-input/` (0700), 파일은 0600이며 artifact SHA256이
PC와 동일하다. plaintext DB/키는 전송하지 않았다. Pi wizard에서 별도로 입력한 `production-key-1`
credential을 Operations scope에 mount하여 decrypt에 성공했다.

release `r-672694d3f0c5418e-d026a47ed4f4b38a`에서 새 private run
`/var/lib/discordbot/phase10-recovery-20260916-01/`을 생성했다. 후보 `restored/candidate.db`의 SHA256은
`8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`다.
incoming restore → schema/위 aggregate 검증 → 새 encrypted backup → `restored/roundtrip.db` 복구 →
data/metadata/count 비교를 통과했다. SQL restore 후 PC 후보와 file digest가 다른 것은 별도 image로
기록하며 semantic 일치 검증으로 판단한다.

Pi 새 backup identity `20260916T022913726030-9e6a4f1f3db140aca083d7178a7bae71`,
SHA256 `3dcaf8eafd9cb33309531e556593dc4a968b3696df2f9236b254625ce1b43766`.
파일은 위 run의 `backups/` 아래에 보존한다. runtime UID 999의 별도 no-network/no-credential
open/close도 PASS. 후보 파일은 private run 내 공유 group 접근 0660이며 원본 secret 권한은 확대하지 않았다.
실행 증거는 `/home/os/discordbot-phase10/recovery-progress.json`, stage `verified_not_promoted`다.
후보 digest/current pointer/canonical inode 보존 확인을 통과했다. canonical 교체 및 production 시작은 없다.
0.304초의 worker 측정은 end-to-end 운영 RTO가 아니며 off-host/timer gate도 대체하지 않는다.

## Actual off-host recovery

Operator가 별도 write deploy key를 등록한 private Bot-Data의 `db-backup` branch에 위 Pi encrypted
artifact를 정상 fast-forward push하고 독립 fetch/download했다. Remote commit
`1d6d6f5317d27581425e70cabb1a94c111f2c753`, artifact identity/SHA256은 위 Pi backup과 동일하다.
`/var/lib/discordbot/phase10-offhost-20260917-01/restored/remote-candidate.db`는 schema 5와 위 counts,
application open/close를 통과했고 digest도 `8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b`다.
증거 `/home/os/discordbot-phase10/offhost-progress.json`, stage `verified_not_enabled`.
업로드 worker는 SSH key만, 복구 worker는 no-network/DB key만 사용했다. 키/평문은 전송하지 않았다.
실제 off-host recovery point 1개가 존재하지만 자동 publication/timer의 지속 RPO 증거는 아니다.

Both use operator-entered key ID `production-key-1`. Recovery compatibility reference is installed
`r-0376f14868461d16-d026a47ed4f4b38a`; the run used the PHASE 10 local tool and current unchanged recovery
implementation. This is **not** the final production release identity. Key/artifacts remain private and untracked.
PC rehearsal evidence is not an installed Pi off-host backup publication or a production timer proof.

## Runtime entrypoint off-host verification (2026-09-18)

`r-d54ff3696c1a81d4-d026a47ed4f4b38a`의 실제 `backup_once`를 별도 DB copy/config/paths에서 실행했다.
Identity `20260918T002700190443-9da027cd4df542f3912d600d3499dbb0`, SHA256
`c40ef426984524686e1d6fcfee5b6e5cfafbacff3697aa838e09b7955612d956`, Bot-Data remote commit
`94886cab51fd0bf4cdc0ec55f21f05c0c1bd6e55`. independent download/decrypt/schema 5/count/data/metadata
reconciliation PASS. `/var/lib/discordbot/phase10-offhost-wiring-d54ff3696c1a/` 격리 run에 보존했다.
증거 `/home/os/discordbot-phase10/offhost-wiring-progress.json`: `verified_not_activated`.
Production candidate config/current pointer/canonical inode는 유지했다. 실제 production activation/timer는 아니다.

## Promotion and rollback boundary

10B requires refreshed writer/source confirmation, final exact release/config/key/destination decision, Pi isolated
validation and matching digest. Only approved candidate may replace canonical, while both real services **and**
synthetic peer/writers/timers are stopped. Sidecars imply reconciliation, never deletion to bypass a guard.
Use the [cutover runbook](cutover-runbook.md); uncertain post-replace audit/fsync failure means stop/reconcile.
Code-only rollback is allowed only with compatible live schema. Once V2 writes, returning to a pre-cutover DB
loses those writes; operator decides reconciliation/recovery point. Preserve at least seven days of rollback
evidence and extend until PHASE 11 approval. Do not run V1/V2 concurrently on uncertain data.
