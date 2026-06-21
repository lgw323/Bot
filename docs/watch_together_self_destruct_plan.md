# [임시 보관] Watch Together 세션 자동 소멸(Self-Destruct) 시스템 설계서

> [!NOTE]
> 본 설계서는 UI/UX 통합 및 개선 프로젝트가 완료된 이후 재개할 예정입니다. 본 기능 구현이 완료되면 이 파일은 삭제됩니다.

사용자가 웹 브라우저를 모두 닫거나 퇴장하여 방에 아무도 남지 않게 되었을 때, 서버 메모리(웹소켓 커넥션)뿐만 아니라 데이터베이스(SQLite)에서도 세션 정보 및 공유 대기열 데이터를 자동으로 청소(Self-Destruct)하는 기능입니다.

## 핵심 요구사항 및 설계

### 1. 페이지 새로고침(F5) 유예 시간 (Grace Period)
- 인터넷이 일시적으로 끊기거나 사용자가 새로고침을 할 때 세션이 즉시 삭제되는 문제를 방지하기 위해 **5초의 유예 시간**을 적용합니다.
- 마지막 유저가 접속을 종료한 시점부터 5초 뒤에 활성 연결이 여전히 0명일 때만 DB에서 세션을 완전히 삭제합니다.

### 2. 제안된 변경 사항 (Proposed Changes)

#### cogs/watch_together/watch_server.py
- `database_manager`에서 `delete_watch_session`을 임포트합니다.
- 마지막 유저가 접속을 종료해 `active_connections`에서 웹소켓 목록이 비게 될 때, `asyncio.create_task`를 활용해 5초 대기 후 세션 파기 여부를 검사하고 삭제하는 백그라운드 태스크를 기동합니다.
- 예시 코드 흐름:
  ```python
  async def self_destruct_session(session_id: str, delay: float = 5.0):
      await asyncio.sleep(delay)
      # 5초 대기 후 세션에 다시 들어온 사람이 없는지 확인
      if session_id not in manager.active_connections or not manager.active_connections[session_id]:
          logger.info(f"Self-destructing session {session_id} due to inactivity (0 users).")
          await delete_watch_session(session_id)
  ```

## 검증 계획 (Verification Plan)

### Automated Tests
- `tests/test_watch_together.py` 내부에 테스트 코드를 추가하거나 수정하여, 세션 연결이 종료된 후 5초 뒤에 DB에서 정상 삭제되는지 확인합니다.

### Manual Verification
1. 디스코드 봇으로 `/시청` 방 생성.
2. 생성된 웹 링크로 접속 후, 창을 닫아 접속 종료.
3. 5초 대기 후 브라우저에 해당 링크 재접속 시 "유효하지 않거나 만료된 세션입니다" 페이지가 나타나는지 확인.
4. SQLite DB에서 `watch_sessions`와 `watch_playlists` 데이터가 지워졌는지 확인.
