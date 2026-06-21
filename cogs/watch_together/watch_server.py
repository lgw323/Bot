import json
import logging
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import aiohttp
import asyncio

# 데이터베이스 매니저 모듈 임포트
from database_manager import (
    get_watch_session,
    get_watch_playlist,
    add_to_watch_playlist,
    remove_from_watch_playlist,
    delete_watch_session
)

logger = logging.getLogger("WatchServer")

SELF_DESTRUCT_DELAY = 5.0

async def self_destruct_session(session_id: str, delay: float = SELF_DESTRUCT_DELAY):
    await asyncio.sleep(delay)
    if session_id not in manager.active_connections or not manager.active_connections[session_id]:
        logger.info(f"Self-destructing session {session_id} due to inactivity (0 users).")
        try:
            await delete_watch_session(session_id)
        except Exception as e:
            logger.error(f"Failed to delete watch session {session_id} on self-destruct: {e}", exc_info=True)

app = FastAPI(title="Watch Together Sync Server")

# 정적 템플릿 경로 설정
TEMPLATE_DIR = Path(__file__).parent / "templates"

class ConnectionManager:
    def __init__(self):
        # 방(session_id)별 활성 웹소켓 목록 매핑
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket client connected to session: {session_id}. Active users: {len(self.active_connections[session_id])}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                # 마지막 유저가 퇴장했으므로 5초 유예 소멸 비동기 태스크 시작
                asyncio.create_task(self_destruct_session(session_id))
            logger.info(f"WebSocket client disconnected from session: {session_id}")

    async def broadcast(self, session_id: str, message: dict, exclude: WebSocket = None):
        if session_id in self.active_connections:
            # 브로드캐스트 대상을 순회하며 패킷 송신
            for connection in self.active_connections[session_id]:
                if connection != exclude:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting to client: {e}")


manager = ConnectionManager()

# 1. 시청 페이지 서빙
@app.get("/watch", response_class=HTMLResponse)
async def get_watch_page(session: str):
    # 세션 유효성 검사
    db_session = await get_watch_session(session)
    if not db_session:
        return HTMLResponse(
            content="<h1>유효하지 않거나 만료된 세션입니다.</h1><p>디스코드 봇을 통해 새로운 방을 개설해 주세요.</p>",
            status_code=404
        )
    
    player_html_path = TEMPLATE_DIR / "player.html"
    if not player_html_path.exists():
        raise HTTPException(status_code=500, detail="Player template not found.")
    
    with open(player_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content, status_code=200)


# 2. WebSocket 동기화 채널 엔드포인트
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # 디바이스 세션 유효성 1차 검증
    db_session = await get_watch_session(session_id)
    if not db_session:
        await websocket.close(code=4003)
        return

    await manager.connect(session_id, websocket)
    
    # 누군가 새로 들어왔을 때, 방의 다른 참여자들에게 현재 재생 정보를 알려달라고 요청하는 브로드캐스트 전송
    await manager.broadcast(
        session_id, 
        {"type": "user_joined", "message": "새로운 참가자가 연결되었습니다."}, 
        exclude=websocket
    )

    try:
        while True:
            # 실시간 클라이언트 메시지 대기
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            # 메시지 타입에 따른 중계 처리
            if msg_type in ["state_change", "seek", "sync_response", "chat", "playlist_change"]:
                # 보낸 클라이언트를 제외하고 세션 내 모든 참가자에게 브로드캐스트
                await manager.broadcast(session_id, message, exclude=websocket)
            elif msg_type == "sync_request":
                # 방 안의 다른 클라이언트들에게 상태 정보를 구걸함
                await manager.broadcast(session_id, message, exclude=websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
        await manager.broadcast(
            session_id, 
            {"type": "user_left", "message": "참가자가 퇴장했습니다."}, 
            exclude=websocket
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(session_id, websocket)


# API용 스키마 정의
class VideoAddRequest(BaseModel):
    video_url: str
    added_by: str

# 3. 플레이리스트 관련 API
@app.get("/api/playlist/{session_id}")
async def api_get_playlist(session_id: str):
    db_session = await get_watch_session(session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    playlist = await get_watch_playlist(session_id)
    return JSONResponse(content={"playlist": playlist})


@app.post("/api/playlist/{session_id}/add")
async def api_add_playlist(session_id: str, request: VideoAddRequest):
    db_session = await get_watch_session(session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 3-1. 유튜브 메타데이터 및 OEmbed 활용 제목 간편 조회
    video_url = request.video_url.strip()
    video_title = "알 수 없는 유튜브 비디오"
    
    # 유튜브 URL 파싱 테스트 및 oembed 조회
    if "youtube.com" in video_url or "youtu.be" in video_url:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=5.0) as resp:
                    if resp.status == 200:
                        meta = await resp.json()
                        video_title = meta.get("title", video_title)
        except Exception as e:
            logger.warning(f"Failed to fetch YouTube oembed title: {e}")
            
    # DB에 플레이리스트 추가
    await add_to_watch_playlist(session_id, video_url, video_title, request.added_by)
    
    # 플레이리스트 갱신 알림을 방 전체에 브로드캐스트
    await manager.broadcast(
        session_id,
        {"type": "playlist_change", "message": f"{request.added_by}님이 새 비디오를 추가했습니다."}
    )
    
    return JSONResponse(content={"status": "success", "title": video_title})


@app.post("/api/playlist/{session_id}/remove")
async def api_remove_playlist(session_id: str, video_url: str):
    db_session = await get_watch_session(session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await remove_from_watch_playlist(session_id, video_url)
    
    # 플레이리스트 갱신 알림 브로드캐스트
    await manager.broadcast(
        session_id,
        {"type": "playlist_change", "message": "비디오가 대기열에서 제거되었습니다."}
    )
    
    return JSONResponse(content={"status": "success"})
