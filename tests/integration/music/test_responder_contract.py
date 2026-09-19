"""Pinned SDK signatures and response ownership, without Discord HTTP."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest

from discordbot.music.adapters.discord_ui import Responder
from .test_discord import controller, interaction

pytestmark = pytest.mark.asyncio


def sdk_followup(request):
    request.followup = create_autospec(discord.Webhook, instance=True)
    message = SimpleNamespace(delete=AsyncMock())
    request.followup.send.return_value = message
    return message


async def test_url_request_uses_real_webhook_signature_and_owns_deletion(rig):
    control, _ = controller(rig)
    request = interaction()
    message = sdk_followup(request)
    try:
        await control.request(request, 'https://youtube.com/watch?v=synthetic')
        request.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        request.followup.send.assert_awaited_once()
        kwargs = request.followup.send.call_args.kwargs
        assert kwargs['wait'] is True and kwargs['ephemeral'] is True
        assert 'delete_after' not in kwargs
        assert len(control._delete_tasks) == 1
        message.delete.assert_not_awaited()
    finally:
        control.close()
        await control._deletions.shutdown(grace_seconds=0)
    assert not control._deletions.snapshot().active


async def test_followup_deletion_runs_under_owner_without_sdk_background_delay(rig):
    control, _ = controller(rig)
    request = interaction()
    message = sdk_followup(request)
    responder = control.responder(request)
    await responder.defer()
    try:
        await responder.send('synthetic', ephemeral=True, delete_after=0)
        await asyncio.gather(*control._delete_tasks)
        message.delete.assert_awaited_once_with()
        await responder.send('duplicate', ephemeral=True)
        assert request.followup.send.await_count == 1
    finally: control.close()


async def test_pre_dispatch_signature_error_allows_exactly_one_fallback():
    request = interaction()
    sdk_followup(request)
    responder = Responder(request)
    await responder.defer()
    with pytest.raises(TypeError):
        await responder.send('synthetic', unsupported_argument=True)
    assert not responder.finished
    request.followup.send.assert_not_called()
    await responder.send('safe fallback', ephemeral=True)
    await responder.send('duplicate', ephemeral=True)
    request.followup.send.assert_awaited_once_with(content='safe fallback', ephemeral=True)


@pytest.mark.parametrize('error', [TypeError('private synthetic payload'), TimeoutError(), RuntimeError()])
async def test_failure_after_dispatch_never_attempts_ambiguous_second_send(error):
    request = interaction()
    sdk_followup(request)
    request.followup.send.side_effect = error
    responder = Responder(request)
    await responder.defer()
    with pytest.raises(type(error)): await responder.send('synthetic', ephemeral=True)
    await responder.send('fallback', ephemeral=True)
    assert request.followup.send.await_count == 1


async def test_initial_response_preserves_sdk_delete_after():
    request = interaction()
    request.response = create_autospec(discord.InteractionResponse, instance=True)
    request.response.is_done.return_value = False
    await Responder(request).send('synthetic', ephemeral=True, delete_after=5)
    request.response.send_message.assert_awaited_once_with(content='synthetic', ephemeral=True, delete_after=5)


async def test_cleanup_failure_cannot_replace_delivered_response(rig):
    control, _ = controller(rig)
    request = interaction()
    message = sdk_followup(request)
    message.delete.side_effect = RuntimeError('private synthetic payload')
    responder = control.responder(request)
    await responder.defer()
    try:
        await responder.send('synthetic', ephemeral=True, delete_after=0)
        await asyncio.gather(*control._delete_tasks)
        assert control.delete_failures == 1
        await responder.send('fallback', ephemeral=True)
        assert request.followup.send.await_count == 1
    finally: control.close()
