import asyncio
from unittest.mock import AsyncMock

import pytest

from characterization.watch_support import harness, interaction
from discordbot.platform.errors import AuthorizationError, DatabaseUnavailableError
from discordbot.watch.adapters.discord_io import DiscordInteraction, build_watch_cog, FAILURE

pytestmark = pytest.mark.asyncio


async def test_full_signed_loopback_command_signature_binding_and_master_cleanup(tmp_path):
    async with harness(tmp_path) as h:
        cog = build_watch_cog(h.bot, h.controller, "https://watch.example.test")
        command = cog.get_app_commands()[0]
        assert command.name == "시청" and not command.parameters
        raw = interaction(h.clock)
        await command.callback(cog, raw)
        raw.response.defer.assert_awaited_once_with(thinking=True, ephemeral=False)
        raw.response.send_message.assert_not_awaited()
        raw.edit_original_response.assert_awaited_once()
        kwargs = raw.edit_original_response.call_args.kwargs
        assert kwargs["embed"].title == "🎬 Watch Together 방이 개설되었습니다!"
        token = kwargs["view"].children[0].url.split("session=")[1]
        actor = h.service.resolve(token)
        assert actor.published
        with pytest.raises(AuthorizationError):
            await h.controller.master_close(43, actor.intent.session_id)
        assert not actor.closed
        await h.controller.master_close(42, actor.intent.session_id)
        await h.controller.master_close(42, actor.intent.session_id)
        assert not h.service.sessions and not h.messages.views
        assert h.channel.get_partial_message.return_value.delete.await_count == 2
        assert (await h.client.call("cleanup", {})) == {"items": []}


@pytest.mark.parametrize("stage", ["durable", "loopback", "admin", "invite", "bind", "cancel"])
async def test_failure_compensation_single_response_and_no_usable_link(tmp_path, stage):
    async with harness(tmp_path) as h:
        raw = interaction(h.clock)
        if stage == "durable":
            h.writer.create = AsyncMock(side_effect=DatabaseUnavailableError("secret=DO_NOT_EXPOSE"))
        elif stage == "loopback":
            original = h.client.call
            async def fail_create(operation, data):
                result = await original(operation, data)
                if operation == "create":
                    raise DatabaseUnavailableError("lost response after commit")
                return result
            h.client.call = fail_create
        elif stage == "admin":
            h.channel.send.side_effect = RuntimeError("secret=DO_NOT_EXPOSE")
        elif stage in {"invite", "cancel"}:
            raw.edit_original_response.side_effect = asyncio.CancelledError() if stage == "cancel" else RuntimeError("secret=DO_NOT_EXPOSE")
        elif stage == "bind":
            original = h.writer.bind
            async def fail_bind(epoch, sid, channel, message, admin, now):
                if not admin:
                    raise DatabaseUnavailableError("secret=DO_NOT_EXPOSE")
                await original(epoch, sid, channel, message, admin, now)
            h.writer.bind = fail_bind
        wrapped = DiscordInteraction(raw, "https://watch.example.test")
        if stage == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await h.controller.request(wrapped)
        else:
            await h.controller.request(wrapped)
            raw.followup.send.assert_awaited_once_with(FAILURE, ephemeral=True)
        assert not h.service.sessions
        raw.response.defer.assert_awaited_once()
        raw.response.send_message.assert_not_awaited()
        if stage in {"durable", "loopback", "admin"}:
            raw.edit_original_response.assert_not_awaited()
        assert "DO_NOT_EXPOSE" not in repr(h.buffer.drain())


async def test_duplicate_discord_delivery_and_single_admin_control(tmp_path):
    async with harness(tmp_path) as h:
        raw = interaction(h.clock)
        await asyncio.gather(*(h.controller.request(DiscordInteraction(raw, "https://watch.example.test")) for _ in range(4)))
        raw.edit_original_response.assert_awaited_once()
        h.channel.send.assert_awaited_once()
        assert len(h.service.sessions) == 1
