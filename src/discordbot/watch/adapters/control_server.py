"""Authenticated loopback-only ASGI app, separate from the public route table."""

from dataclasses import asdict
import re

from discordbot.platform.context import CorrelationContext, correlation_scope
from discordbot.platform.errors import AppError, ValidationError
from discordbot.watch.adapters.security import LoopbackAuth
from discordbot.watch.adapters.wire import Ingress, decode, status
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import positive_id


def build_control_app(service: WatchService, secret: str):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Ingress, maximum=8192, capacity=8, deadline=5)
    auth = LoopbackAuth(secret)

    @app.exception_handler(AppError)
    async def failure(request: Request, error: AppError):
        return JSONResponse({"code": error.code.value, "detail": error.safe_message}, status_code=status(error))

    @app.post("/internal/watch/{operation}")
    async def control(operation: str, request: Request):
        raw = await request.body()
        auth.verify(request.client.host if request.client else "", request.url.path, raw,
            request.headers.get("x-watch-time", ""), request.headers.get("x-watch-nonce", ""),
            request.headers.get("x-watch-signature", ""), service.now())
        envelope = decode(raw)
        if set(envelope) != {"correlation", "data"} or not isinstance(envelope["correlation"], str) or not re.fullmatch(r"[a-f0-9]{32}", envelope["correlation"]):
            raise ValidationError("invalid Watch correlation envelope")
        data = envelope["data"]
        shapes = {"create": {"guild", "user", "operation", "issued"}, "abort": {"guild", "user", "operation", "issued"}, "close": {"session_id"},
            "bind": {"session_id", "channel", "message", "admin"}, "status": set(), "cleanup": set(), "ack": {"session_id"}}
        if operation not in shapes or not isinstance(data, dict) or set(data) != shapes[operation]:
            raise ValidationError("invalid Watch control schema")
        if "session_id" in data and (not isinstance(data["session_id"], str) or not re.fullmatch(r"[a-f0-9]{64}", data["session_id"])):
            raise ValidationError("invalid internal Watch identity")
        with correlation_scope(CorrelationContext(envelope["correlation"])):
            result = {}
            if operation == "status":
                result = {"ready": service.ready()}
            else:
                service.require()
                if operation == "create":
                    result = asdict(await service.create(**data))
                elif operation == "abort":
                    await service.abort(**data)
                elif operation == "close":
                    await service.close(data["session_id"])
                elif operation == "bind":
                    positive_id(data["channel"])
                    positive_id(data["message"])
                    if type(data["admin"]) is not bool:
                        raise ValidationError("invalid Watch binding role")
                    actor = service.sessions.get(data["session_id"])
                    if actor is None:
                        from discordbot.watch.domain.policy import ClosedSession
                        raise ClosedSession("Watch binding session closed")
                    await actor.call("bind", data["channel"], data["message"], data["admin"])
                elif operation == "cleanup":
                    result = {"items": [asdict(item) for item in await service.writer.cleanup(service.epoch, service.now())]}
                elif operation == "ack":
                    await service.writer.acknowledge(service.epoch, data["session_id"], service.now())
            return {"correlation": envelope["correlation"], "data": result}
    return app
