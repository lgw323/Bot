import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.operations.adapters.configuration import load_log_channel, load_settings
from discordbot.operations.adapters.discord_logging import DiscordLogging, Notice, notice
from discordbot.platform.errors import AppError
from .test_runtime import config_files


def record(level, name='discordbot.music', message='private %s', fields=None):
    row = logging.LogRecord(name, level, '/private/path', 1, message, ('token-secret https://private.invalid/ 123456789012345678',), None)
    if fields is not None:
        row.fields = fields
    return row


def test_legacy_warning_error_selection_and_private_fields_never_escape():
    assert notice(record(logging.INFO)) is None
    assert notice(record(logging.WARNING, 'discord.gateway')) is None
    assert notice(record(logging.WARNING, message='ConnectionClosed: %s')) is None
    assert notice(record(logging.ERROR, 'discord.gateway')) is not None
    item = notice(record(logging.INFO, 'discordbot.events', fields={
        'event': 'database.probe_failed', 'result': 'failed', 'error_code': 'deadline_exceeded',
        'token': 'secret', 'user_id': 123456789012345678, 'sql': 'private'}))
    assert 'database.probe_failed' in item.description and 'deadline_exceeded' in item.description
    for private in ('secret', '123456789012345678', 'private', 'https:'):
        assert private not in item.description
    assert notice(record(logging.ERROR, 'discordbot.operations.adapters.discord_logging')) is None


def test_optional_sidecar_never_reuses_watch_admin_and_does_not_change_main_config(config_files):
    config, credentials = config_files
    before = config.read_bytes()
    assert load_settings(config, credentials, 'discord-bot').log_channel is None
    config.with_name('logging.json').write_text(json.dumps({'version': 1, 'channel_id': 42}))
    settings = load_settings(config, credentials, 'discord-bot')
    assert settings.log_channel == 42 and settings.admin_channel != 42
    assert '42' not in repr(settings)
    assert load_settings(config, credentials, 'watch-web').log_channel is None
    assert config.read_bytes() == before


@pytest.mark.parametrize('value', [{'version': 1, 'channel_id': True}, {'version': 1, 'channel_id': 0},
    {'version': 1, 'channel_id': '42'}, {'version': 1, 'channel_id': 42, 'extra': 1},
    {'version': True, 'channel_id': 42}])
def test_malformed_destination_fails_closed(tmp_path, value):
    (tmp_path / 'logging.json').write_text(json.dumps(value))
    with pytest.raises(AppError):
        load_log_channel(tmp_path / 'config.json', 'discord-bot')


def fixture():
    now = [0.]
    channel = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(is_ready=lambda: True, get_channel=lambda _: channel,
        fetch_channel=AsyncMock(), add_listener=lambda *args: None, remove_listener=lambda *args: None)
    owner = DiscordLogging(bot, 42, SimpleNamespace(monotonic=lambda: now[0]), None)
    owner.closed = False
    return owner, now, channel


@pytest.mark.asyncio
async def test_queue_bound_dedup_startup_once_rate_limit_and_unavailable():
    owner, now, channel = fixture()
    await owner.ready(); await owner.ready()
    assert len(owner.queue) == 1
    await owner.deliver_one()
    assert channel.send.await_count == 1
    assert channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'] == []
    item = Notice('warning', 'safe', 0)
    owner.enqueue(item); owner.enqueue(item)
    assert len(owner.queue) == 1
    await owner.deliver_one()
    assert channel.send.await_count == 1
    owner.bot.is_ready = lambda: False
    now[0] = 5
    await owner.deliver_one()
    assert len(owner.queue) == 1
    owner.bot.is_ready = lambda: True
    await owner.deliver_one()
    assert channel.send.await_count == 2
    for number in range(200):
        owner.enqueue(Notice('synthetic', str(number), 0))
    assert len(owner.queue) == 32 and len(owner.recent) <= 128 and owner.dropped == 168
    await owner.stop()
    assert not owner.queue


@pytest.mark.asyncio
async def test_rate_limit_retry_is_once_bounded_and_does_not_repeat_uncertain_delivery():
    owner, now, channel = fixture()
    owner.enqueue(Notice('synthetic', 'safe', 0))
    channel.send.side_effect = discord.RateLimited(10)
    await owner.deliver_one()
    assert owner.queue[0].attempts == 1 and owner.next_send == 10
    now[0] = 10
    await owner.deliver_one()
    assert not owner.queue and owner.failures == 2
    assert channel.send.call_args_list[0].kwargs['nonce'] == channel.send.call_args_list[1].kwargs['nonce']
    with discord.http.handle_message_parameters(nonce=channel.send.call_args.kwargs['nonce']) as params:
        assert params.payload['enforce_nonce'] is True
    now[0] = 70
    owner.enqueue(Notice('synthetic', 'safe', 0))
    channel.send.side_effect = TimeoutError('secret')
    await owner.deliver_one()
    assert not owner.queue and owner.failures == 3
    await owner.stop()


@pytest.mark.asyncio
async def test_owned_handler_and_task_cleanup_preserve_other_handlers():
    owner, _, _ = fixture()
    root = logging.getLogger()
    other = logging.NullHandler()
    root.addHandler(other)
    tasks = []
    def start(spec, factory):
        task = asyncio.create_task(factory()); tasks.append(task); return task
    owner.supervisor = SimpleNamespace(start=start)
    try:
        await owner.start()
        assert root.handlers.count(owner.handler) == 1
        await owner.stop()
        assert owner.handler not in root.handlers and other in root.handlers
        assert all(task.done() for task in tasks)
    finally:
        root.removeHandler(other)
        await owner.stop()


@pytest.mark.asyncio
async def test_optional_capacity_failure_does_not_fail_core_start_or_retain_handler():
    from discordbot.platform.errors import CapacityError
    owner, _, _ = fixture()
    def full(*args):
        raise CapacityError('synthetic')
    owner.supervisor = SimpleNamespace(start=full)
    await owner.start()
    assert owner.closed and owner.handler not in logging.getLogger().handlers
    assert owner.gauges()['discord_log_worker_enabled'] == 0
    await owner.stop()


@pytest.mark.asyncio
async def test_send_library_errors_cannot_feed_the_notification_queue():
    owner, _, channel = fixture()
    owner.enqueue(Notice('synthetic', 'safe', 0))
    async def fails(**kwargs):
        owner.handler.emit(record(logging.ERROR, 'discord.http'))
        raise TimeoutError('private')
    channel.send.side_effect = fails
    await owner.deliver_one()
    assert not owner.queue and owner.failures == 1
    await owner.stop()
