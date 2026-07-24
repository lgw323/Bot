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

## 빠른 시작

1. `envtemplate.txt`를 참고해 프로젝트 루트에 `.env`를 준비합니다.
2. 가상환경을 만들고 필요한 패키지를 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

3. 전체 테스트를 실행합니다.

```powershell
python -m pytest tests/
```

4. 봇을 실행합니다.

```powershell
python main_bot.py
```

실제 Raspberry Pi 설치와 systemd·cron 설정은
[배포 안내](docs/deployment-guide.md)를 따릅니다.

## 데이터와 백업

- 운영 데이터는 Git에서 제외된 `data/bot_database.db`에 저장됩니다.
- 최근 SQL 백업은 `DB_BACKUP_REMOTE_URL`로 지정한 별도 비공개 저장소의
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

현재 데이터 정책과 남아 있는 위험은
[프로젝트 배경과 설계 의도](docs/project-context.md)에 기록합니다.

## 프로젝트 구조

| 위치 | 역할 |
| --- | --- |
| `main_bot.py` | 프로그램 시작, Discord 연결과 기능 모듈 로드 |
| `database_manager.py` | SQLite 스키마, 데이터 읽기·쓰기와 SQL 백업·복구 |
| `cogs/` | 음악, 요약, 레벨링, 생일, 로깅, Watch Together 기능 |
| `scripts/` | Pi 자동 업데이트와 DB 백업 |
| `tests/` | 현재 동작과 회귀를 확인하는 pytest 테스트 |
| `docs/` | 프로젝트 배경, 배포와 테스트 안내 |

## 문서 안내

| 문서 | 책임 |
| --- | --- |
| `README.md` | 기능 개요와 로컬 시작 방법 |
| `docs/project-context.md` | 제품 의도, 유지해야 할 동작과 알려진 위험 |
| `docs/deployment-guide.md` | Raspberry Pi 설치·운영·복구 절차 |
| `docs/test-guide.md` | 현재 테스트 범위와 실행 방법 |
| `docs/refactoring-report.md` | 이번 리팩터링의 목적·변경 내용·검증 결과 |
| `AGENTS.md` | 이 저장소에서 작업하는 코딩 에이전트의 규칙 |
| `CHANGELOG.md` | 실제로 완료된 변경 이력 |

별도의 build, lint, formatting, type-checking 명령은 현재 저장소에 정의되어 있지
않습니다.
