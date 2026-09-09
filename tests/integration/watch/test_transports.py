import asyncio
import json
import uuid

import httpx
import pytest

from discordbot.watch.adapters.control_server import build_control_app
from discordbot.watch.adapters.security import LoopbackAuth
from discordbot.watch.adapters.web import build_public_app

SECRET = "synthetic-control-secret-32-characters"
ORIGIN = "https://watch.example.test"
pytestmark = pytest.mark.asyncio


def signed(clock, operation, data):
    path = f"/internal/watch/{operation}"
    raw = json.dumps({"correlation": uuid.uuid4().hex, "data": data}).encode()
    stamp, nonce = str(int(clock.now().timestamp())), uuid.uuid4().hex
    headers = {"x-watch-time": stamp, "x-watch-nonce": nonce,
        "x-watch-signature": LoopbackAuth(SECRET).signature(path, raw, stamp, nonce)}
    return path, raw, headers


async def test_internal_auth_replay_schema_and_public_separation(service, clock):
    app = build_control_app(service, SECRET)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        path, raw, headers = signed(clock, "create", {"guild": 100, "user": 42, "operation": "signed", "issued": int(service.now())})
        assert (await client.post(path, content=raw)).status_code == 403
        response = await client.post(path, content=raw, headers=headers)
        assert response.status_code == 200
        token = response.json()["data"]["capability"]
        assert service.resolve(token)
        assert (await client.post(path, content=raw, headers=headers)).status_code == 403
        path, raw, headers = signed(clock, "create", {"unexpected": True})
        assert (await client.post(path, content=raw, headers=headers)).status_code == 400
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_public_app(service, ORIGIN)), base_url=ORIGIN) as client:
        assert (await client.post("/internal/watch/create", content=raw, headers=headers)).status_code == 404


async def test_public_routes_security_playlist_and_terminal(service, invite):
    app = build_public_app(service, ORIGIN)
    base = f"/api/playlist/{invite.capability}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        page = await client.get("/watch", params={"session": invite.capability})
        assert page.status_code == 200
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert page.headers["referrer-policy"] == "no-referrer"
        assert "__WATCH_NONCE__" not in page.text
        assert "escapeHtml" in page.text and "X-Watch-CSRF" in page.text
        data = {"video_url": "https://youtu.be/aaaaaaaaaaa", "added_by": "<script>"}
        assert (await client.post(base+"/add", json=data)).status_code == 403
        client.headers.update({"origin": ORIGIN, "x-watch-csrf": "1"})
        assert (await client.post(base+"/add", json=data)).status_code == 200
        rows = (await client.get(base)).json()["playlist"]
        assert rows[0]["added_by"] == "<script>"
        assert (await client.post(base+"/add", json={**data, "video_url": "https://evil.test/"})).status_code == 400
        assert (await client.post(base+"/add", content=b"x"*8193)).status_code == 413
        assert (await client.post(base+"/add", content=b'{"video_url":1,"video_url":2}', headers={"content-type": "application/json"})).status_code == 400
        assert (await client.post(base+"/remove", params={"video_url": data["video_url"]})).status_code == 200
        assert (await client.get(base)).json() == {"playlist": []}
        await service.close(invite.session_id)
        assert (await client.get(base)).status_code == 404
        closed = await client.get("/watch", params={"session": invite.capability})
        assert closed.status_code == 404
        assert "디스코드 봇을 통해 새로운 방을 개설해 주세요." in closed.text


class WebSocket:
    def __init__(self, app, token, origin=ORIGIN):
        self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue()
        scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "wss", "path": f"/ws/{token}",
            "raw_path": f"/ws/{token}".encode(), "query_string": b"", "headers": [(b"origin", origin.encode())],
            "client": ("127.0.0.1", 1234), "server": ("watch.example.test", 443), "subprotocols": []}
        self.task = asyncio.create_task(app(scope, self.incoming.get, self.outgoing.put))

    async def next(self):
        return await asyncio.wait_for(self.outgoing.get(), 2)

    async def connect(self):
        await self.incoming.put({"type": "websocket.connect"})
        return await self.next()

    async def send(self, value):
        await self.incoming.put({"type": "websocket.receive", "text": json.dumps(value)})

    async def stop(self):
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, 2)


async def test_real_asgi_websocket_handshake_join_malformed_and_close(service, invite):
    app = build_public_app(service, ORIGIN)
    invalid = WebSocket(app, "invalid")
    assert (await invalid.connect())["code"] == 4003
    await invalid.stop()
    ws = WebSocket(app, invite.capability)
    try:
        assert (await ws.connect())["type"] == "websocket.accept"
        await ws.send({"type": "join", "username": "synthetic"})
        event = await ws.next()
        assert json.loads(event["text"])["users"] == ["synthetic"]
        await ws.send({"type": "unknown"})
        assert (await ws.next())["code"] == 4002
    finally:
        await ws.stop()


@pytest.mark.parametrize("payload", ["x"*4097, "{bad", '{"type":"chat","text":""}'])
async def test_websocket_size_json_schema_limits(service, invite, payload):
    ws = WebSocket(build_public_app(service, ORIGIN), invite.capability)
    try:
        await ws.connect()
        await ws.incoming.put({"type": "websocket.receive", "text": payload})
        assert (await ws.next())["code"] == 4002
    finally:
        await ws.stop()
