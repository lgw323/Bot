"""Safe exception evidence: fixed categories and public code positions, never payloads."""
from __future__ import annotations

from pathlib import Path
import re
import sys
from types import TracebackType
from collections.abc import Mapping

from discordbot.platform.diagnostic_locations import PUBLIC_FRAME_PATHS

EXCEPTION_TYPES = frozenset('''AppError ValidationError AuthorizationError NotFoundError
ConflictError CapacityError ExternalTemporaryError ExternalPermanentError
DatabaseUnavailableError DataIntegrityError InternalError ConfigurationError
CancellationError DeadlineExceededError DatabaseDeadlineError StartupError ShutdownError
TimeoutError ConnectionError ConnectionResetError ConnectionRefusedError BrokenPipeError
OSError PermissionError FileNotFoundError RuntimeError ValueError TypeError AttributeError
KeyError IndexError AssertionError HTTPException Forbidden NotFound ClientException
ConnectionClosed InvalidData OpusError OpusNotLoaded UnavailableTrack PremiumOnly
ClientConnectionError ClientConnectorError ClientResponseError WSServerHandshakeError
ServerTimeoutError SocketTimeoutError ConnectionTimeoutError ServerDisconnectedError gaierror'''.split())
HTTP_EXCEPTIONS = frozenset({'HTTPException', 'Forbidden', 'NotFound', 'ClientResponseError', 'WSServerHandshakeError'})
MAX_CHAIN = 3
MAX_FRAMES = 5
_LOCATION = re.compile(r'([A-Za-z_][A-Za-z_0-9/]*\.py):([1-9][0-9]{0,6})')
_CORRELATION = re.compile(r'(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})')


def safe_frame_location(value: object) -> str | None:
    """Only an exact published path plus a bounded positive line may cross sinks."""
    if type(value) is not str or len(value) > 160:
        return None
    match = _LOCATION.fullmatch(value)
    return value if match and match[1] in PUBLIC_FRAME_PATHS else None


def safe_exception_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Revalidate evidence on receipt as well as when exceptions are captured."""
    safe: dict[str, object] = {}
    for key in ('exception_type', 'cause_type', 'context_type'):
        value = fields.get(key)
        if type(value) is str and value in EXCEPTION_TYPES | {'unexpected'}:
            safe[key] = value
    value = fields.get('exception_chain')
    if type(value) in (tuple, list) and 1 <= len(value) <= MAX_CHAIN and all(
            type(item) is str and item in EXCEPTION_TYPES | {'unexpected'} for item in value):
        safe['exception_chain'] = tuple(value)
    value = fields.get('chain_relations')
    chain = safe.get('exception_chain', ())
    if type(value) in (tuple, list) and 1 <= len(value) == len(chain) - 1 and all(
            type(item) is str and item in {'cause', 'context'} for item in value):
        safe['chain_relations'] = tuple(value)
    value = fields.get('stack_frames')
    if type(value) in (tuple, list) and 1 <= len(value) <= MAX_FRAMES and all(
            safe_frame_location(item) is not None for item in value):
        safe['stack_frames'] = tuple(value)
    if fields.get('trace_limited') is True:
        safe['trace_limited'] = True
    value = fields.get('correlation_id')
    if type(value) is str and _CORRELATION.fullmatch(value):
        safe['correlation_id'] = value
    value = fields.get('http_status')
    if type(value) is int and 100 <= value <= 599:
        safe['http_status'] = value
    return safe


def _exception_name(error: BaseException) -> str:
    name = type.__getattribute__(type(error), '__name__')
    return name if name in EXCEPTION_TYPES else 'unexpected'


def _frame_location(tb: TracebackType) -> str | None:
    """Resolve against a loaded, published module; do not read source or locals."""
    globals_ = tb.tb_frame.f_globals
    name = globals_.get('__name__')
    if type(name) is not str:
        return None
    module = sys.modules.get(name)
    if module is None or vars(module) is not globals_:
        return None
    package = name.partition('.')[0]
    root_module = sys.modules.get(package)
    origin = vars(module).get('__file__')
    root_origin = vars(root_module).get('__file__') if root_module is not None else None
    if type(origin) is not str or type(root_origin) is not str:
        return None
    try:
        filename = Path(tb.tb_frame.f_code.co_filename).resolve()
        if filename != Path(origin).resolve():
            return None
        relative = filename.relative_to(Path(root_origin).resolve().parent)
    except (OSError, ValueError):
        return None
    location = package + '/' + relative.as_posix() + ':' + str(tb.tb_lineno)
    return safe_frame_location(location)


def exception_fields(error: BaseException) -> dict[str, object]:
    """Capture up to three causal types and five public frames; raw text is never read.

    Explicit cause wins over implicit context. ``raise ... from None`` keeps its
    suppressed context private. Cycles/deeper chains and unpublished frames are
    marked partial rather than presented as a complete explanation.
    """
    fields: dict[str, object] = {'exception_type': _exception_name(error)}
    chain: list[str] = []
    links: list[str] = []
    frames: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    limited = False
    while current is not None and len(chain) < MAX_CHAIN:
        if id(current) in seen:
            limited = True
            break
        seen.add(id(current))
        name = _exception_name(current)
        chain.append(name)
        try:
            status = getattr(current, 'status', None) if name in HTTP_EXCEPTIONS else None
            if 'http_status' not in fields and type(status) is int and 100 <= status <= 599:
                fields['http_status'] = status
            tb = current.__traceback__
            scanned = 0
            while tb is not None and scanned < 64:
                location = _frame_location(tb)
                if location is not None:
                    frames.append(location)
                else:
                    limited = True
                scanned += 1
                tb = tb.tb_next
            limited = limited or tb is not None
            cause = current.__cause__
            relation = 'cause'
            if cause is None and not current.__suppress_context__:
                cause = current.__context__
                relation = 'context'
            if cause is not None:
                links.append(relation)
            current = cause
        except Exception:
            # Optional evidence must not replace the caller's original error.
            limited = True
            break
    limited = limited or current is not None or len(frames) > MAX_FRAMES
    if len(chain) > 1:
        fields['cause_type' if links[0] == 'cause' else 'context_type'] = chain[1]
    if len(chain) > 2:
        fields['exception_chain'] = tuple(chain)
        fields['chain_relations'] = tuple(links[:len(chain)-1])
    if frames:
        fields['stack_frames'] = tuple(frames[-MAX_FRAMES:])
    if limited:
        fields['trace_limited'] = True
    return fields
