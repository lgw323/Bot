"""Synthetic exception faults; never use real services, paths, messages or credentials."""
import sys

import pytest

from discordbot.platform import diagnostics as module
from discordbot.platform.diagnostics import exception_fields, safe_exception_fields, safe_frame_location


def raised_in_public_module(error, *, depth=0):
    """Execute synthetic code in a real public module without modifying a file."""
    namespace = module.__dict__
    names = ('_diagnostic_fixture_error', '_diagnostic_fixture_depth', '_PRIVATE_payload_function')
    assert all(name not in namespace for name in names)
    namespace['_diagnostic_fixture_error'] = error
    namespace['_diagnostic_fixture_depth'] = depth
    source = ('def _PRIVATE_payload_function(n):\n'
              '    if n: return _PRIVATE_payload_function(n-1)\n'
              '    raise _diagnostic_fixture_error\n'
              '_PRIVATE_payload_function(_diagnostic_fixture_depth)\n')
    try:
        exec(compile(source, module.__file__, 'exec'), namespace)
    except BaseException as caught:
        return caught
    finally:
        for name in names:
            namespace.pop(name, None)


def test_public_locations_without_source_function_locals_or_absolute_path():
    error = raised_in_public_module(RuntimeError('PRIVATE message token=PRIVATE'))
    fields = exception_fields(error)
    assert fields['exception_type'] == 'RuntimeError'
    assert fields['stack_frames']
    assert all(row.startswith('discordbot/platform/diagnostics.py:') for row in fields['stack_frames'])
    rendered = repr(fields)
    for private in ('PRIVATE', '_diagnostic_fixture', 'Users', '/home/', 'token=', str(module.__file__)):
        assert private not in rendered


def test_deep_stack_is_bounded_and_marks_missing_private_frames():
    fields = exception_fields(raised_in_public_module(RuntimeError('PRIVATE'), depth=100))
    assert len(fields['stack_frames']) == 5
    assert fields['trace_limited'] is True


def test_explicit_cause_wins_and_suppressed_context_stays_hidden():
    outer, explicit, context = RuntimeError('PRIVATE'), TimeoutError('PRIVATE'), KeyError('PRIVATE')
    outer.__cause__ = explicit
    outer.__context__ = context
    assert exception_fields(outer)['cause_type'] == 'TimeoutError'
    outer.__cause__ = None
    outer.__suppress_context__ = False
    assert exception_fields(outer)['cause_type'] == 'KeyError'
    outer.__suppress_context__ = True
    assert 'cause_type' not in exception_fields(outer)


def test_deep_cause_chain_and_cycle_do_not_recurse_or_expose_messages():
    errors = [RuntimeError('PRIVATE') for _ in range(20)]
    for a, b in zip(errors, errors[1:]):a.__cause__ = b
    fields = exception_fields(errors[0])
    assert fields['exception_chain'] == ('RuntimeError',) * 3
    assert fields['trace_limited'] is True
    errors[0].__cause__ = errors[0]
    assert exception_fields(errors[0]) == {'exception_type':'RuntimeError','trace_limited':True}


def test_unknown_dynamic_type_and_message_stay_opaque():
    class MessageMustNeverBeRead(Exception):
        def __str__(self):raise AssertionError('message accessed')
    fields = exception_fields(raised_in_public_module(MessageMustNeverBeRead('PRIVATE')))
    assert fields['exception_type'] == 'unexpected'
    assert 'MessageMustNeverBeRead' not in repr(fields)
    assert 'PRIVATE' not in repr(fields)


@pytest.mark.parametrize('field,value', [
    ('exception_chain', ['RuntimeError','PRIVATE_payload']),
    ('exception_chain', ['RuntimeError'] * 4),
    ('stack_frames', ['discordbot/platform/PRIVATE_user.py:12']),
    ('stack_frames', ['PRIVATE/vendor/client.py:781']),
    ('stack_frames', ['discordbot/../../home/PRIVATE.py:1']),
    ('stack_frames', ['C:/Users/PRIVATE/client.py:781']),
    ('stack_frames', ['discord/client.py:0']),
    ('stack_frames', ['discord/client.py:10000000']),
    ('stack_frames', ['discord/client.py:1'] * 6),
    ('stack_frames', ['discord/client.py:1\n```PRIVATE']),
    ('correlation_id', 'PRIVATE user 123456789012345678'),
    ('correlation_id', '123456789012345678'),
    ('http_status', True), ('http_status', 600),
])
def test_incoming_evidence_is_revalidated(field, value):
    assert field not in safe_exception_fields({field:value})


def test_valid_evidence_survives_json_list_and_tuple_boundaries():
    fields = dict(exception_type='WSServerHandshakeError', cause_type='TimeoutError',
                  exception_chain=['WSServerHandshakeError','TimeoutError','unexpected'],
                  stack_frames=['discord/client.py:781','aiohttp/client.py:100'],
                  correlation_id='a'*32, http_status=503, trace_limited=True)
    assert safe_exception_fields(fields) == {**fields,'exception_chain':tuple(fields['exception_chain']),
                                             'stack_frames':tuple(fields['stack_frames'])}
    assert safe_frame_location('unknown_package/private.py:1') is None


def test_forged_module_globals_cannot_turn_a_private_frame_into_public_evidence():
    namespace = {'__name__':'discordbot.platform.diagnostics','__file__':module.__file__}
    try:exec(compile('raise RuntimeError("PRIVATE")', module.__file__, 'exec'), namespace)
    except RuntimeError as error:fields = exception_fields(error)
    assert 'stack_frames' not in fields
    assert fields['trace_limited'] is True
