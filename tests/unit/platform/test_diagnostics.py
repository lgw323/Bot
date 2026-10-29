from discordbot.platform.diagnostics import exception_fields


def test_exception_messages_and_dynamic_names_never_escape():
    hidden = type('private_payload_token', (Exception,), {})('private chat')
    error = RuntimeError('private token')
    error.__cause__ = hidden
    assert exception_fields(error) == {'exception_type': 'RuntimeError', 'cause_type': 'unexpected'}
    assert exception_fields(hidden) == {'exception_type': 'unexpected'}
