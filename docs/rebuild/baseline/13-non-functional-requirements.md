# 13. Non-Functional Requirements

## Reliability

| ID | requirement / measure |
| --- | --- |
| NFR-001 | 한 feature exception은 process-global uncaught exception이나 다른 feature queue 정체를 만들지 않는다. fault injection으로 검증한다. |
| NFR-002 | Watch web process 장애는 Discord gateway process를 종료시키지 않는다. |
| NFR-003 | 모든 background task/subprocess는 owner, name, deadline, cancellation, exception observation을 가진다. |
| NFR-004 | startup 필수 dependency 실패는 readiness=false이며 partial capability를 명시한다. |
| NFR-005 | shutdown은 10초 내 신규 admission 차단과 bounded drain/cancel/flush를 끝낸다. |
| NFR-006 | duplicate Discord event/retry/admin close는 idempotency key 또는 state transition으로 안전하다. |
| NFR-007 | 월간 command-plane availability 99.5%를 초기 제안한다; 측정 후 승인한다. |
| NFR-008 | backup age가 승인 RPO를 넘거나 restore drill이 실패하면 alert한다. |

## Performance and capacity

| ID | requirement / proposed target |
| --- | --- |
| NFR-009 | ACK p95 <1s, p99 <2s; 800ms 내 완료가 확실하지 않으면 defer한다. |
| NFR-010 | local non-AI command p95 <2s/p99 <5s; external media wait는 phase metric으로 분리한다. |
| NFR-011 | repository execution read p95 <25ms/write <50ms; queue/lock wait도 별도 측정한다. |
| NFR-012 | event-loop lag p99 <100ms; 1s 초과 지속은 alert 후보이다. |
| NFR-013 | 모든 queue/dict/cache/session/frame/body/result set은 configured hard limit과 거부 UX가 있다. |
| NFR-014 | workload별 concurrency를 분리한다: 초기 제안 summary 1, queue 4; metadata 2; Pi download 1; 실제 부하 test 후 결정한다. |
| NFR-015 | WS 정상 relay p95 <250ms; slow peer는 bounded send timeout 뒤 제거한다. |

## Scalability

| ID | requirement |
| --- | --- |
| NFR-016 | guild/user cardinality에 선형 global scan을 command hot path에서 하지 않는다. |
| NFR-017 | guild별 music actor와 session별 Watch actor로 noisy neighbor를 격리한다. |
| NFR-018 | 현재 2 guild에는 shard를 도입하지 않되 gateway/guild/command metric으로 threshold를 결정한다. |
| NFR-019 | SQLite 한계를 측정하기 전 Postgres/Redis를 요구하지 않으며 repository port로 교체 가능하게 한다. |

## Observability

| ID | requirement |
| --- | --- |
| NFR-020 | structured log는 correlation/interaction/job/session ID, phase, duration, result, typed error를 포함한다. |
| NFR-021 | command, external, DB, executor, actor queue, task, WS, reconnect, backup, deploy metric을 수집한다. |
| NFR-022 | liveness/readiness/dependency health가 process active와 application-ready를 구분한다. |
| NFR-023 | PII/secret/capability URL은 sink 이전 중앙 redaction하며 drop/sample도 metric화한다. |
| NFR-024 | alert는 actionable threshold/runbook/owner를 가지고 폭주를 dedupe한다. |

## Maintainability/testability

| ID | requirement |
| --- | --- |
| NFR-025 | domain은 stdlib 외 framework를 import하지 않고 adapter 의존은 inward port를 따른다. |
| NFR-026 | Discord/FastAPI handler는 ACK·DTO·use case·response만 처리한다. |
| NFR-027 | public contract에는 type hint와 version이 있으며 architecture import test로 경계를 강제한다. |
| NFR-028 | module import는 server/DB/network/migration side effect가 없다. |
| NFR-029 | feature requirement는 unit/integration/contract/failure test에 trace된다. |
| NFR-030 | clean environment에서 locked dependencies로 같은 release를 재현할 수 있다. |

## Security/privacy

| ID | requirement |
| --- | --- |
| NFR-031 | secrets는 repo/log/exception/command line에 노출하지 않고 file/service permission을 최소화한다. |
| NFR-032 | Discord actor/guild/channel/master 권한은 mutation 직전 server-side에서 확인한다. |
| NFR-033 | 모든 Discord/modal/HTTP/WS/config input에 schema, length/range/enum/canonicalization을 적용한다. |
| NFR-034 | Watch는 TLS, unguessable capability, Origin/CSRF/CSP, frame/rate/connection cap, authenticated admin channel을 가진다. |
| NFR-035 | summary 외부 전송은 승인된 consent, ACL, minimization, retention/redaction을 따른다. |
| NFR-036 | backup encryption key rotation과 old backup decrypt policy를 문서화하고 restore로 검증한다. |
| NFR-037 | dependency와 release artifact는 version/provenance를 기록하고 critical vulnerability 처리 절차를 가진다. |

수치는 production SLO 확정치가 아니라 baseline 전 설계 proposal이다. Raspberry Pi 5의
깨끗한 Ubuntu Server 24.04 LTS ARM64 환경에서 Ethernet/LAN을 사용해 PHASE 9 staging
부하·soak를 측정한 뒤 승인한다. 과거 WordPress/CloudPanel이 함께 있던 host의 수치는
acceptance baseline으로 복원하거나 재사용하지 않는다.
