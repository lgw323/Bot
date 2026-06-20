import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import database_manager
from fastapi.testclient import TestClient
from cogs.watch_together.watch_server import app

# 테스트 실행 전 DB 스키마 초기화
@pytest.fixture(scope="module", autouse=True)
def setup_db():
    database_manager.init_db()

# 1. DB CRUD 테스트
@pytest.mark.asyncio
async def test_watch_db_operations():
    session_id = str(uuid.uuid4())
    guild_id = 99999
    user_id = 11111
    
    # 1-1. 세션 등록 테스트
    await database_manager.add_watch_session(session_id, guild_id, user_id)
    session = await database_manager.get_watch_session(session_id)
    assert session is not None
    assert session["guild_id"] == guild_id
    assert session["created_by"] == user_id
    
    # 1-2. 공유 대기열 추가 테스트
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_title = "Never Gonna Give You Up"
    added_by = "테스터"
    
    await database_manager.add_to_watch_playlist(session_id, video_url, video_title, added_by)
    playlist = await database_manager.get_watch_playlist(session_id)
    assert len(playlist) == 1
    assert playlist[0]["video_title"] == video_title
    assert playlist[0]["added_by"] == added_by
    
    # 1-3. 공유 대기열 제거 테스트
    await database_manager.remove_from_watch_playlist(session_id, video_url)
    playlist = await database_manager.get_watch_playlist(session_id)
    assert len(playlist) == 0
    
    # 1-4. 세션 삭제 테스트
    await database_manager.delete_watch_session(session_id)
    session = await database_manager.get_watch_session(session_id)
    assert session is None


# 2. FastAPI Endpoint 테스트
client = TestClient(app)

@pytest.mark.asyncio
async def test_watch_server_endpoints():
    session_id = str(uuid.uuid4())
    
    # 2-1. 존재하지 않는 세션 시청 페이지 조회 시 404
    response = client.get(f"/watch?session={session_id}")
    assert response.status_code == 404
    
    # 임시 세션 등록 후 정상 응답 테스트
    await database_manager.add_watch_session(session_id, 888, 999)
    try:
        # 2-2. 정상 세션 시청 페이지 조회 (200 OK)
        response = client.get(f"/watch?session={session_id}")
        assert response.status_code == 200
        assert "Watch Together" in response.text
        
        # 2-3. API를 통한 플레이리스트 조회 (빈 값)
        response = client.get(f"/api/playlist/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "playlist" in data
        assert len(data["playlist"]) == 0
        
        # 2-4. API를 통한 비디오 추가
        # oembed 호출은 Mocking 하거나 패스
        with patch("aiohttp.ClientSession.get") as mock_get:
            # mock response
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"title": "Mock YouTube Video"})
            
            # mock_get.return_value.__aenter__ 의 리턴값을 mock_resp 로 설정
            mock_get.return_value.__aenter__.return_value = mock_resp
            
            response = client.post(
                f"/api/playlist/{session_id}/add",
                json={"video_url": "https://www.youtube.com/watch?v=123", "added_by": "테스터"}
            )
            assert response.status_code == 200
            
        # 2-5. 추가 이후 플레이리스트 재조회 검증
        response = client.get(f"/api/playlist/{session_id}")
        data = response.json()
        assert len(data["playlist"]) == 1
        
    finally:
        # 정리
        await database_manager.delete_watch_session(session_id)
