import json
import logging
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import aiohttp
import asyncio
import re
from urllib.parse import parse_qs, urlparse

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
YOUTUBE_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def extract_youtube_video_id(video_url: str) -> str | None:
    """Return a validated YouTube video id without changing the API contract."""
    try:
        parsed = urlparse(video_url.strip())
    except (TypeError, ValueError):
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None

    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [None])[0]
    else:
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {
            "embed",
            "live",
            "shorts",
        }:
            candidate = path_parts[1]

    if candidate and YOUTUBE_VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate
    return None


def sanitize_display_text(
    value: object,
    *,
    default: str,
    max_length: int,
) -> str:
    """Normalize browser-provided display text before broadcasting it."""
    if not isinstance(value, str):
        return default
    normalized = value.strip()
    if not normalized:
        return default
    return normalized[:max_length]

async def self_destruct_session(session_id: str, delay: float = SELF_DESTRUCT_DELAY, ignore_grace: bool = False):
    # 1. 30초 개설 유예 대기 검사 (최초 생성 직후 소멸 시점 방지)
    db_session = await get_watch_session(session_id)
    if db_session and not ignore_grace:
        from datetime import datetime, timezone
        try:
            # SQLite3는 CURRENT_TIMESTAMP 값을 기본 "YYYY-MM-DD HH:MM:SS" 형태로 저장함 (UTC 기준)
            created_at_dt = datetime.strptime(db_session["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            elapsed = (now_utc - created_at_dt).total_seconds()
            if elapsed < 30.0:
                remaining = 30.0 - elapsed
                logger.info(f"Session {session_id} is newly created. Waiting remaining {remaining:.1f}s before self-destruct check.")
                await asyncio.sleep(remaining)
        except Exception as e:
            logger.error(f"Error checking watch session elapsed time: {e}", exc_info=True)

    await asyncio.sleep(delay)
    if session_id not in manager.active_connections or not manager.active_connections[session_id]:
        logger.info(f"Self-destructing session {session_id} due to inactivity (0 users).")
        await close_watch_session(session_id, reason="접속자 없음 자동 종료")

app = FastAPI(title="Watch Together Sync Server")

# 정적 템플릿 경로 설정
TEMPLATE_DIR = Path(__file__).parent / "templates"

class ConnectionManager:
    def __init__(self):
        # 방(session_id)별 활성 웹소켓 목록 매핑
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # 방(session_id)별 (웹소켓 -> 닉네임) 매핑
        self.user_names: Dict[str, Dict[WebSocket, str]] = {}
        self.self_destruct_tasks: Dict[str, asyncio.Task[None]] = {}

    def schedule_self_destruct(
        self,
        session_id: str,
        *,
        delay: float = SELF_DESTRUCT_DELAY,
        ignore_grace: bool = False,
    ) -> asyncio.Task[None]:
        existing = self.self_destruct_tasks.get(session_id)
        if existing and not existing.done():
            return existing

        task = asyncio.create_task(
            self_destruct_session(
                session_id,
                delay=delay,
                ignore_grace=ignore_grace,
            )
        )
        self.self_destruct_tasks[session_id] = task

        def discard_finished(finished: asyncio.Task[None]) -> None:
            if self.self_destruct_tasks.get(session_id) is finished:
                self.self_destruct_tasks.pop(session_id, None)

        task.add_done_callback(discard_finished)
        return task

    def cancel_self_destruct(self, session_id: str) -> None:
        task = self.self_destruct_tasks.pop(session_id, None)
        if (
            task
            and not task.done()
            and task is not asyncio.current_task()
        ):
            task.cancel()

    async def connect(self, session_id: str, websocket: WebSocket):
        self.cancel_self_destruct(session_id)
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        
        if session_id not in self.user_names:
            self.user_names[session_id] = {}
            
        logger.info(f"WebSocket client connected to session: {session_id}. Active users: {len(self.active_connections[session_id])}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.user_names and websocket in self.user_names[session_id]:
            del self.user_names[session_id][websocket]
            if not self.user_names[session_id]:
                del self.user_names[session_id]

        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                # 마지막 유저가 퇴장했으므로 5초 유예 소멸 비동기 태스크 시작
                self.schedule_self_destruct(session_id)
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


async def _delete_invite_message(db_session: dict) -> None:
    """Delete the Discord invite message when its session is closed."""
    bot = getattr(app.state, "bot", None)
    channel_id = db_session.get("channel_id")
    message_id = db_session.get("message_id")
    if not bot or not channel_id or not message_id:
        return

    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.delete()
    except Exception as e:
        logger.warning(
            "Failed to delete Discord invite message for session %s: %s",
            db_session.get("session_id"),
            e,
        )


async def close_watch_session(
    session_id: str,
    *,
    reason: str,
) -> bool:
    """Close clients and remove all state for one session idempotently."""
    manager.cancel_self_destruct(session_id)
    db_session = await get_watch_session(session_id)
    if not db_session:
        manager.active_connections.pop(session_id, None)
        manager.user_names.pop(session_id, None)
        return False

    connections = list(manager.active_connections.pop(session_id, []))
    manager.user_names.pop(session_id, None)
    for websocket in connections:
        try:
            await websocket.close(code=4001, reason=reason)
        except Exception as e:
            logger.warning(
                "Failed to close a Watch Together websocket for %s: %s",
                session_id,
                e,
            )

    await _delete_invite_message(db_session)
    await delete_watch_session(session_id)
    logger.info("Watch Together session closed: %s (%s)", session_id, reason)
    return True


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
    username = "알 수 없는 유저"

    try:
        while True:
            # 실시간 클라이언트 메시지 대기
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "join":
                username = sanitize_display_text(
                    message.get("username"),
                    default="임시유저",
                    max_length=50,
                )
                if session_id in manager.user_names:
                    manager.user_names[session_id][websocket] = username
                
                # 누군가 새로 들어왔을 때, 방의 다른 참여자들에게 알림 전송 및 접속자 명단 브로드캐스트
                await manager.broadcast(
                    session_id, 
                    {
                        "type": "user_joined", 
                        "username": username,
                        "message": f"👉 {username}님이 시청방에 입장하셨습니다."
                    },
                    exclude=websocket
                )
                
                # 접속자 명단 전체에 전송
                users_list = list(manager.user_names.get(session_id, {}).values())
                await manager.broadcast(
                    session_id,
                    {
                        "type": "user_list",
                        "users": users_list
                    }
                )
                
                # 방 안의 다른 클라이언트들에게 재생 상태 공유를 구걸함
                await manager.broadcast(
                    session_id,
                    {"type": "sync_request"},
                    exclude=websocket
                )
            
            # 메시지 타입에 따른 중계 처리
            elif msg_type == "chat":
                chat_text = sanitize_display_text(
                    message.get("text"),
                    default="",
                    max_length=500,
                )
                if not chat_text:
                    continue
                safe_message = dict(message)
                safe_message["username"] = sanitize_display_text(
                    message.get("username"),
                    default=username,
                    max_length=50,
                )
                safe_message["text"] = chat_text
                await manager.broadcast(
                    session_id,
                    safe_message,
                    exclude=websocket,
                )
            elif msg_type in ["state_change", "seek", "sync_response", "playlist_change"]:
                # 보낸 클라이언트를 제외하고 세션 내 모든 참가자에게 브로드캐스트
                await manager.broadcast(session_id, message, exclude=websocket)
            elif msg_type == "sync_request":
                # 방 안의 다른 클라이언트들에게 상태 정보를 구걸함
                await manager.broadcast(session_id, message, exclude=websocket)
                
    except WebSocketDisconnect:
        # 퇴장 시 닉네임을 구하고 세션에서 해제
        manager.disconnect(session_id, websocket)
        await manager.broadcast(
            session_id, 
            {
                "type": "user_left", 
                "username": username,
                "message": f"👈 {username}님이 시청방에서 퇴장하셨습니다."
            }, 
            exclude=websocket
        )
        # 퇴장 후 갱신된 접속자 명단 전체 전송
        users_list = list(manager.user_names.get(session_id, {}).values())
        await manager.broadcast(
            session_id,
            {
                "type": "user_list",
                "users": users_list
            }
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
    if not extract_youtube_video_id(video_url):
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube video URL",
        )

    added_by = sanitize_display_text(
        request.added_by,
        default="임시유저",
        max_length=50,
    )
    video_title = "알 수 없는 유튜브 비디오"
    
    # 유튜브 URL 파싱 테스트 및 oembed 조회
    if "youtube.com" in video_url or "youtu.be" in video_url:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=5.0) as resp:
                    if resp.status == 200:
                        meta = await resp.json()
                        video_title = sanitize_display_text(
                            meta.get("title"),
                            default=video_title,
                            max_length=200,
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch YouTube oembed title: {e}")
            
    # DB에 플레이리스트 추가
    await add_to_watch_playlist(session_id, video_url, video_title, added_by)
    
    # 플레이리스트 갱신 알림을 방 전체에 브로드캐스트
    await manager.broadcast(
        session_id,
        {"type": "playlist_change", "message": f"{added_by}님이 새 비디오를 추가했습니다."}
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
