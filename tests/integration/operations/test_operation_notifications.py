import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from discordbot.operations.adapters import discord_logging as logs
from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.operations.adapters.operation_notifications import (
    OperationNotifications, _cursor, operation_key, result_message, startup_description,
)
from discordbot.operations.adapters.operation_results import OperationResults, read_operation_result
from discordbot.platform.errors import DataIntegrityError

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


class Executor:
    async def run(self, fn, *args):
        return fn(*args)

    async def run_retained(self, fn, *args):
        return fn(*args)


def outcome(path, result='ok', *, operation='restart', age=0, stage='complete'):
    return OperationResults(path).write(operation, 'manual', result, stage, 'release',
        identity='a' * 32, receipt='b' * 64, timestamp=NOW - timedelta(seconds=age))


def fixture(path=None):
    time = [0.0]
    channel = SimpleNamespace(send=AsyncMock())
    listeners = []
    bot = SimpleNamespace(is_ready=lambda: True, get_channel=lambda _: channel,
        fetch_channel=AsyncMock(), add_listener=lambda fn, event: listeners.append((fn, event)),
        remove_listener=lambda fn, event: listeners.remove((fn, event)) if (fn, event) in listeners else None)
    kwargs = dict(state=path, executor=Executor(), release='release') if path is not None else {}
    owner = logs.DiscordLogging(bot, 42, SimpleNamespace(monotonic=lambda: time[0], now=lambda: NOW), None, **kwargs)
    owner.closed = False
    return owner, time, channel, listeners


def test_fixed_size_latest_outcome_roundtrip_and_no_arbitrary_fields(tmp_path):
    row = outcome(tmp_path)
    assert read_operation_result(tmp_path) == row
    outcome(tmp_path, 'failed', stage='smoke')
    assert read_operation_result(tmp_path)['result'] == 'failed'
    assert len(list(tmp_path.iterdir())) == 1 and (tmp_path / 'operation-result.json').stat().st_size < 4096
    assert 'b' * 64 in (tmp_path / 'operation-result.json').read_text()
    row['private_content'] = 'private message'
    atomic_json(tmp_path / 'operation-result.json', row)
    with pytest.raises(DataIntegrityError):
        read_operation_result(tmp_path)


@pytest.mark.parametrize('key,value', [('version', True), ('operation', 'shell'), ('source', {}),
    ('result', 'success_guessed'), ('stage', 'private path/token'), ('receipt', 'raw interaction'),
    ('release', '/home/private/release'), ('timestamp', '2026-10-30T00:00:00'), ('id', 'private-token')])
def test_invalid_status_never_becomes_public_success(tmp_path, key, value):
    row = outcome(tmp_path)
    row[key] = value
    atomic_json(tmp_path / 'operation-result.json', row)
    with pytest.raises(DataIntegrityError):
        read_operation_result(tmp_path)


@pytest.mark.parametrize('raw', [b'{"version":1,"version":1}', b'{' + b' ' * 4097, b'[]'])
def test_malformed_or_oversized_metadata_rejected(tmp_path, raw):
    (tmp_path / 'operation-result.json').write_bytes(raw)
    with pytest.raises(DataIntegrityError):
        read_operation_result(tmp_path)


def test_naive_writer_timestamp_rejected(tmp_path):
    with pytest.raises(DataIntegrityError):
        OperationResults(tmp_path).write('restart', 'operator', 'ok', 'complete', 'release', timestamp=NOW.replace(tzinfo=None))


@pytest.mark.parametrize('operation,result,stage', [('restart','ok','unchanged'), ('update','ok','build'),
    ('restart','ok_cleanup_failed','retention'), ('update','ok_cleanup_failed','complete')])
def test_success_requires_actual_terminal_stage(tmp_path, operation, result, stage):
    with pytest.raises(DataIntegrityError):outcome(tmp_path,result,operation=operation,stage=stage)


def test_render_boundary_rejects_injected_result_fields(tmp_path):
    row=outcome(tmp_path);row['stage']='private message token URL'
    with pytest.raises(DataIntegrityError):result_message(row)
    assert 'private' not in startup_description('release',row,NOW)


def test_startup_reason_distinguishes_observed_request_and_unknown_cause(tmp_path):
    row = outcome(tmp_path, 'in_progress', stage='checkpoint')
    text = startup_description('release', row, NOW)
    assert '진행 중' in text and '최종 완료 검증 대기' in text
    assert '직접 원인을 확정하지 않습니다' in text and '시작 원인: 확인되지 않음' in text
    for age in [601, -61]:
        row = outcome(tmp_path, 'in_progress', age=age, stage='checkpoint')
        assert '최근 운영 기록' not in startup_description('release', row, NOW)
    assert '최근 운영 기록' not in startup_description('release', outcome(tmp_path), NOW)


def test_unchanged_update_is_check_not_actual_update_or_health_success(tmp_path):
    title, text, color = result_message(outcome(tmp_path, operation='update', stage='unchanged'))
    assert '변경 없음' in title and '실행하지 않았습니다' in text
    assert '건강 상태를 검증했다는 뜻은 아닙니다' in text and color == 0x3498DB
    with pytest.raises(DataIntegrityError):
        result_message(outcome(tmp_path, 'in_progress'))


@pytest.mark.asyncio
async def test_terminal_state_and_delivery_cursor_survive_restart_without_duplicate(tmp_path):
    row = outcome(tmp_path)
    reader = OperationNotifications(tmp_path, Executor())
    assert await reader.snapshot(NOW) == row
    reader.admitted(row)
    assert await reader.snapshot(NOW) is None
    await reader.claim(operation_key(row))
    await reader.delivered(operation_key(row))
    rebooted = OperationNotifications(tmp_path, Executor())
    assert await rebooted.snapshot(NOW) is None and rebooted.uncertain == 0
    assert set(_cursor(tmp_path / 'operation-notice.json')) == {'version', 'key', 'phase'}


@pytest.mark.asyncio
async def test_claimed_crash_is_uncertain_and_never_blindly_replayed(tmp_path):
    row = outcome(tmp_path)
    reader = OperationNotifications(tmp_path, Executor())
    await reader.claim(operation_key(row))
    rebooted = OperationNotifications(tmp_path, Executor())
    assert await rebooted.snapshot(NOW) is None
    assert await rebooted.snapshot(NOW) is None and rebooted.uncertain == 1
    assert read_operation_result(tmp_path)['result'] == 'ok'  # Outcome is not lost with its alert.


@pytest.mark.asyncio
@pytest.mark.parametrize('result,age', [('in_progress', 0), ('ok', 86401), ('ok', -61)])
async def test_nonterminal_stale_future_results_not_announced(tmp_path, result, age):
    outcome(tmp_path, result, age=age)
    reader = OperationNotifications(tmp_path, Executor())
    assert await reader.snapshot(NOW) is None


@pytest.mark.asyncio
async def test_first_connection_and_resumed_ready_recovery_are_distinct_and_not_optimistic(tmp_path):
    outcome(tmp_path, 'in_progress', stage='checkpoint')
    owner, time, channel, _ = fixture(tmp_path)
    await owner.ready()
    assert len(owner.queue) == 1 and '전체 서비스' in owner.queue[0].description
    assert '최종 완료 검증 대기' in owner.queue[0].description
    await owner.ready()
    assert len(owner.queue) == 1
    await owner.disconnected();time[0] = 11
    await owner.resumed();await owner.ready()
    assert len(owner.queue) == 2 and '약 11초' in owner.queue[0].description
    assert owner.gauges()['discord_log_reconnects'] == 1
    assert channel.send.await_count == 0
    await owner.stop()


@pytest.mark.asyncio
async def test_operation_delivery_claimed_then_delivered_and_no_transport_payload_persistence(tmp_path):
    row = outcome(tmp_path)
    owner, _, channel, _ = fixture(tmp_path)
    await owner.poll_operations()
    assert len(owner.queue) == 1
    await owner.deliver_one()
    assert channel.send.await_count == 1
    assert _cursor(tmp_path / 'operation-notice.json')['phase'] == 'delivered'
    assert channel.send.call_args.kwargs['nonce'] == hashlib.sha256(operation_key(row).encode()).hexdigest()[:24]
    assert channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'] == []
    assert '완료 검증' in channel.send.call_args.kwargs['embed'].title
    assert all('완료' not in f.read_text() for f in tmp_path.iterdir())
    assert await OperationNotifications(tmp_path, Executor()).snapshot(NOW) is None
    await owner.stop()


@pytest.mark.asyncio
async def test_explicit_429_retry_once_same_nonce_then_rejected_persisted(tmp_path):
    outcome(tmp_path)
    owner, time, channel, _ = fixture(tmp_path)
    channel.send.side_effect = discord.RateLimited(10)
    await owner.poll_operations();await owner.deliver_one()
    assert len(owner.queue) == 1 and owner.queue[0].attempts == 1
    assert _cursor(tmp_path / 'operation-notice.json')['phase'] == 'rejected'
    time[0] = 10;await owner.deliver_one()
    assert not owner.queue and owner.failures == 2 and owner.retries == 1
    assert channel.send.call_args_list[0].kwargs['nonce'] == channel.send.call_args_list[1].kwargs['nonce']
    fresh = OperationNotifications(tmp_path, Executor())
    assert await fresh.snapshot(NOW) is None and fresh.uncertain == 0
    await owner.stop()


@pytest.mark.asyncio
async def test_timeout_is_observable_and_not_replayed_across_process(tmp_path):
    outcome(tmp_path)
    owner, _, channel, _ = fixture(tmp_path)
    channel.send.side_effect = TimeoutError('private token and user chat')
    await owner.poll_operations();await owner.deliver_one()
    assert owner.failures == owner.uncertain == owner.dropped == 1 and not owner.queue
    assert await OperationNotifications(tmp_path, Executor()).snapshot(NOW) is None
    assert all('private' not in f.read_text() for f in tmp_path.iterdir())
    await owner.stop()


@pytest.mark.asyncio
async def test_cancellation_during_send_preserves_uncertain_marker(tmp_path):
    outcome(tmp_path)
    owner, _, channel, _ = fixture(tmp_path)
    entered = asyncio.Event()
    async def wait(**kwargs):
        entered.set();await asyncio.Event().wait()
    channel.send.side_effect = wait
    await owner.poll_operations();task = asyncio.create_task(owner.deliver_one())
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert owner.uncertain == 1 and owner.failures == 1
    assert await OperationNotifications(tmp_path, Executor()).snapshot(NOW) is None
    await owner.stop()


@pytest.mark.asyncio
async def test_cursor_storage_failure_never_sends_before_claim(tmp_path, monkeypatch):
    outcome(tmp_path)
    owner, _, channel, _ = fixture(tmp_path)
    await owner.poll_operations()
    async def fail(key):raise PermissionError('private path')
    monkeypatch.setattr(owner.operations, 'claim', fail)
    await owner.deliver_one()
    assert channel.send.await_count == 0 and owner.storage_failures == 1 and owner.dropped == 1
    await owner.stop()


@pytest.mark.asyncio
async def test_ack_failure_after_known_send_does_not_retry_or_fail_core(tmp_path, monkeypatch):
    outcome(tmp_path)
    owner,_,channel,_=fixture(tmp_path)
    await owner.poll_operations()
    async def fail(key):raise PermissionError('PRIVATE cursor')
    monkeypatch.setattr(owner.operations,'delivered',fail)
    await owner.deliver_one()
    assert channel.send.await_count==1 and owner.delivered==1 and owner.failures==0
    assert owner.storage_failures==1 and not owner.queue
    assert await OperationNotifications(tmp_path,Executor()).snapshot(NOW) is None
    await owner.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('delay',[-1,31,float('inf'),float('nan')])
async def test_invalid_or_unbounded_429_delay_never_retries(tmp_path,delay):
    outcome(tmp_path)
    owner,_,channel,_=fixture(tmp_path)
    error=discord.RateLimited(1);error.retry_after=delay
    channel.send.side_effect=error
    await owner.poll_operations();await owner.deliver_one()
    assert not owner.queue and owner.retries==0 and owner.failures==1 and owner.dropped==1
    await owner.stop()


@pytest.mark.asyncio
async def test_corrupt_cursor_is_observable_not_core_failure(tmp_path):
    outcome(tmp_path)
    atomic_json(tmp_path / 'operation-notice.json', {'version': 1, 'key': 'private secret', 'phase': {}})
    owner, _, channel, _ = fixture(tmp_path)
    await owner.poll_operations()
    assert owner.storage_failures == 1 and not owner.queue and channel.send.await_count == 0
    await owner.stop()


@pytest.mark.asyncio
async def test_cancellation_retained_claim_finishes_atomic_write_but_never_starts_send(tmp_path):
    outcome(tmp_path)
    owner, _, channel, _ = fixture(tmp_path)
    await owner.poll_operations()
    class Cancelling(Executor):
        async def run_retained(self, fn, *args):
            task = asyncio.current_task();task.cancel()
            try:await asyncio.sleep(0)
            except asyncio.CancelledError:pass
            return fn(*args)
    owner.operations.executor = Cancelling()
    task = asyncio.create_task(owner.deliver_one())
    with pytest.raises(asyncio.CancelledError):await task
    assert channel.send.await_count == 0 and _cursor(tmp_path / 'operation-notice.json')['phase'] == 'claimed'
    await owner.stop()
