"""Discord-side bounded HTTP client. No web runtime, DB or session state imports."""

import asyncio
import json
import uuid
from typing import Any

from discordbot.platform.clock import Clock
from discordbot.platform.errors import (AuthorizationError, CapacityError, ConflictError,
    DeadlineExceededError, ExternalTemporaryError, ValidationError, DatabaseUnavailableError, ShutdownError)
from discordbot.watch.adapters.control_schema import response_data
from discordbot.watch.adapters.security import LoopbackAuth, loopback_url
from discordbot.watch.adapters.wire import decode


class LoopbackClient:
    def __init__(self, url: str, secret: str, clock: Clock, session: Any = None) -> None:
        self.url, self.auth, self.clock = loopback_url(url), LoopbackAuth(secret), clock
        self.session, self.owned = session, session is None
        self.active = 0

    async def start(self) -> None:
        if self.session is None:
            import aiohttp
            self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=8),
                timeout=aiohttp.ClientTimeout(total=5), trust_env=False)

    async def call(self, operation: str, data: dict[str, object]) -> dict[str, object]:
        if operation not in {"create", "abort", "close", "bind", "status", "cleanup", "ack"}:
            raise ValidationError("unknown Watch control operation")
        if self.active >= 8:
            raise CapacityError("Watch control client full")
        correlation = uuid.uuid4().hex
        try:
            raw = json.dumps({"correlation": correlation, "data": data}, separators=(",", ":"), allow_nan=False).encode()
        except (ValueError, TypeError):
            raise ValidationError("invalid Watch control request") from None
        if len(raw) > 8192:
            raise ValidationError("Watch control body limit")
        path, stamp, nonce = f"/internal/watch/{operation}", str(int(self.clock.now().timestamp())), uuid.uuid4().hex
        headers = {"Content-Type": "application/json", "X-Watch-Time": stamp, "X-Watch-Nonce": nonce,
            "X-Watch-Signature": self.auth.signature(path, raw, stamp, nonce)}
        self.active += 1
        try:
            async with asyncio.timeout(5):
                async with self.session.post(self.url+path, data=raw, headers=headers, allow_redirects=False) as response:
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        if len(body)+len(chunk) > 65536:
                            raise ExternalTemporaryError("Watch control response limit")
                        body.extend(chunk)
                    try:
                        value = decode(bytes(body))
                    except ValidationError:
                        raise ExternalTemporaryError("Watch control malformed response") from None
                    if response.status != 200:
                        code = value.get("code")
                        fallback = {400: ValidationError, 403: AuthorizationError, 404: ConflictError,
                            408: DeadlineExceededError, 413: ValidationError, 429: CapacityError}.get(response.status, ExternalTemporaryError)
                        error = {"validation": ValidationError, "authorization": AuthorizationError, "conflict": ConflictError,
                            "capacity": CapacityError, "database_unavailable": DatabaseUnavailableError,
                            "deadline_exceeded": DeadlineExceededError, "shutdown": ShutdownError}.get(code, fallback)
                        raise error("Watch control rejected")
                    if set(value) != {"correlation", "data"} or value["correlation"] != correlation or not isinstance(value["data"], dict):
                        raise ExternalTemporaryError("Watch control invalid response")
                    return response_data(operation, value["data"])
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise DeadlineExceededError("Watch loopback deadline") from None
        except (AuthorizationError, CapacityError, ConflictError, ValidationError, ExternalTemporaryError, DatabaseUnavailableError, DeadlineExceededError, ShutdownError):
            raise
        except Exception:
            raise ExternalTemporaryError("Watch loopback unavailable") from None
        finally:
            self.active -= 1

    async def stop(self) -> None:
        if self.session is not None and self.owned:
            await self.session.close()
        self.session = None
