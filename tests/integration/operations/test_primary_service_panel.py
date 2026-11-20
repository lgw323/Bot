"""Primary services, independent Watch evidence; synthetic Discord only."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.operations.adapters.discord_admin import OperationsPanel
from discordbot.operations.adapters.service_status import PRIMARY_SERVICE_KEYS, SERVICES
from .test_admin_panel import interaction
from .test_unified_panel import NOW, RELEASE, observations, unified


REMOVED = ('watch', 'cloudflared', 'backup')
WATCH_RELEASE = 'r-' + 'c' * 16 + '-' + 'd' * 16
WATCH_FIELD = 'Watch · Bot 구성 요소'


def current(h):
    return h.messages[444].embeds[0]


def fields(h):
    return {field.name: field.value for field in current(h).fields}


def with_rows(h, **changes):
    h.services.snapshot.return_value = tuple(
        replace(row, **changes.get(row.key, {})) for row in observations())


def options(h, keys):
    select = next(child for group in h.messages[444].components for child in group.children
                  if child.custom_id == 'ops:v2:service')
    select.options = [discord.SelectOption(label=key, value=key) for key in keys]


@pytest.mark.asyncio
async def test_primary_choices_do_not_change_six_collector_contract(unified):
    h = unified
    assert PRIMARY_SERVICE_KEYS == ('bot', 'supper', 'forme', 'mymoney')
    assert tuple(spec.key for spec in SERVICES) == ('bot', 'watch', 'supper', 'forme', 'cloudflared', 'backup')
    assert tuple(option.value for option in h.panel.view.children[0].options) == PRIMARY_SERVICE_KEYS
    assert len(h.services.snapshot.return_value) == 6
    assert WATCH_FIELD in fields(h)
    assert {child.custom_id: child.disabled for child in h.panel.view.children[1:]} == {
        'ops:v2:refresh': False, 'ops:v2:restart': True,
        'ops:v2:update': True, 'ops:v2:backup': True}
    h.status.snapshot.assert_not_called()
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ('bot', 'supper', 'forme'))
async def test_primary_selection_keeps_same_panel_and_only_bot_nests_watch(unified, key):
    h = unified
    marker = h.panel.store.read()
    click = interaction()
    click.data = {'values': [key]}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service == key
    assert h.panel.message_id == 444 and h.panel.store.read() == marker
    assert h.channel.send.await_count == 1
    assert (WATCH_FIELD in fields(h)) is (key == 'bot')
    h.messages[444].delete.assert_not_called()
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', REMOVED)
@pytest.mark.parametrize('boundary', ('render', 'view', 'refresh'))
async def test_legacy_saved_selection_normalizes_to_bot_at_every_ui_boundary(unified, key, boundary):
    h = unified
    h.panel.selected_service = key
    if boundary == 'render':
        h.panel._service_embed(await h.panel._snapshot())
    elif boundary == 'view':
        view = h.panel._view()
        try:
            assert [option.value for option in view.children[0].options if option.default] == ['bot']
        finally:
            view.stop()
    else:
        await h.panel._refresh_panel()
        assert WATCH_FIELD in fields(h)
    assert h.panel.selected_service == 'bot'
    assert h.channel.send.await_count == 1
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', (*REMOVED, 'PRIVATE token=synthetic'))
async def test_removed_and_unknown_forged_selections_are_rejected_without_echo(unified, key):
    h = unified
    before = h.messages[444].edit.await_count
    click = interaction()
    click.data = {'values': [key]}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service == 'bot'
    assert h.messages[444].edit.await_count == before
    assert h.channel.send.await_count == 1
    assert key not in str(click.followup.send.call_args)
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_six_option_published_panel_upgrades_same_id_nonce_and_survives_restart(unified):
    h = unified
    marker = h.panel.store.read()
    options(h, [spec.key for spec in SERVICES])
    assert h.panel._own_panel(h.messages[444], generation=marker['nonce'], guild_id=71)
    await h.panel.stop()
    restarted = OperationsPanel(h.bot, master=1, channel=42, state=h.panel.store.state,
        inbox=h.inbox, status=h.status, clock=h.clock, supervisor=h.supervisor,
        executor=h.executor, services=h.services)
    await restarted.start()
    try:
        assert restarted.message_id is None
        await restarted.ready()
        assert restarted.message_id == 444 and restarted.store.read() == marker
        assert h.channel.send.await_count == 1
        assert tuple(option.value for option in restarted.view.children[0].options) == PRIMARY_SERVICE_KEYS
        assert current(h).footer.text.endswith(' · 패널: ' + marker['nonce'])
        assert await restarted.verified_link() == 'https://discord.com/channels/71/42/444'
        h.messages[444].delete.assert_not_called()
    finally:
        await restarted.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('keys', [
    ('bot', 'supper'), ('bot', 'supper', 'forme', 'backup'),
    ('bot', 'supper', 'unknown'), ('bot', 'bot', 'forme'),
    ('bot', 'supper', 'forme', 'bot', 'supper', 'forme'),
    ('bot', 'watch', 'supper', 'forme', 'backup', 'backup'),
])
async def test_current_panel_proof_rejects_non_exact_or_duplicated_selector_payload(unified, keys):
    h = unified
    marker = h.panel.store.read()
    options(h, keys)
    assert not h.panel._own_panel(h.messages[444], generation=marker['nonce'], guild_id=71)
    h.panel._invalidate_link()
    assert await h.panel.verified_link() is None
    h.messages[444].edit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('identity', ('author', 'channel', 'guild', 'generation'))
async def test_primary_shape_does_not_relax_existing_panel_identity_proof(unified, identity):
    h = unified
    marker = h.panel.store.read()
    message = h.messages[444]
    kwargs = {'generation': marker['nonce'], 'guild_id': 71}
    if identity == 'author':
        message.author = SimpleNamespace(id=901)
    elif identity == 'channel':
        message.channel = SimpleNamespace(id=99, guild=h.channel.guild)
    elif identity == 'guild':
        message.guild = SimpleNamespace(id=72)
    else:
        kwargs['generation'] = 'e' * 32
    assert not h.panel._own_panel(message, **kwargs)
    h.messages[444].edit.assert_not_called()


@pytest.mark.asyncio
async def test_watch_failure_is_red_without_rewriting_healthy_bot_evidence(unified):
    h = unified
    with_rows(h, watch=dict(state='실패', health='미통과', version=WATCH_RELEASE,
                           observed_at=NOW-timedelta(seconds=5)))
    await h.panel._refresh_panel()
    assert '프로세스: 실행 중' in current(h).description and '검사: 통과' in current(h).description
    assert current(h).color.value == 0xFF0000
    watch = fields(h)[WATCH_FIELD]
    assert '실패' in watch and '미통과' in watch
    assert next(spec.health_scope for spec in SERVICES if spec.key == 'watch') in watch
    assert '2026-10-31 11:59:55 UTC' in watch and '5초 전' in watch
    assert 'cccccccc' in watch and 'dddddddd' in watch and '실행 health 응답' in watch
    assert 'aaaaaaaa' not in watch
    assert 'aaaaaaaa' in fields(h)['실행 버전 · 출처']


@pytest.mark.asyncio
async def test_bot_failure_is_red_without_rewriting_healthy_watch_evidence(unified):
    h = unified
    with_rows(h, bot=dict(state='실패', health='미통과'), watch=dict(version=WATCH_RELEASE))
    await h.panel._refresh_panel()
    assert '프로세스: 실패' in current(h).description and '검사: 미통과' in current(h).description
    assert current(h).color.value == 0xFF0000
    watch = fields(h)[WATCH_FIELD]
    assert '프로세스: 실행 중' in watch and '검사: 통과' in watch
    assert 'cccccccc' in watch


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ('unknown', 'stale', 'future', 'missing_time'))
async def test_watch_unknown_or_noncurrent_evidence_is_explicit_and_gray(unified, kind):
    h = unified
    change = {'health': '미확인', 'version': None, 'version_provenance': '실행 버전 미제공'}
    if kind == 'stale':
        change = {'observed_at': NOW-timedelta(seconds=61), 'version': WATCH_RELEASE}
    elif kind == 'future':
        change = {'observed_at': NOW+timedelta(seconds=1), 'version': WATCH_RELEASE}
    elif kind == 'missing_time':
        change.update(state='미확인', observed_at=None)
    with_rows(h, watch=change)
    await h.panel._refresh_panel()
    assert '프로세스: 실행 중' in current(h).description and '검사: 통과' in current(h).description
    assert current(h).color.value == 0x95A5A6
    watch = fields(h)[WATCH_FIELD]
    assert '미확인' in watch
    if kind == 'stale':
        assert '오래된 관측' in watch and '이전 관측' in watch
    elif kind == 'future':
        assert '미래 관측 시각' in watch and '이전 관측' in watch
    elif kind == 'missing_time':
        assert '미제공' in watch


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ('exception', 'malformed'))
async def test_provider_failure_does_not_leave_previous_healthy_bot_or_watch(unified, failure):
    h = unified
    if failure == 'exception':
        h.services.snapshot.side_effect = RuntimeError('PRIVATE secret=synthetic')
    else:
        with_rows(h, watch=dict(health_scope='PRIVATE secret=synthetic'))
    await h.panel._refresh_panel()
    assert '상태 수집 실패' in current(h).description
    assert current(h).color.value == 0x95A5A6
    assert '미확인' in fields(h)[WATCH_FIELD]
    assert 'PRIVATE' not in str(current(h).to_dict())
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('user,channel,message', [(2,42,444), (True,42,444), (1,99,444), (1,42,999)])
async def test_primary_select_checks_authority_before_provider_or_message_edit(unified, user, channel, message):
    h = unified
    count = h.services.snapshot.await_count
    click = interaction(user=user, channel=channel, message=message)
    click.data = {'values': ['forme']}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service == 'bot' and h.services.snapshot.await_count == count
    h.messages[444].edit.assert_not_called()
    click.response.defer.assert_not_called()
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_refresh_and_forged_legacy_actions_never_create_or_execute(unified):
    h = unified
    marker = h.panel.store.read()
    for _ in range(3):
        await h.panel.interact(interaction(), 'refresh')
    for action in ('restart', 'update', 'backup', 'confirm', 'cancel', 'ops:v1:restart'):
        await h.panel.interact(interaction(), action, 'old-confirmation')
    assert h.panel.store.read() == marker and h.panel.message_id == 444
    assert h.channel.send.await_count == 1 and not h.panel.confirmations
    assert len(h.messages) == 1
    h.messages[444].delete.assert_not_called()
    h.inbox.accept_current.assert_not_called()
    h.status.snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_changed_generation_denies_old_primary_callback_without_new_message(unified):
    h = unified
    h.panel.store.rotate(h.panel.store.read())  # Temporary local store only; no send.
    click = interaction()
    click.data = {'values': ['supper']}
    await h.panel.view.children[0].callback(click)
    assert h.panel.selected_service == 'bot' and h.panel.message_id is None
    assert h.channel.send.await_count == 1
    h.messages[444].edit.assert_not_called()
    h.inbox.accept_current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ('bot', 'supper', 'forme'))
async def test_primary_panel_stays_inside_discord_limits_without_mentions_or_operation_views(unified, key):
    h = unified
    h.panel.selected_service = key
    await h.panel._refresh_panel()
    embed = current(h)
    utf16 = lambda value: len(value.encode('utf-16-le')) // 2
    assert utf16(embed.title) <= 256 and utf16(embed.description) <= 4096
    assert len(embed.fields) <= 25 and sum(utf16(str(value)) for value in (
        embed.title, embed.description, embed.footer.text,
        *[part for field in embed.fields for part in (field.name,field.value)])) <= 6000
    assert all(utf16(field.name) <= 256 and utf16(field.value) <= 1024 for field in embed.fields)
    assert utf16(embed.footer.text) <= 2048
    assert 'Bot 중단 시 갱신 불가' in embed.footer.text
    kwargs = h.messages[444].edit.call_args.kwargs
    assert not kwargs['allowed_mentions'].everyone and not kwargs['allowed_mentions'].users
    assert len(h.panel.view.children) == 5
    h.inbox.accept_current.assert_not_called()
