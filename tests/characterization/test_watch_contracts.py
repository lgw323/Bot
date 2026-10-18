from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_f037_fr004_fr038_correct_watch_commits_before_invite(tmp_path) -> None:
    """Feature F037; FR-004/FR-038; CORRECT through the actual V2 process contract."""
    from characterization.watch_support import harness, interaction
    from discordbot.watch.adapters.discord_io import DiscordInteraction

    async with harness(tmp_path) as h:
        events = []
        durable_create = h.writer.create

        async def durable(*args, **kwargs):
            result = await durable_create(*args, **kwargs)
            events.append("durable")
            return result

        h.writer.create = durable
        request = interaction(h.clock)
        message = SimpleNamespace(id=500, channel=SimpleNamespace(id=1000))
        async def invite(**kwargs):
            events.append("invite")
            return message
        request.edit_original_response.side_effect = invite
        await h.controller.request(DiscordInteraction(request, "https://watch.example.test"))
        assert events == ["durable", "invite"]
        assert len(h.service.sessions) == 1


@pytest.mark.asyncio
async def test_f037_fr004_fr010_correct_watch_failure_uses_single_responder(tmp_path) -> None:
    """Feature F037; FR-004/FR-010; CORRECT through the actual V2 process contract."""
    from characterization.watch_support import harness, interaction
    from discordbot.platform.errors import DatabaseUnavailableError
    from discordbot.watch.adapters.discord_io import DiscordInteraction, FAILURE

    async with harness(tmp_path) as h:
        request = interaction(h.clock)
        h.writer.create = AsyncMock(side_effect=DatabaseUnavailableError("synthetic failure"))
        await h.controller.request(DiscordInteraction(request, "https://watch.example.test"))
        request.response.defer.assert_awaited_once_with(thinking=True, ephemeral=False)
        request.response.send_message.assert_not_awaited()
        request.edit_original_response.assert_not_awaited()
        request.followup.send.assert_awaited_once_with(FAILURE, ephemeral=True)
