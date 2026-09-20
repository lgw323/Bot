"""Public HTTP/WS factory. Internal controls are never mounted in this app."""

import asyncio
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from discordbot.platform.errors import AppError, AuthorizationError, ConfigurationError, ValidationError
from discordbot.watch.adapters.wire import Ingress, decode, status
from discordbot.watch.adapters.security import public_origin
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import ClosedSession, InvalidCapability, Rate, video_id


def build_public_app(service: WatchService, origin: str):
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
    origin = public_origin(origin)
    template = Path(__file__).with_name("templates").joinpath("player.html").read_text(encoding="utf-8")
    client_revision = sha256(template.encode("utf-8")).hexdigest()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Ingress, maximum=service.limits.body_bytes, capacity=service.limits.requests)
    rate = Rate(80)

    @app.exception_handler(AppError)
    async def failure(request: Request, error: AppError):
        if request.url.path == "/watch" and isinstance(error, (InvalidCapability, ClosedSession)):
            return HTMLResponse("<h1>유효하지 않거나 만료된 세션입니다.</h1><p>디스코드 봇을 통해 새로운 방을 개설해 주세요.</p>",
                status_code=404, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"})
        return JSONResponse({"detail": error.safe_message, "code": error.code.value}, status_code=status(error),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    def admit(request: Request, mutation: bool = False):
        service.require()
        rate.take(service.clock.monotonic())
        if mutation and (request.headers.get("origin") != origin or request.headers.get("x-watch-csrf") != "1"):
            raise AuthorizationError("Watch origin or CSRF rejected")

    @app.get("/health/live")
    async def live():
        return {"live": service.health.snapshot().live}

    @app.get("/health/ready")
    async def ready():
        value = service.ready()
        return JSONResponse({"ready": value}, status_code=200 if value else 503)

    @app.get("/watch")
    async def page(request: Request, session: str = ""):
        admit(request)
        actor = service.resolve(session)
        await actor.call("playlist")  # expiry/readiness barrier before displaying the player
        nonce = secrets.token_urlsafe(24)
        csp = (f"default-src 'none'; script-src 'nonce-{nonce}' https://www.youtube.com https://s.ytimg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
            "img-src 'self' data: https://i.ytimg.com https://img.youtube.com; "
            "frame-src https://www.youtube.com; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        return HTMLResponse(template.replace("__WATCH_NONCE__", nonce), headers={"Content-Security-Policy": csp,
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "X-Watch-Client-Revision": client_revision})

    @app.get("/api/playlist/{session_id}")
    async def playlist(request: Request, session_id: str):
        admit(request)
        rows = await service.resolve(session_id).call("playlist")
        return JSONResponse({"playlist": [asdict(row) for row in rows]}, headers={"Cache-Control": "no-store"})

    @app.post("/api/playlist/{session_id}/add")
    async def add(request: Request, session_id: str):
        admit(request, True)
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise ValidationError("Watch JSON content type required")
        data = decode(await request.body())
        if set(data) != {"video_url", "added_by"}:
            raise ValidationError("invalid playlist add fields")
        title = await service.add(session_id, data["video_url"], data["added_by"])
        return {"status": "success", "title": title}

    @app.post("/api/playlist/{session_id}/remove")
    async def remove(request: Request, session_id: str, video_url: str = ""):
        admit(request, True)
        if await request.body() or set(request.query_params) != {"video_url"}:
            raise ValidationError("playlist remove requires query only")
        video_id(video_url)
        await service.resolve(session_id).call("remove", video_url)
        return {"status": "success"}

    @app.websocket("/ws/{session_id}")
    async def websocket(socket: WebSocket, session_id: str):
        actor = peer = None
        class Transport:
            async def send(self, message):
                await socket.send_json(message)
            async def close(self, code):
                await socket.close(code=code)
        try:
            if socket.headers.get("origin") != origin:
                raise InvalidCapability("Watch WebSocket origin rejected")
            service.resolve(session_id)
            await socket.accept()
            actor, peer = await service.connect(session_id, Transport())
            while not peer.failed:
                raw = await socket.receive()
                if raw["type"] == "websocket.disconnect":
                    break
                service.require()
                data = raw.get("text")
                if not isinstance(data, str) or len(data.encode("utf-8")) > service.limits.message_bytes:
                    raise ValidationError("Watch WebSocket frame limit")
                await actor.call("message", peer.id, decode(data.encode()))
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except AppError as error:
            code = 4003 if isinstance(error, (InvalidCapability, ClosedSession)) else 4008 if status(error) == 429 else 4002
            if peer:
                peer.stop(code)
            else:
                await socket.close(code=code)
        except Exception:
            if peer:
                peer.stop(4002)
            else:
                await socket.close(code=4002)
        finally:
            if actor and peer:
                try:
                    await actor.call("leave", peer.id)
                except AppError:
                    peer.stop(4001)
    return app
