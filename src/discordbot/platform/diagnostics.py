"""Exception categories only: never materialize messages, arguments or locals."""
from __future__ import annotations

EXCEPTION_TYPES = frozenset('''AppError ValidationError AuthorizationError NotFoundError
ConflictError CapacityError ExternalTemporaryError ExternalPermanentError
DatabaseUnavailableError DataIntegrityError InternalError ConfigurationError
CancellationError DeadlineExceededError DatabaseDeadlineError StartupError ShutdownError
TimeoutError ConnectionError ConnectionResetError ConnectionRefusedError BrokenPipeError
OSError PermissionError FileNotFoundError RuntimeError ValueError TypeError AttributeError
KeyError IndexError AssertionError HTTPException Forbidden NotFound ClientException
ConnectionClosed InvalidData OpusError OpusNotLoaded UnavailableTrack PremiumOnly'''.split())


def exception_fields(error: Exception) -> dict[str, str]:
    """Unknown/dynamically named exceptions stay opaque, even with private names."""
    name = type(error).__name__
    fields = {'exception_type': name if name in EXCEPTION_TYPES else 'unexpected'}
    cause = error.__cause__
    if cause is not None:
        name = type(cause).__name__
        fields['cause_type'] = name if name in EXCEPTION_TYPES else 'unexpected'
    return fields
