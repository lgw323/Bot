import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from discordbot.summary.adapters.gemini import GeminiProvider


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError, TimeoutError, asyncio.CancelledError])
async def test_transport_close_failure_keeps_session_for_retry(error):
    session = SimpleNamespace(close=AsyncMock(side_effect=[error('synthetic'), None]))
    provider = GeminiProvider('SYNTHETIC', session=session)
    with pytest.raises(error):
        await provider.close()
    assert provider._session is session
    await provider.close()
    await provider.close()
    assert session.close.await_count == 2 and provider._session is None
