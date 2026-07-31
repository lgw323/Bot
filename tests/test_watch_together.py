import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import database_manager
from fastapi.testclient import TestClient
from cogs.watch_together.watch_server import app
from cogs.watch_together.watch_agent import WatchAgentCog

# 테스트 실행 전 DB 스키마 초기화
@pytest.fixture(scope="module", autouse=True)
def setup_db(isolated_database):
    database_manager.init_db()

# 1. DB CRUD 테스트
@pytest.mark.asyncio
async def test_watch_db_operations():
    session_id = str(uuid.uuid4())
    guild_id = 99999
    user_id = 11111
    
    # 1-1. 세션 등록 테스트
    channel_id = 12345
    message_id = 67890
    await database_manager.add_watch_session(session_id, guild_id, user_id, channel_id, message_id)
    session = await database_manager.get_watch_session(session_id)
    assert session is not None
    assert session["guild_id"] == guild_id
    assert session["created_by"] == user_id
    assert session["channel_id"] == channel_id
    assert session["message_id"] == message_id
    
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
        assert 'href="/watch-assets/watch.css"' in response.text
        assert '<main class="app-shell">' in response.text
        assert 'role="log"' in response.text
        assert 'aria-live="polite"' in response.text
        assert 'id="session-participant-count"' in response.text
        assert 'id="sync-status"' in response.text
        assert 'role="tablist"' in response.text
        assert "공동 제어" in response.text
        assert "호스트" not in response.text
        rendered_body = response.text.split("<body>", 1)[1]
        assert "WATCH NODE" not in rendered_body
        assert "SECURE CHANNEL" not in rendered_body
        assert "Signal Nominal" not in rendered_body
        assert "QUEUE/01" not in rendered_body
        assert "COMMS/02" not in rendered_body
        
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
                json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "added_by": "테스터"}
            )
            assert response.status_code == 200
            
        # 2-5. 추가 이후 플레이리스트 재조회 검증
        response = client.get(f"/api/playlist/{session_id}")
        data = response.json()
        assert len(data["playlist"]) == 1
        
    finally:
        # 정리
        await database_manager.delete_watch_session(session_id)


def test_watch_design_system_stylesheet_is_served():
    response = client.get("/watch-assets/watch.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--canvas:" in response.text
    assert "--orange:" in response.text
    assert "--line:" in response.text
    assert "--space-4:" in response.text
    assert "--motion-state:" in response.text
    assert "@media (prefers-reduced-motion: reduce)" in response.text


@pytest.mark.asyncio
async def test_watch_server_self_destruct():
    from cogs.watch_together.watch_server import self_destruct_session, manager
    
    session_id_empty = str(uuid.uuid4())
    session_id_active = str(uuid.uuid4())
    guild_id = 777
    user_id = 999
    
    # 1. 두 세션 등록
    await database_manager.add_watch_session(session_id_empty, guild_id, user_id)
    await database_manager.add_watch_session(session_id_active, guild_id, user_id)
    
    # 2. active 세션에 모의 커넥션 추가
    manager.active_connections[session_id_active] = ["mock_websocket"]
    
    try:
        # 3. 두 세션에 대해 self_destruct_session 실행 (유예 시간 0.05초, 테스트용 유예 우회 적용)
        await self_destruct_session(session_id_empty, delay=0.05, ignore_grace=True)
        await self_destruct_session(session_id_active, delay=0.05, ignore_grace=True)
        
        # 4. 검증
        # 빈 세션은 삭제되어야 함
        session_empty = await database_manager.get_watch_session(session_id_empty)
        assert session_empty is None
        
        # 활성 세션은 남아있어야 함
        session_active = await database_manager.get_watch_session(session_id_active)
        assert session_active is not None
        
    finally:
        # 정리
        if session_id_active in manager.active_connections:
            del manager.active_connections[session_id_active]
        await database_manager.delete_watch_session(session_id_empty)
        await database_manager.delete_watch_session(session_id_active)


@pytest.mark.asyncio
async def test_admin_close_disconnects_users_and_removes_session():
    from cogs.watch_together.watch_server import close_watch_session, manager

    session_id = str(uuid.uuid4())
    websocket = AsyncMock()
    await database_manager.add_watch_session(session_id, 123, 456)
    await database_manager.add_to_watch_playlist(
        session_id,
        "https://youtu.be/admin-close",
        "Close Me",
        "tester",
    )
    manager.active_connections[session_id] = [websocket]
    manager.user_names[session_id] = {websocket: "tester"}

    closed = await close_watch_session(
        session_id,
        reason="관리자 강제 종료",
    )

    assert closed is True
    websocket.close.assert_awaited_once()
    assert session_id not in manager.active_connections
    assert session_id not in manager.user_names
    assert await database_manager.get_watch_session(session_id) is None
    assert await database_manager.get_watch_playlist(session_id) == []


@pytest.mark.asyncio
async def test_stale_sessions_can_be_listed_for_startup_cleanup():
    session_id = str(uuid.uuid4())
    await database_manager.add_watch_session(session_id, 321, 654)

    try:
        sessions = await database_manager.get_all_watch_sessions()
        assert any(session["session_id"] == session_id for session in sessions)
    finally:
        await database_manager.delete_watch_session(session_id)


@pytest.mark.asyncio
async def test_watch_agent_cleans_only_stale_sessions_once():
    from cogs.watch_together.watch_server import manager

    stale_id = "stale-session"
    active_id = "active-session"
    manager.active_connections[active_id] = [object()]
    cog = WatchAgentCog(MagicMock())

    try:
        with patch(
            "cogs.watch_together.watch_agent.get_all_watch_sessions",
            new_callable=AsyncMock,
            return_value=[
                {"session_id": stale_id},
                {"session_id": active_id},
            ],
        ), patch(
            "cogs.watch_together.watch_server.close_watch_session",
            new_callable=AsyncMock,
        ) as close_session:
            await cog.on_ready()
            await cog.on_ready()

        close_session.assert_awaited_once_with(
            stale_id,
            reason="봇 재시작 후 접속자 없음",
        )
    finally:
        manager.active_connections.pop(active_id, None)


@pytest.mark.asyncio
async def test_watch_creation_sends_private_admin_control():
    from cogs.watch_together.watch_server import manager

    bot = MagicMock()
    log_cog = MagicMock()
    log_cog.send_watch_session_control = AsyncMock()
    bot.get_cog.return_value = log_cog
    cog = WatchAgentCog(bot)

    interaction = MagicMock()
    interaction.guild_id = 101
    interaction.user.id = 202
    interaction.user.mention = "<@202>"
    interaction.response.send_message = AsyncMock()
    original_message = MagicMock()
    original_message.id = 303
    original_message.channel.id = 404
    interaction.original_response = AsyncMock(
        return_value=original_message,
    )

    with patch.object(manager, "schedule_self_destruct") as schedule:
        try:
            await cog.handle_watch_together(interaction)

            log_cog.send_watch_session_control.assert_awaited_once()
            request = log_cog.send_watch_session_control.call_args.kwargs
            assert request["guild_id"] == 101
            assert request["created_by"] == 202
            assert request["channel_id"] == 404
            schedule.assert_called_once_with(request["session_id"])
        finally:
            if log_cog.send_watch_session_control.await_count:
                session_id = (
                    log_cog.send_watch_session_control.call_args.kwargs[
                        "session_id"
                    ]
                )
                await database_manager.delete_watch_session(session_id)


@pytest.mark.asyncio
async def test_watch_playlist_rejects_non_youtube_urls():
    session_id = str(uuid.uuid4())
    await database_manager.add_watch_session(session_id, 888, 999)

    try:
        response = client.post(
            f"/api/playlist/{session_id}/add",
            json={
                "video_url": "https://example.com/not-youtube",
                "added_by": "테스터",
            },
        )

        assert response.status_code == 400
        assert await database_manager.get_watch_playlist(session_id) == []
    finally:
        await database_manager.delete_watch_session(session_id)


def test_watch_player_renders_playlist_without_dynamic_inner_html():
    from pathlib import Path

    player_path = (
        Path(__file__).resolve().parents[1]
        / "cogs"
        / "watch_together"
        / "templates"
        / "player.html"
    )
    player_html = player_path.read_text(encoding="utf-8")
    render_section = player_html.split(
        "function renderPlaylist()",
        1,
    )[1].split("function playPlaylistVideo", 1)[0]

    assert ".innerHTML" not in render_section
    assert "onclick=" not in render_section
    assert "textContent = item.video_title" in render_section
    assert "addEventListener" in render_section
    assert 'itemInfo.setAttribute("role", "button")' in render_section
    assert 'itemInfo.addEventListener("keydown"' in render_section


def test_watch_player_renders_chat_and_users_without_dynamic_html():
    from pathlib import Path

    player_path = (
        Path(__file__).resolve().parents[1]
        / "cogs"
        / "watch_together"
        / "templates"
        / "player.html"
    )
    player_html = player_path.read_text(encoding="utf-8")
    chat_section = player_html.split(
        "function appendChatMessage",
        1,
    )[1].split("function appendSystemMessage", 1)[0]
    users_section = player_html.split(
        "function updateUsersList",
        1,
    )[1].split("// 7.", 1)[0]

    assert ".innerHTML" not in chat_section
    assert "textContent = text" in chat_section
    assert "replaceChildren()" in users_section
    assert "textContent = user" in users_section


def test_watch_player_maps_real_session_events_to_visible_state():
    from pathlib import Path

    player_path = (
        Path(__file__).resolve().parents[1]
        / "cogs"
        / "watch_together"
        / "templates"
        / "player.html"
    )
    player_html = player_path.read_text(encoding="utf-8")

    assert "function setConnectionState" in player_html
    assert "function setPlaybackState" in player_html
    assert "function setSyncState" in player_html
    assert 'case "state_change":' in player_html
    assert 'case "seek":' in player_html
    assert 'case "sync_request":' in player_html
    assert 'case "sync_response":' in player_html
    assert 'setConnectionState("reconnecting", "재연결 중")' in player_html
    assert 'setSyncState("offline", "연결 끊김")' in player_html
    assert "updateParticipantCount(users.length)" in player_html
    assert "updateQueueCount(playlist.length)" in player_html


def test_watch_player_operation_tabs_are_keyboard_accessible():
    from pathlib import Path

    player_path = (
        Path(__file__).resolve().parents[1]
        / "cogs"
        / "watch_together"
        / "templates"
        / "player.html"
    )
    player_html = player_path.read_text(encoding="utf-8")

    assert 'role="tablist"' in player_html
    assert player_html.count('role="tab"') == 2
    assert player_html.count('role="tabpanel"') == 2
    assert 'event.key !== "ArrowLeft"' in player_html
    assert 'event.key !== "ArrowRight"' in player_html
    assert 'tab.setAttribute("aria-selected", String(isActive))' in player_html
