# DiscordBot

친구들과 사용하는 Discord 서버를 위한 다기능 봇입니다. 음악 전용 채널의
주크박스, 대화 요약, 경험치와 랭킹, 생일 알림, YouTube 동시 시청, 관리자 로그를
한 프로그램에서 제공합니다.

## 주요 기능

- 음악 재생, 대기열, 반복, 자동 재생, 사용자별 즐겨찾기
- 봇 재시작 후 음성 채널, 재생 위치와 대기열 복원
- 지정 채널 대화 수집 및 Gemini 요약
- 채팅·음성 활동 기반 경험치, 내 정보와 랭킹
- 생일 등록, 목록과 오전 9시 알림
- 링크로 입장하는 Watch Together 동시 시청방
- 로컬 로그와 관리자 Discord 채널 오류 알림

## 로컬 개발 시작

Python 3.12 환경에서 개발 의존성을 준비한 뒤 테스트를 실행합니다.
테스트에는 운영 `.env`나 Discord 로그인이 필요하지 않습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest tests/
```

현재 실행 코드는 `src/discordbot/`의 V2입니다. 운영 시작에는 검토된 immutable
release, release manifest, 명시적인 설정과 scoped credentials가 필요합니다.
[운영 가이드](docs/operations.md)와 [배포 절차](deploy/runbooks/README.md)를 따릅니다.
폐기된 루트 V1 시작 파일과 `.env` 템플릿은 현재 실행 경로가 아닙니다.

## 테스트와 데이터 보호

기본 전체 테스트 명령은 다음과 같습니다.

```powershell
python -m pytest tests/
```

루트 `conftest.py`는 테스트 수집 전에 자동 `.env` 로딩과 저장소 `.env` 직접 읽기를
차단하고, 실행 셸에서 상속된 앱 설정을 제거합니다. 필요한 설정은 테스트가 명시적인
합성 값으로 제공합니다. 이 보호는 일반 fixture보다 먼저 적용되며 운영 실행에는 적용되지 않습니다.
테스트는 `tests/conftest.py`가 준비한 임시 SQLite DB와 임시 백업 경로를
사용합니다. 실제 `data/bot_database.db`, 실제 SQL 백업, Discord, Gemini,
YouTube, GitHub와 systemd에는 접근하지 않습니다.

Linux process 종료 회귀는 명시적으로 선택한 비운영 Linux/systemd 환경에서만 실행합니다.
기본 suite에서는 건너뛰며, 선택 실행은 임시 사용자 systemd 단위를 실제로 만들고 정리합니다.
검증한 Ubuntu WSL의 native Linux 후보 소스 디렉터리에서 해당 Python 3.12 venv를 사용합니다.

```bash
A2_LINUX_PROCESS_TESTS=1 ../.venv/bin/python -B -m pytest tests/integration/test_termination_linux.py -q -p no:cacheprovider
```

운영 서비스 이름이나 자격증명은 사용하지 않습니다. Windows는 일반 단위·통합 테스트 환경이며,
관리된 V2 실행 진입점의 process-tree 종료 보장은 Linux guardian과 systemd를 요구합니다.

종료되지 않은 비동기 작업을 더 엄격하게 검사하려면 다음 명령을 사용합니다.

```powershell
python -m pytest tests/ -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

테스트 개수는 기능 추가에 따라 달라지므로 문서의 고정 숫자보다 실행 결과를
기준으로 판단합니다. Python 3.12에서는 Discord 음성 재생이 사용하는 `audioop`
지원 종료 예고가 표시될 수 있으며, Python 3.13 전환 전에 별도 호환 검증이
필요합니다.

## 데이터와 백업

- 현재 V2 운영 데이터 경로는 명시적인 배포 설정으로 결정됩니다. 기존 V1의
  `data/bot_database.db`와 아래 백업 설명은 호환성·복구 계약의 배경이며,
  현재 백업·복구 명령은 [운영 절차](deploy/runbooks/README.md)를 따릅니다.
- 최근 SQL 백업은 `DB_BACKUP_REMOTE_URL`로 지정한 별도 비공개
  [`lgw323/Bot-Data`](https://github.com/lgw323/Bot-Data) 저장소의
  `db-backup` 브랜치에 단일 커밋으로 갱신됩니다. 코드 저장소에는 DB 백업
  브랜치를 두지 않습니다.
- Pi의 `data/archives/`에는 최근 7일의 로컬 SQL 백업이 보관됩니다.
- 백업 파일 전체를 Fernet으로 암호화하므로 사용자·서버 ID, 생일, 음악 취향과
  테이블 구조가 원격 저장소에서 평문으로 보이지 않습니다.
- `DB_ENCRYPTION_KEY`가 없거나 잘못되면 평문 백업을 만들지 않습니다. 새 덤프는
  임시 파일에서 SQL 검증과 암호화 왕복 검사를 통과한 뒤에만 기존 백업과
  교체되므로, 실패하면 마지막 정상 백업이 유지됩니다.
- `DB_BACKUP_REMOTE_URL`이 없으면 공개 코드 저장소로 우회하지 않고 원격
  업로드와 무데이터 복구를 중단합니다.
- 새 전체 암호화 형식뿐 아니라 기존의 필드 암호화 SQL 백업도 같은 키로 복구할
  수 있습니다.

현재 데이터 정책, 기능 의도와 남아 있는 위험은
[제품 명세](docs/product-spec.md)에 기록합니다.

## 프로젝트 구조

| 위치 | 역할 |
| --- | --- |
| `src/discordbot/` | 현재 V2 platform, 저장소, Engagement, Summary, Music, Watch와 composition |
| `compatibility/v1/` | 출처와 해시가 기록된 DB·Engagement·Music 비교 참조; 운영 runtime에서 import 금지 |
| `scripts/` | 격리된 데이터 호환성 리허설과 명시적으로 선택하는 검증 도구 |
| `deploy/` | V2 immutable release, systemd 자산과 운영 절차 |
| `tests/` | V2 동작, 보존된 V1 비교 계약, 자격 증명 경계와 architecture 검사 |
| `docs/` | 제품 명세, 운영 절차와 과거 작업 기록 |

## 문서 안내

| 문서 | 책임 |
| --- | --- |
| `README.md` | 기능 개요와 로컬 시작 방법 |
| `docs/product-spec.md` | 제품 의도, 유지해야 할 동작과 알려진 위험 |
| `docs/system-design.md` | 전체 기능의 유즈케이스, 구성요소와 실행 흐름 |
| `docs/music-engine-rebuild-plan.md` | 음악 403 분석과 안전한 재생 엔진 교체 계획 |
| `docs/rebuild/README.md` | V2 요구사항, ADR, 단계별 구현·검증 보고서 |
| `docs/operations.md` | Raspberry Pi 설치·운영·복구 절차 |
| `AGENTS.md` | 이 저장소에서 작업하는 코딩 에이전트의 규칙 |
| `CHANGELOG.md` | 실제로 완료된 변경 이력 |

V2 `src` package의 Python 3.12/setuptools build metadata는 `pyproject.toml`에 정의되어
있습니다. V2 실행·배포 entrypoint와 systemd 자산은 구현됐으며, 실제 설치 전
[운영 절차](deploy/runbooks/README.md)와 [PHASE 8 보고서](docs/rebuild/phases/phase-08/phase-8-report.md)를
검토합니다. 루트 V1 실행 경로는 제거했으며 필요한 비교 참조만 격리해 보존합니다. 별도의 lint, formatting, type-checking 명령은 없습니다.

## Required source and installed test lanes

For the reusable guarded source command and synthetic cutover/WAL checks, see
[local tooling and tests](docs/local-tooling.md). The runner uses the existing
Python 3.12 development environment and fresh temporary fixtures.

The full source-review/development/commit gate remains `python -m pytest tests/`.
It includes the mandatory measurement regressions
`tests/integration/operations/test_a9_local_harness.py` and
`tests/integration/operations/test_a9_candidate_packet.py`, plus the historical
Git proofs in `tests/integration/source_review/test_a9_bt1_history.py`. A focused source check
does not replace that full gate:

```powershell
python -B docs/rebuild/final-audit/a8r4-test-runner.py tests/integration/operations/test_a9_local_harness.py tests/integration/operations/test_a9_candidate_packet.py tests/integration/source_review/test_a9_bt1_history.py --confcutdir=tests/integration -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -o xfail_strict=true
```

Installed admission is also mandatory. From the isolated candidate's `app`
directory, using its reviewed interpreter, its selection is:

```text
python -B -m pytest tests/integration/operations --confcutdir=tests/integration/operations --ignore=tests/integration/operations/test_a9_local_harness.py --ignore=tests/integration/operations/test_a9_candidate_packet.py -p no:cacheprovider -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -o xfail_strict=true
```

The two exact exclusions apply before collection because these tools require
source scripts, audit documents and Git provenance. They are not skips or waivers;
no other operations module is excluded. Both deployment callers use the shared
selection policy, and keep their existing 300-second timeout and warning controls
(the production verifier also retains strict xfail). Never add a source-tree
fallback to an installed admission run. Counts change as tests are added; evidence
must record test identities and actual source hashes, including dirty work.
The mixed A9-BT1 test's current configuration/fetch routing remains installed;
only its original fixed-commit proofs moved to source review. Disposable local-Git
backup drills and the isolated staging-interpreter probe remain installed coverage.
See the [bounded correction and local evidence](docs/rebuild/final-audit/admission-selection-evidence-20261009.md)
for guarded reproduction, partition proof and remaining gates.
