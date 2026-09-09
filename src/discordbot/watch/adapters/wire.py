"""Bounded JSON and ASGI ingress shared only by Watch transport adapters."""

import asyncio
import json
from typing import Any

from discordbot.platform.errors import AppError, AuthorizationError, CapacityError, ValidationError
from discordbot.watch.domain.policy import ClosedSession, InvalidCapability


def decode(raw: bytes) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ValidationError("invalid Watch JSON") from None


def status(error: AppError) -> int:
    if isinstance(error, (InvalidCapability, ClosedSession)):
        return 404
    if isinstance(error, AuthorizationError):
        return 403
    if isinstance(error, CapacityError):
        return 429
    if isinstance(error, ValidationError):
        return 400
    return 503


class Ingress:
    """Read at most one bounded body; never accumulate unbounded chunked input."""
    def __init__(self, app, maximum: int = 8192, capacity: int = 32, deadline: float = 10):
        self.app, self.maximum, self.capacity = app, maximum, capacity
        self.deadline = deadline
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        oversized = (len(scope.get("raw_path", b"")) + len(scope.get("query_string", b"")) > 4096
            or sum(len(k)+len(v) for k, v in scope.get("headers", ())) > 16384)
        if scope["type"] == "websocket":
            if oversized:
                return await send({"type": "websocket.close", "code": 4002})
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        if oversized or self.active >= self.capacity:
            return await JSONResponse({"detail": "Request limit"}, status_code=413 if oversized else 429)(scope, receive, send)
        self.active += 1
        try:
            body = bytearray()
            try:
                async with asyncio.timeout(5):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body)+len(chunk) > self.maximum:
                            return await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, send)
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await JSONResponse({"detail": "Request deadline"}, status_code=408)(scope, receive, send)
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()
            started = False
            async def safe_send(message):
                nonlocal started
                if message["type"] == "http.response.start":
                    started = True
                await send(message)
            try:
                async with asyncio.timeout(self.deadline):
                    await self.app(scope, bounded_receive, safe_send)
            except Exception:
                # An unexpected adapter exception must not reach an access/error
                # logger carrying the capability path or provider exception text.
                if not started:
                    await JSONResponse({"detail": "Watch request unavailable"}, status_code=503)(scope, receive, send)
        finally:
            self.active -= 1
