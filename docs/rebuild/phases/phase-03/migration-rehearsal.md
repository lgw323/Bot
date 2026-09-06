# PHASE 3 Actual DB Compatibility Rehearsal

2026-09-05–06 Windows / repository Python 3.12.14에서 실행했다. 실제 원본은
`docs/rebuild/bot_database.db`이며 pytest fixture로 사용하지 않았다. 원본 접근은 파일
metadata/hash와 read-only copy에 제한했다. SQLite API, integrity/schema 검증, migration과
V1 reader는 `scratch/` 아래 별도 working copy에만 적용했다.

## Original integrity

| 항목 | 작업 전 | rehearsal 후 |
| --- | --- | --- |
| bytes | 65,536 | 65,536 |
| SHA-256 | `4e8f333b4903d2372fef75ac7ed5a90e58926b3b23a61cceb0c7cfd12517aa25` | 동일 |
| Git ignore | `*.db`에 의해 보호 | 유지 |

원본 rename/move/delete/schema 변경, production restore, Pi 전송은 없었다.

## Procedure and results

[`scripts/rehearse_v2_data.py`](../../../../scripts/rehearse_v2_data.py)는 명시적 source와 ignored
scratch output을 요구한다. source에 WAL/journal sidecar가 있으면 bare copy를 거부한다.
파일 복사 hash를 대조하고 V2 migration copy → 재실행 copy → V1/V2 reader 비교를 수행한다.
완료·실패 시 report에 safe aggregate만 기록하고 임시 working directory를 제거한다.

두 차례 독립 실행을 `scratch/phase03/rehearsal-01.json`과 `rehearsal-02.json`에 기록했다.
두 실행 모두 아래 검사와 원본 hash 보존에 성공했다. 이 파일과 DB 사본은 Git에 추가하지
않는다. 정상 복구용 key·token이나 운영 backup은 사용하지 않았다.

| 검사 | 실제 결과 |
| --- | --- |
| SQLite open / integrity_check | PASS / `ok` |
| schema variant | `legacy-current`, V1 six-table column/type/default/PK 호환 |
| SQLite user_version | 0 유지 |
| migration ledger | 0 → 2 |
| repeat migration | version/identity/checksum 검증 후 중복 적용 없이 PASS |
| row counts | 모든 기존 table 전후 동일 |
| semantic checksum | 모든 기존 column의 값·PK·scope 전후 일치 |
| old-reader compatibility | V1의 실제 public read 함수와 V2 adapter 결과 비교 PASS |
| cleanup | script가 만든 temporary working copies 제거 |
| original SHA-256 | 전후 동일 |

| Table | Before | After |
| --- | ---: | ---: |
| users | 15 | 15 |
| favorites | 40 | 40 |
| music_settings | 1 | 1 |
| music_play_counts | 50 | 50 |
| watch_sessions | 0 | 0 |
| watch_playlists | 0 | 0 |

users 중 guild membership 12행과 legacy global 3행을 보존했다. favorite 소유 사용자 3개,
music 데이터가 있는 guild 1개의 reader 결과를 비교했다. 잘못된 calendar 생일 warning은 0개,
orphan playlist는 0개였다. 개별 사용자 ID, 생일, 제목, URL 또는 실제 row는 보고하지 않는다.

| Version | Identity | SHA-256 of migration definition |
| --- | --- | --- |
| 1 | `legacy-nullable-pairs` | `4e70188b3ff476c130be765c012c1111e10c8541fb405682e4efb4395ae84063` |
| 2 | `legacy-guild-query-indexes` | `0cc61e732304ed421d2793ae2ea1c15a19809ba5434325cfa52a88d00bae29a2` |

## Limits

Watch는 실제 0행이므로 nonempty session/playlist 호환은 synthetic fixture에서 별도로 검증했다.
actual rehearsal은 migration/rollback-read proof이며 production cutover나 실제 backup key 복구
훈련이 아니다. Pi의 filesystem/power-loss/CPU/RSS/SLO, remote backup와 운영 RPO/RTO는
PHASE 8/9에서 검증한다. 원본의 의미가 바뀌면 기존 report를 재사용하지 않고 새 hash로 다시
rehearsal해야 한다.
