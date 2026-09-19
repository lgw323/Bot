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
    rig[4].acquire.side_effect = ExternalPermanentError(marker, context={'url':marker,'user_id':987654321,
        'reason':'http_forbidden','child_exit_code':1})
    actor = rig[0]()
    await actor.ask('connect', channel_id=123)
    await actor.ask('enqueue', tracks=(song(title=marker),))
    await settle(lambda: actor.projection().status == 'retry')
    failures = [r for r in caplog.records if r.msg == 'music.work_failed']
    assert len(failures) == 1
    assert failures[0].fields['stage'] == 'prepare'
    assert failures[0].fields['error_code'] == 'external_permanent'
    assert failures[0].fields['reason'] == 'http_forbidden'
    assert failures[0].fields['child_exit_code'] == 1
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


@pytest.mark.parametrize('diagnostic,reason,error_type', [
    ('ERROR: HTTP Error 403: Forbidden', 'http_forbidden', 'ExternalPermanentError'),
    ('Requested format is not available', 'no_audio_format', 'ExternalPermanentError'),
    ('Sign in to confirm your age', 'auth_required', 'ExternalPermanentError'),
    ('This is members-only', 'provider_rejected', 'PremiumOnly'),
    ('Private video', 'provider_rejected', 'UnavailableTrack'),
    ('Unable to download media', 'download_failed', 'ExternalPermanentError'),
    ('No supported JavaScript runtime could be found', 'js_runtime_missing', 'ExternalPermanentError'),
    ('Timed out', 'timeout', 'ExternalPermanentError'),
    ('unrecognized vendor response', 'child_nonzero', 'ExternalPermanentError'),
])
async def test_actual_child_nonzero_is_classified_without_stderr(rig, diagnostic, reason, error_type):
    import sys
    from discordbot.music.adapters.processes import ProcessPool
    pool = ProcessPool(rig[7])
    marker = 'private-payload-must-not-cross-error-boundary'
    try:
        with pytest.raises(ExternalPermanentError) as caught:
            await pool.run((sys.executable, '-c', 'import sys; sys.stderr.write(sys.argv[1]); sys.exit(7)',
                            diagnostic+' '+marker), seconds=3, name='acquire')
        assert type(caught.value).__name__ == error_type
        assert dict(caught.value.context) == {'reason':reason, 'child_exit_code':7}
        assert marker not in str(caught.value.to_log_fields())+str(caught.value)
        assert pool.admitted == 0 and not pool.children
    finally: await pool.close()


@pytest.mark.parametrize('reason,code,expected', [('private-title',1,{'child_exit_code':1}),
    ('http_forbidden',999999999,{'reason':'http_forbidden'}),
    ('timeout',True,{'reason':'timeout'}), ('timeout',-9,{'reason':'timeout','child_exit_code':-9})])
async def test_failure_field_allowlist_cannot_copy_arbitrary_context(reason, code, expected):
    from discordbot.music.domain.failures import safe_failure_fields
    assert safe_failure_fields({'reason':reason,'child_exit_code':code,'url':'private-url'}) == expected


@pytest.mark.parametrize('mode,reason', [('missing','executable_not_found'),('timeout','timeout')])
async def test_spawn_and_deadline_are_distinct_from_provider_rejection(rig, mode, reason):
    import sys
    from discordbot.music.adapters.processes import ProcessPool
    from discordbot.platform.errors import AppError
    pool = ProcessPool(rig[7], kill_seconds=.2)
    args = ('no-such-synthetic-music-executable',) if mode == 'missing' else (sys.executable,'-c','import time; time.sleep(60)')
    try:
        with pytest.raises(AppError) as caught: await pool.run(args, seconds=.1, name='acquire')
        assert caught.value.context['reason'] == reason
        assert not pool.children and pool.admitted == 0
    finally: await pool.close()


@pytest.mark.parametrize('mode,reason', [('empty','empty_output'),('write','cache_write_failure'),('publish','cache_publish_failure')])
async def test_cache_failure_boundary_and_partial_cleanup(rig, tmp_path, monkeypatch, mode, reason):
    import os
    from discordbot.music.adapters.cache import DiskCache
    from discordbot.platform.errors import AppError
    from discordbot.platform.executors import BoundedExecutor
    executor = BoundedExecutor(workers=1, queue_capacity=2, name='cache-boundary')
    cache = DiskCache(tmp_path/'cache', executor, rig[1])
    async def produce(path, maximum):
        path.write_bytes(b'' if mode == 'empty' else b'synthetic')
        if mode == 'write': raise PermissionError('private path')
    try:
        await cache.start()
        if mode == 'publish':
            def denied(*args): raise PermissionError('private path')
            monkeypatch.setattr(os, 'replace', denied)
        with pytest.raises(AppError) as caught: await cache.acquire('synthetic', produce)
        assert caught.value.context['reason'] == reason
        assert not list(cache.directory.iterdir()) and cache.admitted == 0
    finally:
        await cache.close()
        await executor.close(grace_seconds=2)
