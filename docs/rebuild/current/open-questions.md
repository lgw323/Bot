# Current Open Questions and Decision Closure

2026-09-04 V2 구현 마스터 프롬프트를 최상위 사용자 결정으로 반영했다. PHASE 0 기준
미해결 `BLOCKER`는 **0개**다. 아래 `ACCEPTED`는 구현 기준이며, `DEFERRED-MEASURE`는
제품 결정을 다시 묻는 항목이 아니라 정해진 phase에서 실측해 기술 값을 조정하는 항목이다.

## BLOCKER closure

| ID | Status | 확정 결정 | 후속 검증 |
| --- | --- | --- | --- |
| Q-B01 | ACCEPTED | 정상 DB/정상 backup이 없으면 production은 fail-closed한다. 새 DB는 `admin init-database`와 동등한 명시적 bootstrap operation만 생성한다. | missing/0-byte/corrupt/wrong-schema/explicit-bootstrap test |
| Q-B02 | ACCEPTED | 초기 목표 RPO는 최대 6시간, RTO는 약 1시간이다. 여러 recovery point와 deployment 전 verified backup을 유지한다. retention 개수는 DB 크기와 Pi storage를 측정해 정한다. | backup age alert, restore rehearsal, Pi disk measurement |
| Q-B03 | ACCEPTED | V1-compatible rollback 및 구 SQLite/backup/music snapshot reader 보존 기간은 production cutover 후 최소 7일이다. | old-reader contract와 day-7 removal gate |
| Q-B04 | ACCEPTED | Watch public runtime은 같은 Pi의 별도 `watch-web` process이고 Watch session persistence의 single writer다. Discord는 인증된 loopback application contract만 사용한다. | process crash isolation, loopback auth/replay, single-writer architecture test |
| Q-B05 | ACCEPTED | 기본 UX는 TLS 위 capability link이며 Cloudflare Access/login/IP restriction을 추가하지 않는다. token expiry/revocation, Origin/CSRF/CSP, schema/size/rate/cap을 적용한다. | web security/compatibility tests |
| Q-B06 | ACCEPTED | production cutover는 사용자 승인이 있어야 시작한다. readiness, integrity, reconciliation, 핵심 command, Discord 연결, event-loop lag 중 하나라도 중대 기준을 위반하면 즉시 rollback한다. | Phase 8 runbook과 Phase 9 rehearsal에서 수치 확정 |
| Q-B07 | ACCEPTED | 현재 배치는 소규모 single-guild 중심이어도 되지만 architecture, state, data, channel config는 `guild_id`로 격리된 multi-guild capable 구조다. | second-guild isolation suite |
| Q-B08 | ACCEPTED | 별도 staging Discord application과 guild를 사용한다. production token/guild에서 최초 실험하지 않는다. | Phase 9 staging gate; secret은 그때 operator가 주입 |

## Product and compatibility decisions

| ID | Status | 확정 결정 |
| --- | --- | --- |
| Q-H01 | ACCEPTED | command 이름·parameter 의미·permission·public/ephemeral·button/select/modal 기능은 보존한다. 문구와 embed cosmetic detail은 가능한 한 보존하되 byte-for-byte 동일성보다 architecture를 우선한다. |
| Q-H02 | ACCEPTED | 현재 `MASTER_USER_ID` exact-match 정책을 유지하고 authorization port 뒤에 둔다. role/admin 확장은 새 제품 결정 전 추가하지 않는다. |
| Q-H03 | ACCEPTED | Summary는 요청 시에만 source ACL을 통과한 필요한 범위의 원문을 Gemini로 전송한다. 애플리케이션은 원문을 별도 장기 보존하거나 raw content를 log하지 않는다. 추가 상시 opt-in UX는 도입하지 않는다. |
| Q-H04 | ACCEPTED | Summary source channel을 실제로 열람할 수 있는 requester만 요청·결과 접근이 가능하다. |
| Q-H05 | ACCEPTED | music play count는 실제 playback이 성공적으로 시작될 때 session당 한 번 증가한다. retry와 TTS resume은 중복 증가시키지 않는다. |
| Q-H06 | ACCEPTED | voice XP는 완료된 분 단위의 기존 공식을 한 곳에서 적용하며 profile과 ranking이 같은 값을 사용한다. |
| Q-H07 | ACCEPTED | music state는 graceful restart뿐 아니라 process crash에서도 의미 있는 transition과 coarse periodic checkpoint로 복구한다. 정확한 sample position보다 queue/session 일관성을 우선한다. |
| Q-H08 | ACCEPTED | 모든 Watch workload를 typed configuration의 hard cap으로 제한한다. Phase 6에서 session actor mailbox 100과 participant/playlist/frame/rate/client-send 상한을 구현했으며 Phase 9 Pi 부하 측정으로 조정한다. |
| Q-H09 | ACCEPTED | Watch는 login/host 없이 참여자가 공동 제어하는 현재 모델을 유지한다. abuse 방어는 capability, validation, rate/cap, audit로 한다. |
| Q-H10 | ACCEPTED | 실제 calendar에 존재하는 생일만 허용하며 2월 29일은 비윤년에 2월 28일 알림을 보낸다. |
| Q-H11 | ACCEPTED | summary/music/log/birthday channel과 feature flag는 guild-specific configuration으로 표현한다. 특정 guild/channel을 business logic에 하드코딩하지 않는다. |
| Q-H12 | ACCEPTED | 짧은 maintenance restart를 허용한다. zero-downtime을 위해 구조를 과도하게 복잡하게 만들지 않으며 readiness 실패 시 release와 dependency를 함께 rollback한다. |

## Engineering decisions

| ID | Status | 확정 결정 / 처리 |
| --- | --- | --- |
| Q-M01 | ACCEPTED | 기존 persisted volume과 snapshot field는 호환한다. 새 user-facing volume UI는 추가하지 않으며 새 session default는 현재 주 경로의 `0.5`로 통일한다. |
| Q-M02 | ACCEPTED | 암묵적 mention-prefix `help`는 V2 전환 기간에 보존한다. 제거는 Phase 11 legacy approval 대상이다. |
| Q-M03 | ACCEPTED | `direct` playback backend는 7일 rollback window 동안 compatibility fallback으로 유지한다. |
| Q-M04 | ACCEPTED | Discord 25-option 한계는 storage cap이나 데이터 삭제가 아니라 pagination으로 해결한다. |
| Q-M05 | ACCEPTED | V2 재구축 중 text XP cooldown/상한 등 지급 정책을 추가하지 않고 기존 의미를 먼저 보존한다. |
| Q-M06 | ACCEPTED | Discord voice channel 간 move는 가능한 한 같은 voice XP session으로 취급한다. |
| Q-M07 | ACCEPTED | KST application semantics를 유지한다. weekly reboot는 baseline/soak로 leak 부재를 확인하기 전 제거하지 않는다. |
| Q-M08 | DEFERRED-MEASURE | backup key rotation은 production 변경 승인 없이는 수행하지 않는다. Phase 8에서 key ID, old-key 보존, 책임자와 restore 절차를 작성한다. |
| Q-M09 | DEFERRED-MEASURE | 모든 log/TTS/music cache는 bounded configuration을 갖는다. 정확한 byte/retention 값은 Phase 2/7/9에서 Pi disk와 privacy 측정 후 정한다. |
| Q-M10 | ACCEPTED | 우선 Pi 내부의 bounded JSON log, Prometheus-compatible local metric, health/readiness를 사용한다. hosted platform은 기본 의존성이 아니다. |
| Q-M11 | ACCEPTED | 첫 production runtime은 Python 3.12 계열로 pin한다. yt-dlp도 재현 가능한 pin을 기본으로 하고 provider breakage용 emergency update 절차를 별도로 둔다. |
| Q-M12 | ACCEPTED/DEFERRED-MEASURE | Target은 Raspberry Pi 5, Ubuntu Server 24.04 LTS ARM64, Ethernet/LAN이다. Discord Bot V2·Watch Web·SQLite·필수 media/runtime·운영 도구만 설치하며 WordPress/CloudPanel과 기존 Cloudflare Tunnel/DNS는 복원하지 않는다. service account, RAM/storage/filesystem, 새 Watch tunnel/firewall 세부값과 capacity는 Phase 8/9에서 확정한다. |

## Legacy and presentation disposition

| ID | Status | 처리 |
| --- | --- | --- |
| Q-L01 | DEFERRED-PHASE-11 | orphan symbol/config는 V2 compatibility inventory에 남기고 rollback window 종료와 사용자 승인 전 삭제하지 않는다. |
| Q-L02 | ACCEPTED | Summary의 Discord 공개 응답 방식은 유지한다. 애플리케이션이 원문을 별도 장기 저장하지 않는 정책과 구분한다. |
| Q-L03 | DEFERRED-ADAPTER | 운영 dashboard의 언어·표현은 adapter 세부사항이다. 필수 health/metric과 기존 사용자 동작을 먼저 구현한다. |

## Remaining gates, not blockers

- PHASE 6은 Q-B04/05, Q-H01/02/08/09의 Watch 범위를 구현했다. 독립 process composition,
  signed loopback, durable-before-invite, lease/stale readiness, capability/limits와 bounded peer를
  synthetic 환경에서 검증했다. [Watch contract](../phases/phase-06/watch-contract.md)에 전송 불확실성과
  실제 browser/dual-process/Pi/Cloudflare 검증 한계를 기록했다. 실제 원본 DB는 이번 Phase에서 사용하지 않았다.

- PHASE 5는 Q-H01/03/04/11, Q-M04/07과 Q-L02의 Summary 범위를 구현했다.
  [Summary contract](../phases/phase-05/summary-contract.md)는 request ACL, public result visibility,
  retention/cap, provider cancellation과 staging 한계를 명시한다. 새로운 제품 결정은 없다.

- PHASE 4는 Q-H02/06/10/11, Q-M05/06/07의 Engagement 범위를 구현했다. 근거는
  [Engagement contract](../phases/phase-04/engagement-contract.md)다. 실제 Discord Gateway와 Pi
  intent/channel/capacity 검증은 staging에 남는다. 생일 claim 이후 uncertain failure는 자동
  재전송하지 않으며 voice observation failure는 restart reconciliation을 요구한다.

- PHASE 3에서 Q-B01의 V2 fail-closed startup/explicit bootstrap과 Q-B03의 copy-based old-reader
  검증을 구현했다. 세부 증거는
  [data contract](../phases/phase-03/data-compatibility-contract.md),
  [actual rehearsal](../phases/phase-03/migration-rehearsal.md)에 있다. V1 경로와 실제 운영 DB는
  전환하지 않았다. legacy global row와 날짜 오류를 자동 정리하는 새 제품 결정은 없다.
- actual DB의 Watch tables는 비어 있어 nonempty 동작은 synthetic test 증거만 있다. 실제 backup
  key를 이용한 restore drill, live-path/WAL 교체 절차, hard-link/filesystem/power-loss 검증과
  RPO/RTO 측정은 PHASE 8/9 gate에 남는다.

- Raspberry Pi 5와 Ubuntu Server 24.04 LTS ARM64, Ethernet/LAN은 확정됐다. RAM, storage,
  filesystem과 capacity/SLO baseline은 깨끗한 새 Pi staging에서 아직 측정하지 않았다.
- staging token/guild와 production secret은 저장소에 넣지 않으며 필요한 phase에서만 operator가 주입한다.
- capacity와 SLO 제안값은 typed configuration의 초기값일 뿐 Phase 9 실측 전 production 확정치가 아니다.
- production DB migration, service 중단, cutover, V1 삭제와 backup key 교체는 별도 사용자 승인 전 실행하지 않는다.

## PHASE 8 implementation / remaining gates

- 운영 도구·systemd 자산·13개 runbook과 synthetic backup/restore는 구현했다.
  [PHASE 8 report](../phases/phase-08/phase-8-report.md)의 증거와 미검증 범위를 따른다.
- Phase 9는 ARM64 pin/wheel availability, native ABI, actual systemd credential/polkit/group/WAL
  권한, symlink/fsync, capacity와 RPO/RTO를 측정한다. staging token/guild와 host auth는 그때만 주입한다.
- backup remote port에는 실제 destination/auth adapter가 없다. 새 외부 서비스나 기존 production
  destination 변경은 별도 결정 대상이다. 현재 local-only 도구를 off-host 복구 완료로 보지 않는다.
- daily update와 4시간 backup은 자산의 초기값이며 production timer 활성화/cadence는 staging 결과
  검토 후 확정한다. Cloudflare public route 검증과 production cutover는 현재 미실행이다.
- 이번 구현을 마무리하기 위한 추가 사용자 결정은 없다. PHASE 9는 새 지시 전 자동 시작하지 않는다.

## PHASE 9 actual staging update (2026-09-14)

- 사용자 지시로 Pi staging을 시작했다. ARM64 pins, actual release/permissions, local process pair,
  deployment/rollback, encrypted synthetic recovery/promotion과 reboot 증거는
  [PHASE 9 report](../phases/phase-09/phase-9-report.md)를 따른다. 앞의 Phase 8 상태는 당시 기록이다.
- staging Discord/Gemini credentials와 guild/channel/origin은 준비되지 않았다. 기존 PC `.env`를
  사용하지 않으며 live Gateway/command/Voice/provider smoke만 해당 gate로 남긴다.
- 공개 코드 저장소는 읽기 가능하지만 `codex/rebuild-v2` remote ref는 없었다. 승인된 ref publication
  및 update policy 없이 network auto-update를 활성화하지 않는다. SSH/source 인증은 새로 만들지 않았다.
- Cloudflare public hostname/route와 off-host backup destination은 별도 선택이 필요하다.
  짧은 synthetic 관찰을 production capacity, 장기 soak나 production RPO/RTO 증명으로 보지 않는다.

## PHASE 10A update (2026-09-16)

- Authoritative DB 확인 완료: operator가 preservation 이후 V1 실행 없으며 보존본이 최신이라고 확인했다.
  실제 copy migration/semantic/V1 reader와 schema 0/5 encrypted restore PASS. 원본 및 Pi canonical 보존.
- Public Watch origin 선택 완료: `https://watch.lgw323.com`; route는 기존 tunnel → loopback 9000만 계획한다.
  public DNS/route 실행은 10B 최종 승인 전 금지한다. 내부 9001/9010/9011 공개 없음.
- Config UX는 한국어 single-command setup으로 확정했다. 기존 3개 secret은 hidden double-entry,
  Watch 키 2개는 자동 생성한다. 사용자에게 여러 파일 직접 편집을 요구하지 않는다.
- 현재 blocker: 사용자 실제 candidate 입력, Pi scoped credential/backup restore 검증, final immutable release,
  off-host destination 또는 명시적 local-only risk acceptance, approved source ref/update policy,
  maintenance 및 V1 Music checkpoint 상태 확인. `.env` 자동 사용 금지.
- 24h finite observer는 도구를 준비했지만 새 경로의 실제 samples는 미확인이다. 긴 soak PASS가 아니다.
  기존 probe failure counter와 실제 long-run evidence의 한계는 [PHASE 10 report](../phases/phase-10/phase-10-report.md)에 남긴다.
- 전환 가능한 상태가 되기 전 최종 10B 승인 질문을 올리지 않는다. 승인 후에도 V1/호환성/backup/역사는
  보존하며 PHASE 11을 자동 시작하지 않는다.
