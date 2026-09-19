import json
import logging

import pytest

from discordbot.platform.errors import ExternalPermanentError
from discordbot.platform.telemetry import JsonEventFormatter
from .conftest import settle, song

pytestmark = pytest.mark.asyncio


async def test_failed_preparation_reports_stage_code_without_track_or_exception_data(rig, caplog):
    caplog.set_level(logging.INFO, logger='discordbot.music')
    marker = 'private-payload-must-not-be-logged'
    rig[4].acquire.side_effect = ExternalPermanentError(marker, context={'url':marker,'user_id':987654321})
    actor = rig[0]()
    await actor.ask('connect', channel_id=123)
    await actor.ask('enqueue', tracks=(song(title=marker),))
    await settle(lambda: actor.projection().status == 'retry')
    failures = [r for r in caplog.records if r.msg == 'music.work_failed']
    assert len(failures) == 1
    assert failures[0].fields['stage'] == 'prepare'
    assert failures[0].fields['error_code'] == 'external_permanent'
    assert len(failures[0].fields['work_id']) == 32
    encoded = '\n'.join(JsonEventFormatter().format(r) for r in caplog.records)
    assert marker not in encoded and '987654321' not in encoded and 'example.invalid' not in encoded
    assert {'music.voice_connected','music.enqueued','music.work_started'} <= {r.msg for r in caplog.records}


async def test_ui_failure_does_not_log_error_message_or_context(caplog):
    from discordbot.music.adapters.discord_ui import report_failure
    caplog.set_level(logging.WARNING, logger='discordbot.music')
    report_failure('action', ExternalPermanentError('private-title',context={'user_id':123456789,'url':'private-url'}))
    payload = json.loads(JsonEventFormatter().format(caplog.records[-1]))
    assert payload['event']=='music.ui_failed' and payload['stage']=='action'
    assert payload['error_code']=='external_permanent'
    assert 'private' not in json.dumps(payload) and '123456789' not in json.dumps(payload)


async def test_cache_diagnostics_separate_acquisition_from_reused_lease(rig, tmp_path, caplog):
    from discordbot.music.adapters.cache import DiskCache
    from discordbot.platform.executors import BoundedExecutor

    caplog.set_level(logging.INFO, logger='discordbot.music')
    executor = BoundedExecutor(workers=1,queue_capacity=2,name='cache-diagnostics')
    cache = DiskCache(tmp_path/'cache',executor,rig[1])
    async def produce(path, maximum):
        path.write_bytes(b'synthetic audio')
    try:
        await cache.start()
        for _ in range(2):
            media = await cache.acquire('private-content-identity',produce)
            await cache.release(media)
        events = [r for r in caplog.records if r.msg=='music.cache_leased']
        assert [r.fields['result'] for r in events]==['published','hit']
        assert sum(r.msg=='music.media_acquired' for r in caplog.records)==1
        assert 'private-content-identity' not in '\n'.join(JsonEventFormatter().format(r) for r in caplog.records)
    finally:
        await cache.close()
        await executor.close(grace_seconds=2)
