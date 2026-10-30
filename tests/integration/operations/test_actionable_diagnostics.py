"""Safe v1-level error evidence reaches a fake Discord send, never a live channel."""
import logging
from types import SimpleNamespace

from aiohttp import WSServerHandshakeError
import discord.client
import pytest

from discordbot.operations.adapters.discord_logging import diagnostic_fields, notice
from discordbot.platform.context import CorrelationContext, correlation_scope
from .test_discord_logging import fixture, record


def library_handshake_record(*, delay=418.37):
    namespace = vars(discord.client)
    name = '_PRIVATE_diagnostic_fixture_error'
    assert name not in namespace
    error = WSServerHandshakeError(SimpleNamespace(real_url='https://PRIVATE.invalid/?token=PRIVATE'), (),
                                  status=503, message='PRIVATE invalid response status',
                                  headers={'Authorization':'PRIVATE'})
    namespace[name] = error
    try:
        exec(compile('raise '+name, discord.client.__file__, 'exec'), namespace)
    except WSServerHandshakeError as caught:
        return logging.LogRecord('discord.client', logging.ERROR, '/home/PRIVATE/client.py', 781,
                                 'Attempting a reconnect in %.2fs', (delay,),
                                 (type(caught),caught,caught.__traceback__))
    finally:
        namespace.pop(name, None)


@pytest.mark.asyncio
async def test_real_handshake_type_503_stack_and_retry_reach_fake_delivery():
    owner, _, channel = fixture()
    row = library_handshake_record()
    row.getMessage = lambda: (_ for _ in ()).throw(AssertionError('raw log interpolation'))
    with correlation_scope(CorrelationContext('a'*32)):
        owner.handler.emit(row)
    await owner.deliver_one()
    actual = channel.send.call_args.kwargs
    content = actual['content']
    for expected in ['Summary:', 'HTTP 503', '세부 원인은 미확정', 'Severity: ERROR',
                     'Module: discord.client', 'Code: external_temporary', 'Recovery: pending',
                     'exception_type: WSServerHandshakeError', 'http_status: 503',
                     'retry_delay_seconds: 418.37', 'discord/client.py:', 'Correlation: '+'a'*32]:
        assert expected in content
    for hidden in ['PRIVATE','https://','/home/','Authorization','invalid response status']:
        assert hidden not in content
    assert actual['allowed_mentions'].to_dict()['parse'] == []
    assert content.count('```') == 2
    await owner.stop()


def test_unknown_external_logger_name_is_not_exported():
    row = library_handshake_record()
    row.name = 'PRIVATE.user.module'
    item = notice(row)
    assert 'Module: external' in item.description
    assert 'PRIVATE' not in item.description


@pytest.mark.parametrize('delay', [True,-1,float('nan'),float('inf'),86401,'418.37 PRIVATE'])
def test_reconnect_delay_accepts_only_bounded_numeric_sdk_argument(delay):
    item = notice(library_handshake_record(delay=delay))
    assert 'retry_delay_seconds' not in item.description
    assert 'reconnect_scheduled' not in item.description


def test_no_arbitrary_library_template_or_arguments_are_interpolated():
    row = library_handshake_record()
    row.msg = 'PRIVATE url=%s password=%s'
    row.args = ('https://PRIVATE.invalid','PRIVATE')
    item = notice(row)
    assert 'retry_delay_seconds' not in item.description
    assert 'PRIVATE' not in item.description


def test_correlation_is_safe_and_does_not_defeat_grouping():
    row = record(logging.ERROR, fields={'event':'music.work_failed','error_code':'internal',
                                      'correlation_id':'a'*32})
    first = notice(row)
    row.fields['correlation_id'] = 'b'*32
    second = notice(row)
    assert first.dedup_key == second.dedup_key
    assert 'a'*32 in first.description and 'b'*32 in second.description
    row.fields['correlation_id'] = 'PRIVATE user path'
    assert 'Correlation: 미제공' in notice(row).description


def test_untrusted_project_module_and_trace_fields_do_not_escape():
    row = record(logging.ERROR, name='discordbot.PRIVATE_user', fields={
        'stack_frames':['discordbot/platform/PRIVATE_user.py:1'],
        'exception_chain':['RuntimeError','PRIVATE_type'],
        'event':'music.work_failed','error_code':'internal'})
    content = notice(row).description
    assert 'Module: discordbot\n' in content
    assert 'PRIVATE' not in content


def test_string_subclass_cannot_pass_allowlist_then_format_private_payload():
    class Injected(str):
        def __str__(self):return 'PRIVATE token=PRIVATE'
        def __format__(self, spec):return 'PRIVATE token=PRIVATE'
    fields = {'event':Injected('music.work_failed'),'error_code':Injected('internal'),
              'stage':Injected('connect'),'work_id':Injected('a'*32),
              'sqlite_family':Injected('busy'),'exception_type':Injected('RuntimeError')}
    content = notice(record(logging.ERROR,fields=fields)).description
    assert 'PRIVATE' not in content and 'Code: unspecified' in content


def test_rich_detail_is_clipped_after_core_identity_with_explicit_marker():
    from discordbot.operations.adapters.discord_logging import _bounded_block
    core = ['Event: database.probe_contention','Code: database_unavailable','Correlation: '+'a'*32]
    content = _bounded_block(core, ['safe detail: '+'🧪'*700]*5)
    assert len(content.encode('utf-16-le'))//2 <= 2000
    assert content.startswith('```text\n') and content.endswith('\n```')
    assert content.count('```') == 2
    for value in core:assert value in content
    assert '상세 일부 생략' in content


def test_maximal_rich_notice_retains_core_and_stays_within_discord_limit():
    from discordbot.platform.diagnostics import EXCEPTION_TYPES
    from discordbot.storage.adapters.probe_diagnostics import STAGES, CONFIGURE_STEPS, FAMILIES
    fields = dict(event='database.probe_contention', error_code='database_unavailable',
                  stage=max(STAGES,key=len), configure_step=max(CONFIGURE_STEPS,key=len),
                  exception_family=max(FAMILIES,key=len), sqlite_family='constraint', errno_category='capacity',
                  sqlite_errorcode=0xFFFFFF, connection_opened=False, close_succeeded=False, cleanup_failed=False,
                  exception_type=max(EXCEPTION_TYPES,key=len), cause_type=max(EXCEPTION_TYPES,key=len),
                  state_before='tts_starting',state_after='tts_starting',probe_disposition='recovery_expired',
                  reason='executable_not_found',voice_connected=False,probe_recovery_safe=False,
                  healthy_probes=100000,read_admitted=100000,write_admitted=100000,child_exit_code=-255,
                  http_status=503,work_id='b'*32,incident_id='c'*32,correlation_id='a'*32,
                  stack_frames=['discordbot/operations/adapters/discord_logging.py:1234567']*5,
                  exception_chain=[max(EXCEPTION_TYPES,key=len)]*3,trace_limited=True)
    content = notice(record(logging.ERROR,fields=fields)).description
    assert len(content.encode('utf-16-le'))//2 <= 2000
    assert content.startswith('```text\n') and content.endswith('\n```')
    assert content.count('```') == 2
    for core in ['Event: database.probe_contention','Code: database_unavailable','Correlation: '+'a'*32]:
        assert core in content


def test_watch_relay_revalidates_and_preserves_only_safe_evidence():
    from discordbot.operations.adapters.watch_diagnostics import _record
    row = dict(event='watch.shutdown',result='deadline',exception_type='TimeoutError',
               stack_frames=['discordbot/watch/application/service.py:219'],
               context_type='KeyError',exception_chain=['TimeoutError','KeyError','unexpected'],
               chain_relations=['context','cause'],correlation_id='a'*32,
               http_status=503,token='PRIVATE',message='PRIVATE')
    relayed = _record(row)
    assert relayed.fields['stack_frames'] == tuple(row['stack_frames'])
    assert relayed.fields['correlation_id'] == 'a'*32
    assert relayed.fields['context_type'] == 'KeyError'
    assert relayed.fields['chain_relations'] == ('context','cause')
    assert '--context--> KeyError --cause--> unexpected' in notice(relayed).description
    row['stack_frames'] = ['C:/Users/PRIVATE/script.py:1']
    row['exception_chain'] = ['PRIVATE_type']
    row['context_type'] = 'PRIVATE_type'
    row['chain_relations'] = ['PRIVATE_relation']
    relayed = _record(row)
    assert 'stack_frames' not in relayed.fields and 'exception_chain' not in relayed.fields
    assert 'context_type' not in relayed.fields and 'chain_relations' not in relayed.fields
    assert 'PRIVATE' not in notice(relayed).description
