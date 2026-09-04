import datetime as stdlib_datetime
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord
import pytest
from fastapi import WebSocketDisconnect

from cogs.application_commands import CommandsCog
from cogs.watch_together import watch_server
from cogs.watch_together.watch_agent import WatchAgentCog
from cogs.watch_together.watch_server import (
    ConnectionManager,
    VideoAddRequest,
    app,
    websocket_endpoint,
)


class _FakeWebSocket:
    def __init__(self, messages: list[dict]) -> None:
        self.accept = AsyncMock()
        self.close = AsyncMock()
        self.send_json = AsyncMock()
        self._messages = iter(messages)

    async def receive_text(self) -> str:
        try:
            return json.dumps(next(self._messages))
        except StopIteration as error:
            raise WebSocketDisconnect() from error


class _FixedUtcClock(stdlib_datetime.datetime):
    @classmethod
    def now(cls, tz: stdlib_datetime.tzinfo | None = None) -> "_FixedUtcClock":
        return cls(2026, 9, 4, 0, 0, 0, tzinfo=tz)


def test_f038_f040_fr039_preserve_watch_http_paths_and_payload() -> None:
    """Features F038/F040; FR-039; PRESERVE."""
    routes = {(route.path, tuple(sorted(getattr(route, "methods", ())))) for route in app.routes}
    assert ("/watch", ("GET",)) in routes
    assert ("/api/playlist/{session_id}", ("GET",)) in routes
    assert ("/api/playlist/{session_id}/add", ("POST",)) in routes
    assert ("/api/playlist/{session_id}/remove", ("POST",)) in routes
    assert any(route.path == "/ws/{session_id}" for route in app.routes)
    assert tuple(VideoAddRequest.model_fields) == ("video_url", "added_by")


@pytest.mark.asyncio
async def test_f037_fr003_fr010_fr038_preserve_watch_command_publicness_and_unready_error() -> None:
    """Feature F037; FR-003/FR-010/FR-038; PRESERVE."""
    bot = MagicMock()
    bot.get_cog.return_value = None
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response.send_message = AsyncMock()
    await CommandsCog.watch_command.callback(CommandsCog(bot), interaction)
    interaction.response.send_message.assert_awaited_once_with(
        "시청 기능이 아직 준비되지 않았습니다.",
        ephemeral=True,
    )

    bot = MagicMock()
    bot.get_cog.return_value = None
    cog = WatchAgentCog(bot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user.id = 456
    interaction.user.mention = "<@456>"
    interaction.response.send_message = AsyncMock()
    interaction.original_response = AsyncMock(
        return_value=SimpleNamespace(id=789, channel=SimpleNamespace(id=987))
    )
    with patch(
        "cogs.watch_together.watch_agent.add_watch_session",
        new=AsyncMock(),
    ), patch.object(watch_server.manager, "schedule_self_destruct"):
        await cog.handle_watch_together(interaction)
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is False


@pytest.mark.asyncio
async def test_f039_fr040_fr041_preserve_websocket_join_protocol() -> None:
    """Feature F039; FR-040/FR-041; PRESERVE."""
    session_id = "join-session"
    websocket = _FakeWebSocket([{"type": "join", "username": "  친구  "}])
    manager = watch_server.manager
    manager.active_connections.pop(session_id, None)
    manager.user_names.pop(session_id, None)

    with patch(
        "cogs.watch_together.watch_server.get_watch_session",
        new=AsyncMock(return_value={"session_id": session_id}),
    ), patch.object(manager, "broadcast", new=AsyncMock()) as broadcast, patch.object(
        manager,
        "schedule_self_destruct",
    ):
        await websocket_endpoint(websocket, session_id)  # type: ignore[arg-type]

    websocket.accept.assert_awaited_once()
    message_types = [item.args[1]["type"] for item in broadcast.await_args_list]
    assert message_types == [
        "user_joined",
        "user_list",
        "sync_request",
        "user_left",
        "user_list",
    ]
    joined = broadcast.await_args_list[0].args[1]
    assert joined["username"] == "친구"
    assert joined["message"] == "👉 친구님이 시청방에 입장하셨습니다."


@pytest.mark.parametrize(
    "message",
    [
        {"type": "chat", "username": "친구", "text": "안녕"},
        {"type": "state_change", "playing": True, "time": 12.5},
        {"type": "seek", "time": 30.0},
        {"type": "sync_request"},
        {"type": "sync_response", "playing": False, "time": 8.0},
        {"type": "playlist_change", "message": "changed"},
    ],
    ids=["chat", "state_change", "seek", "sync_request", "sync_response", "playlist_change"],
)
@pytest.mark.asyncio
async def test_f039_fr040_preserve_websocket_relay_types(message: dict) -> None:
    """Feature F039; FR-040; PRESERVE remaining six client message types."""
    session_id = f"relay-{message['type']}"
    websocket = _FakeWebSocket([message])
    manager = watch_server.manager
    manager.active_connections.pop(session_id, None)
    manager.user_names.pop(session_id, None)

    with patch(
        "cogs.watch_together.watch_server.get_watch_session",
        new=AsyncMock(return_value={"session_id": session_id}),
    ), patch.object(manager, "broadcast", new=AsyncMock()) as broadcast, patch.object(
        manager,
        "schedule_self_destruct",
    ):
        await websocket_endpoint(websocket, session_id)  # type: ignore[arg-type]

    relayed = [
        item.args[1]
        for item in broadcast.await_args_list
        if item.args[1].get("type") == message["type"]
    ]
    assert relayed == [message]
    assert broadcast.await_args_list[0].kwargs["exclude"] is websocket


@pytest.mark.asyncio
async def test_f039_fr040_preserve_invalid_websocket_session_close_code() -> None:
    """Feature F039; FR-040; PRESERVE failure contract."""
    websocket = _FakeWebSocket([])
    with patch(
        "cogs.watch_together.watch_server.get_watch_session",
        new=AsyncMock(return_value=None),
    ):
        await websocket_endpoint(websocket, "missing")  # type: ignore[arg-type]

    websocket.close.assert_awaited_once_with(code=4003)
    websocket.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_f041_fr042_preserve_thirty_and_five_second_lifecycle_fake_clock() -> None:
    """Feature F041; FR-042; PRESERVE fake-clock contract."""
    session_id = "grace-session"
    fake_datetime_module = SimpleNamespace(
        datetime=_FixedUtcClock,
        date=stdlib_datetime.date,
        time=stdlib_datetime.time,
        timedelta=stdlib_datetime.timedelta,
        timezone=stdlib_datetime.timezone,
    )
    sleep = AsyncMock()
    watch_server.manager.active_connections.pop(session_id, None)
    with patch(
        "cogs.watch_together.watch_server.get_watch_session",
        new=AsyncMock(
            return_value={"created_at": "2026-09-04 00:00:00"}
        ),
    ), patch.dict(sys.modules, {"datetime": fake_datetime_module}), patch.object(
        watch_server.asyncio,
        "sleep",
        new=sleep,
    ), patch(
        "cogs.watch_together.watch_server.close_watch_session",
        new=AsyncMock(return_value=True),
    ) as close_session:
        await watch_server.self_destruct_session(session_id)

    assert sleep.await_args_list == [call(30.0), call(5.0)]
    close_session.assert_awaited_once_with(
        session_id,
        reason="접속자 없음 자동 종료",
    )
    assert watch_server.SELF_DESTRUCT_DELAY == 5.0


def test_f041_fr042_preserve_last_disconnect_schedules_five_second_grace() -> None:
    """Feature F041; FR-042; PRESERVE."""
    manager = ConnectionManager()
    websocket = MagicMock()
    manager.active_connections["session"] = [websocket]
    manager.user_names["session"] = {websocket: "친구"}
    manager.schedule_self_destruct = MagicMock()  # type: ignore[method-assign]

    manager.disconnect("session", websocket)

    manager.schedule_self_destruct.assert_called_once_with("session")
    assert "session" not in manager.active_connections


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 sends the invite before durable session creation",
)
@pytest.mark.asyncio
async def test_f037_fr004_fr038_correct_watch_commits_before_invite() -> None:
    """Feature F037; FR-004/FR-038; CORRECT."""
    events: list[str] = []
    bot = MagicMock()
    bot.get_cog.return_value = None
    cog = WatchAgentCog(bot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user.id = 456
    interaction.user.mention = "<@456>"
    interaction.response.send_message = AsyncMock(
        side_effect=lambda **_kwargs: events.append("invite")
    )
    interaction.original_response = AsyncMock(
        return_value=SimpleNamespace(id=789, channel=SimpleNamespace(id=987))
    )

    async def durable(*_args: object, **_kwargs: object) -> None:
        events.append("durable")

    with patch(
        "cogs.watch_together.watch_agent.add_watch_session",
        new=durable,
    ), patch.object(watch_server.manager, "schedule_self_destruct"):
        await cog.handle_watch_together(interaction)

    assert events == ["durable", "invite"]


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: post-ACK persistence failure must use followup, not a second response",
)
@pytest.mark.asyncio
async def test_f037_fr004_fr010_correct_watch_failure_uses_single_responder() -> None:
    """Feature F037; FR-004/FR-010; CORRECT."""
    bot = MagicMock()
    bot.get_cog.return_value = None
    cog = WatchAgentCog(bot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user.id = 456
    interaction.user.mention = "<@456>"
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = True
    interaction.followup.send = AsyncMock()
    interaction.original_response = AsyncMock(
        return_value=SimpleNamespace(id=789, channel=SimpleNamespace(id=987))
    )
    with patch(
        "cogs.watch_together.watch_agent.add_watch_session",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        await cog.handle_watch_together(interaction)

    assert interaction.response.send_message.await_count == 1
    interaction.followup.send.assert_awaited_once_with(
        "❌ 시청 세션 방을 개설하는 동안 에러가 발생했습니다. 로그를 확인해 주세요.",
        ephemeral=True,
    )
