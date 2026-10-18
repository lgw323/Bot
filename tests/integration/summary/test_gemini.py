import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from discordbot.platform.errors import DeadlineExceededError, ExternalPermanentError, ExternalTemporaryError
from discordbot.summary.adapters.gemini import GeminiProvider
from discordbot.summary.domain.models import MalformedSummary, Prompt


def response_body(value=None, finish="STOP"):
    return json.dumps({"candidates": [{"finishReason": finish, "content": {"parts": [{"text": json.dumps(
        value if value is not None else {"overall": "합성 요약", "topics": [{"title": "합성 주제"}]})}]}}],
        "usageMetadata": {"promptTokenCount": 12}}).encode()


class Response:
    def __init__(self, status=200, raw=None):
        self.status, self.raw = status, response_body() if raw is None else raw
        self.content = self
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def iter_chunked(self, size):
        for start in range(0, len(self.raw), size):
            yield self.raw[start:start+size]


@pytest.mark.asyncio
async def test_rest_boundary_structure_remaining_budget_and_close():
    response = Response()
    session = SimpleNamespace(post=MagicMock(return_value=response), close=AsyncMock())
    provider = GeminiProvider("SYNTHETIC_SECRET", session=session)
    result = await provider.generate(Prompt("APP instructions", '{"messages": "untrusted"}'), remaining=17.5)
    assert result.overall == "합성 요약" and result.input_tokens == 12
    args, kwargs = session.post.call_args
    assert "SYNTHETIC_SECRET" not in args[0]
    assert kwargs["headers"] == {"x-goog-api-key": "SYNTHETIC_SECRET"}
    assert kwargs["timeout"].total == 17.5
    assert kwargs["timeout"].connect == 10
    assert kwargs["timeout"].sock_read == 17.5
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "APP instructions"
    assert kwargs["json"]["contents"][0]["parts"][0]["text"] == '{"messages": "untrusted"}'
    assert kwargs["allow_redirects"] is False and response.closed
    await provider.close()
    await provider.close()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,error", [(429, ExternalTemporaryError), (503, ExternalTemporaryError),
    (400, ExternalPermanentError), (403, ExternalPermanentError), (302, ExternalPermanentError)])
async def test_http_typed_failure_does_not_read_or_log_body(status, error, caplog):
    response = Response(status, b"RAW PRIVATE token=SECRET")
    session = SimpleNamespace(post=MagicMock(return_value=response), close=AsyncMock())
    with pytest.raises(error) as raised:
        await GeminiProvider("SECRET", session=session).generate(Prompt("private", "private"), remaining=60)
    assert "SECRET" not in str(raised.value) + caplog.text
    reason = 'http_rate_limited' if status == 429 else 'http_server_error' if status >= 500 else 'http_rejected'
    assert dict(raised.value.context) == {'reason': reason, 'http_status': status}
    assert response.closed and session.post.call_count == 1


@pytest.mark.parametrize("raw", [b"not json SECRET", b"{}", response_body({}, "STOP"),
    response_body(finish="MAX_TOKENS"), response_body({"overall": "x", "topics": []}),
    response_body({"overall": "x", "topics": [{"title": "x"*201}]}),
    response_body({"overall": "x", "topics": [{"title": "x"}]*101})])
def test_malformed_output_is_typed_and_redacted(raw):
    with pytest.raises(MalformedSummary) as raised:
        GeminiProvider.parse(raw)
    assert "SECRET" not in str(raised.value)


@pytest.mark.asyncio
async def test_oversized_output_rejected_and_transport_cancelled():
    response = Response(raw=b"x"*512001)
    session = SimpleNamespace(post=MagicMock(return_value=response), close=AsyncMock())
    with pytest.raises(MalformedSummary):
        await GeminiProvider("SECRET", session=session).generate(Prompt("x", "x"), remaining=60)
    assert response.closed
    session.post.side_effect = TimeoutError("SECRET")
    with pytest.raises(DeadlineExceededError):
        await GeminiProvider("SECRET", session=session).generate(Prompt("x", "x"), remaining=60)
    session.post.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await GeminiProvider("SECRET", session=session).generate(Prompt("x", "x"), remaining=60)
