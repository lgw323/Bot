# AI Agent System Directives (Project Context)

본 문서는 대형 언어 모델(LLM) 기반 코딩 에이전트가 본 프로젝트에 기여할 때 반드시 준수해야 하는 최상위 제약 조건(Constraints) 및 도메인 지식입니다. 에이전트는 코드 분석 및 생성 시 이 문서의 원칙을 최우선으로 적용해야 합니다.

---

## 🌍 1. Environment Boundary (환경 분리 원칙)

본 프로젝트는 코드 작성 환경과 실제 배포/운영 환경이 철저히 분리되어 있습니다.

- **Dev Environment (Main PC)**: 코드 에디팅 및 GitHub Push 수행.
- **Prod Environment (Raspberry Pi 5)**: GitHub Pull 및 실제 봇 구동. Linux(Ubuntu/Debian) OS 사용.

> [!IMPORTANT]
> **[Constraint 1]**: 파일 경로, 프로세스 관리, 외부 시스템 호출 등 운영체제 종속적인 코드를 작성할 경우, 반드시 **Linux 환경(Prod)**을 기준으로 작동하도록 작성하십시오. 로컬 테스트를 위한 임시 경로나 Windows 전용 모듈 사용을 엄격히 금지합니다.

---

## 🏗️ 2. Architecture & SRP (단일 책임 원칙)

디스코드 봇의 구조는 다음과 같이 분리되어 있습니다. 지정된 책임을 벗어나는 코드 배치를 금지합니다.

- **`main_bot.py`**: 시스템 진입점(Entry Point). Cog 로드, 전역 이벤트 등록, 봇 인증 로직만 포함합니다. 비즈니스 로직 삽입을 금지합니다.
- **`database_manager.py`**: SQLite DB 연결 및 테이블 스키마 관리 매니저. DB Lock 방지를 위해 모든 DB 커넥션 관리는 이곳으로 중앙집중화합니다.
- **`cogs/`**: 독립적인 기능 모듈 디렉토리.
    - `music/`: 음악 컨트롤러(`music_agent`), 코어 스트리밍(`music_core`), 인터페이스(`music_ui`) 구조 유지.
    - `summary/`: 리스너와 AI 요약 에이전트 분리.
    - `leveling/`: 채팅/음성 경험치 연산 및 역할(Role) 부여 로직.
    - `logging/`: 전역 로깅 하이재킹 및 디스코드 원격 에러 알림.
- **`tests/`**: TDD 및 시스템 무결성 검증을 위한 `pytest` 기반 테스트 코드 디렉토리.
- **`scripts/`, `docs/`**: 리눅스 쉘 스크립트(`.sh`) 및 문서. 파이썬 코드와 섞이지 않도록 격리합니다.

> [!WARNING]
> **[Constraint 2]**: 새로운 기능을 추가할 경우 기존 `main_bot.py`를 비대하게 만들지 말고, `cogs/` 하위에 새로운 모듈로 분리하여 제안하십시오.

---

## 🛠️ 3. Code Generation & Refactoring Rules

- **[Constraint 3] 불변성 유지**: 리팩토링 요청 시, 코드의 가독성 및 구조만 개선하며 기존에 구현된 기능, 이벤트, 명령어의 실행 결과는 100% 보존해야 합니다.
- **[Constraint 4] Type Hinting**: 모든 함수, 클래스, 메서드에 Python Type Hint를 의무적으로 적용하십시오.
- **[Constraint 5] Error Handling**: 기능 추가 시 봇의 크래시(Crash)를 방지하기 위해 `try-except` 블록을 필수적으로 구성하고, 전역 `logger`를 사용하여 에러를 기록하십시오. (`print()` 사용 금지)

---

## 📝 4. Git Commit Convention

버전 관리를 위해 **Angular Commit Convention**을 준수합니다. 에이전트가 커밋 메시지를 생성할 때 다음 포맷을 사용하십시오. 커밋시 파일 하나씩 개별로 진행하십시오.

### Format
`<type>[optional scope]: <description in Korean>`

### Types
- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `refactor`: 코드 리팩토링 (기능 변화 없음)
- `style`: 코드 포맷팅 (동작 변화 없음)
- `docs`: 문서 수정
- `chore`: 빌드, 스크립트 등 기타 잡무

**Example**: `feat: 레벨링 기능에 음성 채널 체류 시간 연산 추가`

---

## 📜 5. 시스템 업데이트 및 변경 이력 관리 (Changelog)

대규모 리팩토링이나 아키텍처 업데이트가 발생할 경우, 다른 개발자나 AI 에이전트가 단번에 개발 및 유지보수 흐름을 파악할 수 있도록 프로젝트 루트 디렉토리에 있는 `CHANGELOG.md` 문서에 패치노트를 반드시 기록해야 합니다.

### 작성 원칙 (Keep a Changelog)
- **버전명 부여 규칙 (Semantic Versioning)**: `vX.Y.Z` 포맷 사용
  - **Major (X)**: 기존 코드와 전혀 호환되지 않는 코어 엔진 교체, DB 모델 대규모 변경.
  - **Minor (Y)**: 눈에 띄는 새로운 거대 기능 추가, 아키텍처의 대규모 구조 개선.
  - **Patch (Z)**: 작고 가벼운 버그 수정, 텍스트(오타) 수정, 내부 로직의 단순 속도 최적화.
- **분류 태그 (Tags)**
  수정 사항을 무작위로 나열하지 말고, 아래 태그로 그룹화하여 직관적으로 기술하십시오.
  - `[Added]`: 완전히 새로운 기능 설계/추가
  - `[Changed]`: 기존 기능의 동작 방식/루틴 변경
  - `[Fixed]`: 발견된 버그 및 취약점에 대한 직접적 수정
  - `[Security]`: 보안 정책 강화 및 데이터 노출 방어 기법 탑재
