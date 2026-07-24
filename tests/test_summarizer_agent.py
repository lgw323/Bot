from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.summary import summarizer_agent


def test_initialize_gemini_client_uses_supported_sdk() -> None:
    client = MagicMock()

    with patch.object(
        summarizer_agent.genai,
        "Client",
        return_value=client,
    ) as client_factory:
        summarizer_agent.initialize_gemini_client("test-api-key")

    client_factory.assert_called_once_with(api_key="test-api-key")
    assert summarizer_agent.gemini_client is client


@pytest.mark.asyncio
async def test_gemini_summary_uses_async_supported_sdk() -> None:
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock()
    client.aio.models.generate_content.return_value.text = "요약 결과"
    summarizer_agent.gemini_client = client

    try:
        result, token_count = await summarizer_agent.gemini_summarize(
            [
                (
                    datetime.now(timezone.utc),
                    1,
                    2,
                    "친구",
                    "오늘 같이 게임하자",
                )
            ]
        )
    finally:
        summarizer_agent.gemini_client = None

    assert result == "요약 결과"
    assert token_count > 0
    client.aio.models.generate_content.assert_awaited_once()
    request = client.aio.models.generate_content.call_args.kwargs
    assert request["model"] == summarizer_agent.GEMINI_MODEL
    assert request["contents"]
    assert request["config"].max_output_tokens == (
        summarizer_agent.MAX_RESPONSE_TOKENS
    )


@pytest.mark.asyncio
async def test_close_gemini_client_releases_async_resources() -> None:
    client = MagicMock()
    client.aio.aclose = AsyncMock()
    summarizer_agent.gemini_client = client

    await summarizer_agent.close_gemini_client()

    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()
    assert summarizer_agent.gemini_client is None
