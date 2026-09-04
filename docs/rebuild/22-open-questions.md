# 22. Decision Closure

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
| Q-H08 | ACCEPTED | 모든 Watch workload를 typed configuration의 hard cap으로 제한한다. session actor mailbox 100은 초기 제안값이며 participant/playlist/frame/rate/client-send 값은 Phase 6 Pi 부하 측정으로 조정한다. |
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
| Q-M12 | DEFERRED-MEASURE | 실제 Pi의 service account, restricted sudo, tunnel/firewall 설정은 추측하지 않는다. Phase 8/9에서 read-only inventory 후 runbook 값을 확정한다. |

## Legacy and presentation disposition

| ID | Status | 처리 |
| --- | --- | --- |
| Q-L01 | DEFERRED-PHASE-11 | orphan symbol/config는 V2 compatibility inventory에 남기고 rollback window 종료와 사용자 승인 전 삭제하지 않는다. |
| Q-L02 | ACCEPTED | Summary의 Discord 공개 응답 방식은 유지한다. 애플리케이션이 원문을 별도 장기 저장하지 않는 정책과 구분한다. |
| Q-L03 | DEFERRED-ADAPTER | 운영 dashboard의 언어·표현은 adapter 세부사항이다. 필수 health/metric과 기존 사용자 동작을 먼저 구현한다. |

## Remaining gates, not blockers

- 실제 Raspberry Pi model, RAM, storage, filesystem과 운영 baseline은 아직 확인하지 않았다.
- staging token/guild와 production secret은 저장소에 넣지 않으며 필요한 phase에서만 operator가 주입한다.
- capacity와 SLO 제안값은 typed configuration의 초기값일 뿐 Phase 9 실측 전 production 확정치가 아니다.
- production migration, service 중단, cutover, V1 삭제와 backup key 교체는 별도 사용자 승인 전 실행하지 않는다.
