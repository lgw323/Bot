# DiscordBot Agent Rules

이 문서는 DiscordBot 프로젝트를 수정하는 AI 에이전트와 개발자가 따라야 할 작업 원칙을 정의합니다.
이 프로젝트는 친구들이 사용하는 단일 Discord 커뮤니티의 음악 봇에서 시작했으며, 음악 재생, 대화 요약,
경험치와 생일 관리, Watch Together, 관리자 로그 기능을 함께 제공합니다.

## 1. 가장 중요한 원칙

### 기존 사용자 동작 보존

- 리팩터링은 Discord 명령어 이름, 응답 문구, 공개/비공개 응답 방식, 버튼 동작을 바꾸지 않는 것을 기본으로 합니다.
- 음악 대기열, 반복 모드, 자동 재생, 즐겨찾기, 재시작 후 복원 동작을 유지합니다.
- Watch Together의 URL, HTTP endpoint, WebSocket message 형식, 30초 개설 유예와 5초 퇴장 유예를 유지합니다. 개인 관리 서버의 세션 종료 버튼은 관리자만 사용할 수 있으며, 종료 시 접속자·초대 메시지·세션·대기열을 함께 정리합니다.
- SQLite schema, SQL 백업 형식, `music_state.json` 형식은 명시적인 승인 없이 변경하지 않습니다.
- 동작 변경이 필요한 버그 수정은 기존 동작과 수정 후 동작을 먼저 설명하고 승인을 받습니다.

### 작은 변경과 검증

- 대규모 일괄 변경보다 하나의 책임과 하나의 위험을 다루는 작은 변경을 우선합니다.
- 버그 수정과 구조 변경 전에는 가능한 경우 현재 동작을 기록하는 characterization test를 먼저 추가합니다.
- 한 기능을 수정한 뒤 관련 test를 실행하고, 마지막에 전체 test를 실행합니다.
- 현재 repository에는 별도의 build, lint, formatting, type-checking 명령이 정의되어 있지 않습니다. 존재하지 않는 명령을 추측해 사용하지 않습니다.

### 실제 사용자 데이터 보호

- test는 실제 `data/bot_database.db`나 실제 SQL 백업을 읽거나 수정하면 안 됩니다.
- DB test는 `tmp_path` 등으로 만든 임시 DB와 임시 backup path만 사용합니다.
- `.env`, Discord token, API key, encryption key, 실제 DB 값과 로그 내용을 출력하거나 commit하지 않습니다.
- `*.db`, `*.sql`, `data/logs/`, 임시 음악 상태와 TTS cache를 새로 Git에 추가하지 않습니다.
- 이미 추적 중인 backup이나 Git history를 제거 또는 rewrite하는 작업은 별도 승인 없이 수행하지 않습니다.
- migration, backup 복구, 원격 branch 변경처럼 되돌리기 어려운 작업은 대상과 rollback 방법을 먼저 확인합니다.

## 2. 프로젝트 구조와 책임

### 시작과 기능 연결

- `main_bot.py`는 환경 설정 로드, bot 생성, Cog 로드, command 동기화, application lifecycle만 담당합니다.
- 새로운 비즈니스 로직을 `main_bot.py`에 직접 추가하지 않습니다.
- startup을 수정할 때는 DB가 필요한 기능이나 웹 요청이 DB 준비보다 먼저 실행되지 않도록 순서를 검증합니다.

### 데이터 저장

- `database_manager.py`의 기존 public async 함수는 다른 기능이 사용하는 내부 API로 간주합니다.
- 연결 설정, schema 준비, backup/restore, 기능별 CRUD를 분리할 때도 public 함수의 입력과 반환 형식을 유지합니다.
- SQLite WAL과 PRAGMA 정책은 `docs/product-spec.md`의 기존 운영 의도를 확인한 뒤 변경합니다.
- 사용자 ID는 민감한 데이터로 취급합니다. 음악 취향을 드러낼 수 있는 URL과 제목도 보호 대상입니다. 새 원격 백업은 SQL 구조를 포함한 파일 전체를 `DB_ENCRYPTION_KEY`로 암호화하며, 같은 키 없이는 복구할 수 없어야 합니다.
- 원격 백업은 `DB_BACKUP_REMOTE_URL`로 지정한 별도 비공개 저장소의 `db-backup` 브랜치만 사용합니다. 설정이 없을 때 공개 코드 저장소로 우회하지 않습니다.
- 기존 일부 필드 암호화 방식의 백업은 복구 호환성을 유지하되, 새 백업은 전체 파일 암호화 형식으로만 생성합니다.
- backup이 없을 때 새 DB를 만드는 정책은 아직 구현되지 않았으므로, 관련 변경 전 test와 복구 정책을 먼저 확정합니다.

### Discord 기능

- `cogs/` 아래에서 기능별 책임을 유지합니다.
- `music/`은 요청 처리, 실제 재생, Discord UI, 상태 저장 책임을 단계적으로 분리하되 외부 동작은 유지합니다.
- 음악 채널은 대화용이 아닌 전용 jukebox 채널입니다. 기존 dashboard 유지와 메시지 정리 동작을 보존합니다.
- 음악 즐겨찾기는 guild별이 아니라 Discord 사용자별 공용 목록입니다. 명시적 요청 없이 guild 범위를 추가하지 않습니다.
- 재시작 후에는 이전 음성 채널, 재생 위치, 대기열, 반복·자동 재생 설정을 모두 복원하는 것을 목표 동작으로 유지합니다.
- `summary/`는 메시지 수집과 Gemini 통신을 구분합니다.
- `leveling/`과 `birthday/`는 기존 XP 공식, 사용자 데이터, 알림 시간을 보존합니다.
- 요약 대상 채널과 생일 알림 채널은 친구들이 대화하는 같은 메인 채널을 사용하는 것이 현재 의도입니다.
- `watch_together/`는 Discord 초대, FastAPI/WebSocket 서버, 브라우저 화면을 구분합니다.
- Watch Together는 신뢰하는 친구들이 초대 링크를 공유하는 방식입니다. 별도 로그인이나 방장 권한을 임의로 추가하지 않되, 개인 관리 서버에는 새 세션 알림과 관리자 전용 강제 종료 수단을 유지합니다. 브라우저 입력값에는 escaping과 validation을 적용합니다.
- `logging/`은 다른 library의 handler를 무조건 제거하거나 reconnect마다 중복 handler를 추가하지 않도록 주의합니다.

## 3. 환경과 운영 규칙

- 개발 환경은 Windows이며, 실제 운영 환경은 Raspberry Pi의 Linux입니다.
- 운영 server는 실행 전용으로 간주하며 `/home/os/bot`, `bot_env`, systemd와 cron 경로를 명시적 승인 없이 변경하지 않습니다.
- 운영체제 종속 코드와 shell script는 Linux 운영 환경을 기준으로 작성합니다.
- Python dependency를 추가하거나 제거할 때는 `requirements.txt` 또는 `requirements-dev.txt`에 직접 dependency를 기록합니다.
- 일반 dependency의 무조건적인 최신화는 피합니다. `yt-dlp`는 YouTube 변경 대응 때문에 별도 update 정책이 필요한 예외 후보입니다.
- package 설치, dependency upgrade, systemd 재시작, Git force push는 사용자의 명시적인 요청 없이 실행하지 않습니다.
- 자동 update가 실패했을 때 현재 정상 버전을 보존하고 원인을 기록하는 방향을 우선하며, 무한 재시도나 무조건 restart를 새로 추가하지 않습니다.

## 4. Test 원칙

- 기본 전체 test 명령은 `pytest tests/`입니다.
- test 실행 전에 test가 실제 DB, network, Discord, Gemini, YouTube, systemd에 접근하지 않는지 확인합니다.
- 외부 통신은 mock 또는 fake adapter로 대체합니다.
- background task, Uvicorn server, Discord View, logging handler는 test 종료 시 정리합니다.
- DB 변경은 임시 DB에서 schema, CRUD, backup, restore를 검증합니다.
- 음악 변경은 queue, loop, pause/resume, TTS interruption, state save/restore를 가능한 한 fake voice client로 검증합니다.
- Watch Together 변경은 HTTP뿐 아니라 WebSocket join/disconnect, session expiry, 입력 escaping, 관리자 강제 종료와 재시작 뒤 오래된 세션 정리를 검증합니다.
- 테스트를 실행할 수 없는 환경이면 성공했다고 추측하지 말고 원인과 미검증 범위를 명시합니다.

## 5. 코드 작성 규칙

- 함수와 method에는 가능한 한 정확한 type hint를 사용합니다. `any` 대신 `typing.Any`를 사용합니다.
- 오류를 조용히 무시해야 하는 명확한 이유가 없다면 `except: pass`를 새로 추가하지 않습니다.
- 사용자에게 보여줄 오류와 운영 로그에 남길 오류를 구분합니다.
- `print()` 대신 module logger를 사용합니다.
- module import나 객체 생성만으로 server, DB migration, network call 같은 큰 side effect가 발생하지 않도록 합니다.
- global state를 추가하기보다 생성자 인자나 작은 설정 객체로 dependency를 전달하는 방식을 우선합니다.
- 기존 public symbol을 dead code로 판단하더라도 repository 내부 참조, test, 운영 script 사용 여부를 확인한 뒤 제거합니다.

## 6. 문서와 변경 기록

- `README.md`에는 기능 개요, 로컬 시작 방법과 문서 안내만 둡니다.
- `docs/product-spec.md`에는 제품 의도, 유지할 동작과 알려진 위험을 기록합니다.
- `docs/operations.md`에는 Raspberry Pi 설치·운영·복구 절차만 기록합니다.
- `docs/archive/`에는 완료된 과거 작업의 시점별 보고서만 보관하며 현재 사양의
  근거로 사용하지 않습니다.
- 테스트 실행 방법은 `README.md`, 테스트 작업 원칙은 이 `AGENTS.md`, 기능별
  유지 계약은 `docs/product-spec.md`에서 관리합니다.
- 이 `AGENTS.md`에는 코딩 에이전트의 작업 규칙만 두고 제품 설명을 중복해 늘리지 않습니다.
- 사용자 기능, 실행 명령, 설정값, backup 정책을 변경하면 책임이 맞는 문서를 함께 확인합니다.
- 의미 있는 기능 또는 구조 변경은 `CHANGELOG.md`에 기록합니다.
- 확인되지 않은 사실을 문서에 확정적으로 적지 않습니다.
- 현재 프로젝트는 한 개의 친구용 서버와 한 개의 개인 관리용 서버에서 사용되지만, guild별 데이터 구조의 확장 가능성을 불필요하게 제거하지 않습니다.

## 7. Git과 작업 안전

### 원자적 커밋

- 하나의 커밋은 하나의 기능, 버그, 리팩터링 또는 문서 책임만 다룹니다.
- 서로 독립적으로 설명하거나 되돌릴 수 있는 변경은 별도 커밋으로 나눕니다.
- 파일이 다르다는 이유만으로 기계적으로 나누지 않습니다. 구현과 그 구현을
  검증하는 test는 함께 있어야 커밋이 정상 동작한다면 같은 커밋에 둡니다.
- 기능 구현, 독립적인 문서 정리와 관련 없는 리팩터링을 한 커밋에 섞지 않습니다.
- 각 커밋은 가능한 한 그 시점에서 관련 test를 통과하고 독립적으로 revert할 수
  있어야 합니다.
- commit 전 `git diff --cached --check`와 staged diff를 확인해 의도하지 않은
  파일, 실제 데이터와 비밀 정보가 포함되지 않았는지 검사합니다.
- commit message는 `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:` 등으로
  책임을 구분하고, 같은 작업에서 의미가 겹치는 message를 반복하지 않습니다.

### Pull Request

- PR은 목적, 주요 변경, 호환성·영향 범위, 테스트 결과, 롤백 방법과 체크리스트를
  포함합니다.
- PR을 만들기 전에 commit 목록이 책임별로 분리됐는지와 최종 diff가 요청 범위만
  포함하는지 확인합니다.
- 자동 검사가 없더라도 관련 test와 전체 test의 실제 실행 결과를 PR에 기록합니다.
- merge 전에 base branch와 충돌 여부, 승인되지 않은 동작·데이터 형식 변경이
  없는지 확인합니다.

- 사용자가 만든 기존 변경을 보존하고 관련 없는 파일을 되돌리지 않습니다.
- `.env`, 실제 DB, SQL backup, log, cache를 commit하지 않습니다.
- `git reset --hard`, history rewrite, force push는 사용자의 명시적인 요청 없이 실행하지 않습니다.
- 각 변경의 검증 방법과 rollback 방법을 commit 또는 PR에 남깁니다.
