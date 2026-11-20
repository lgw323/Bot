"""Synthetic callback/counter checks; no loop, socket, Discord send or real data."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from discordbot.operations.adapters.discord_logging import DiscordLogging, Notice, notice
from discordbot.operations.adapters.gateway_observations import GatewayObservations
from discordbot.platform.telemetry import JsonEventFormatter


def complete_inline(coroutine):
    """These callbacks only update memory; fail if they ever start awaiting I/O."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    else:
        pytest.fail('Gateway observation unexpectedly yielded to I/O')
    finally:
        coroutine.close()


def owner():
    clock = [0.0]
    bot = SimpleNamespace(latency=0.125)
    sink = DiscordLogging(bot, 42, SimpleNamespace(monotonic=lambda: clock[0]), None)
    sink.closed = False
    sink.announced = True
    return sink, clock


def recovery(sink, clock, begin, end):
    clock[0] = begin
    complete_inline(sink.disconnected())
    clock[0] = end
    complete_inline(sink.resumed())
    complete_inline(sink.ready())


def test_frequent_short_recovery_is_measured_without_changing_sixty_second_policy(caplog):
    sink, clock = owner()
    caplog.set_level(logging.INFO)
    for begin in (0.0, 10.0, 61.0):
        recovery(sink, clock, begin, begin + 0.2)
    gauges = sink.gauges()
    assert sink.reconnects == 3 and len(sink.queue) == 2
    assert gauges['discord_log_disconnect_events_total'] == 3
    assert gauges['discord_log_recovery_under_one_second_total'] == 3
    assert gauges['discord_log_recovery_notices_enqueued_total'] == 2
    assert gauges['discord_log_recovery_notices_not_enqueued_total'] == 1
    assert sink.suppressed == 1
    assert gauges['discord_log_last_heartbeat_latency_seconds'] == .125
    observed = [row for row in caplog.records if row.msg == 'discord.gateway_recovery_observed']
    assert len(observed) == 3
    assert [row.fields['connection_sequence'] for row in observed] == [1, 2, 3]
    assert [row.fields['recovery_notice_enqueued'] for row in observed] == [True, False, True]
    assert all(row.fields['sdk_callback'] == 'resumed' for row in observed)
    assert all(notice(row) is None for row in caplog.records)
    for item in sink.queue:
        assert dict(item.card.fields)['관측된 연결 이벤트 간격'] == '1초 미만'
        assert dict(item.card.fields)['중단 원인'] == '확인되지 않음'


def test_repeated_disconnect_and_ready_do_not_inflate_observations():
    sink, clock = owner()
    complete_inline(sink.ready())
    clock[0] = 10
    complete_inline(sink.disconnected())
    clock[0] = 11
    complete_inline(sink.disconnected())
    clock[0] = 12
    complete_inline(sink.ready())
    complete_inline(sink.resumed())
    assert sink.reconnects == 1 and len(sink.queue) == 1
    assert sink.gauges()['discord_log_disconnect_events_total'] == 1
    assert sink.gauges()['discord_log_last_observed_connection_interval_seconds'] == 2


def test_startup_and_disabled_sink_do_not_claim_recovery():
    sink, _ = owner()
    sink.announced = False
    complete_inline(sink.disconnected())
    complete_inline(sink.ready())
    assert sink.reconnects == 0 and len(sink.queue) == 1
    assert sink.gauges()['discord_log_disconnect_events_total'] == 0
    sink.closed = True
    complete_inline(sink.disconnected())
    complete_inline(sink.resumed())
    assert sink.reconnects == 0


@pytest.mark.parametrize('start,end', [
    (None, 1), (0, None), (1, 0), (True, 1), ('PRIVATE', 1),
    (float('nan'), 1), (0, float('inf')), (-1e308, 1e308),
    (10**1000, 10**1000 + 1),
])
def test_invalid_intervals_stay_unknown_and_json_is_strict(start, end):
    counter = GatewayObservations()
    counter.disconnected(None)
    fields = counter.recovered(start, end, 'ready', True, float('nan'))
    assert fields['observed_interval_seconds'] is None
    assert fields['sdk_last_heartbeat_latency_seconds'] is None
    assert counter.unknown_intervals == 1 and counter.under_one_second == 0
    assert counter.last_interval == -1 and counter.last_latency == -1
    assert 'PRIVATE' not in json.dumps(fields, allow_nan=False)


def test_over_limit_measurement_is_capped_and_explicit():
    counter = GatewayObservations()
    fields = counter.recovered(0, 1e308, 'resumed', True, 1e308)
    assert fields['observed_interval_seconds'] == 7 * 86400
    assert fields['interval_capped'] is True
    assert counter.capped_intervals == 1 and counter.unknown_intervals == 0
    assert fields['sdk_last_heartbeat_latency_seconds'] is None


def test_rejected_objects_are_never_coerced_or_formatted():
    class Private:
        def __str__(self):
            raise AssertionError('private value rendered')
        def __float__(self):
            raise AssertionError('private value coerced')
    value = Private()
    counter = GatewayObservations()
    fields = counter.recovered(value, value, value, False, value)
    row = logging.LogRecord('discordbot.operations.adapters.discord_logging', logging.INFO,
                            __file__, 1, fields['event'], (), None)
    row.fields = fields
    rendered = json.loads(JsonEventFormatter().format(row))
    assert rendered['sdk_callback'] == 'unknown'
    assert rendered['cause'] == 'unconfirmed'
    assert rendered['measurement_scope'] == 'sdk_callback_interval_not_total_outage'
    assert rendered['observed_interval_seconds'] is None
    assert rendered['recovery_notice_enqueued'] is False
    assert notice(row) is None


def test_optional_observation_failure_cannot_break_recovery(monkeypatch):
    sink, clock = owner()
    monkeypatch.setattr('discordbot.operations.adapters.discord_logging.logger.info',
                        Mock(side_effect=RuntimeError('PRIVATE log sink failure')))
    recovery(sink, clock, 10, 10.2)
    assert sink.reconnects == 1 and len(sink.queue) == 1
    assert sink.disconnected_at is None and sink.disconnect_observed is False
    assert sink.connection_observation_failures == 2
    assert sink.gauges()['discord_log_recovery_notices_enqueued_total'] == 1


def test_unavailable_latency_does_not_block_the_callback():
    sink, clock = owner()
    class Bot:
        @property
        def latency(self):
            raise RuntimeError('PRIVATE SDK detail')
    sink.bot = Bot()
    recovery(sink, clock, 0, 1)
    assert sink.reconnects == 1 and len(sink.queue) == 1
    assert sink.gauges()['discord_log_last_heartbeat_latency_seconds'] == -1


def test_queue_rejection_is_not_mislabeled_as_duplicate_suppression(monkeypatch):
    sink, clock = owner()
    original_enqueue = sink.enqueue
    monkeypatch.setattr(sink, 'enqueue', lambda *args, **kwargs: False)
    recovery(sink, clock, 0, .2)
    assert sink.gauges()['discord_log_recovery_notices_not_enqueued_total'] == 1
    assert sink.suppressed == 0
    monkeypatch.setattr(sink, 'enqueue', original_enqueue)
    sink.enqueue(Notice('unrelated warning', 'synthetic', 0))
    assert len(sink.queue) == 1


def test_new_instance_does_not_claim_durable_history():
    first, clock = owner()
    recovery(first, clock, 0, .2)
    second, _ = owner()
    assert second.gauges()['discord_log_disconnect_events_total'] == 0
    assert second.gauges()['discord_log_last_observed_connection_interval_seconds'] == -1
