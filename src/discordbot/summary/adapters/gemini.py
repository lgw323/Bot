"""Cancellable Gemini REST boundary. No client, environment read or network at import."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from discordbot.platform.errors import (ConfigurationError, DeadlineExceededError,
    ExternalPermanentError, ExternalTemporaryError)
from discordbot.summary.domain.models import MalformedSummary, Prompt, Summary, Topic


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-flash-latest", *, session: Any = None) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", model):
            raise ConfigurationError("invalid Gemini configuration")
        self._api_key, self._model, self._session = api_key, model, session

    async def start(self) -> None:
        if not self._api_key:
            raise ConfigurationError("Gemini key required when enabled")
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()

    async def generate(self, prompt: Prompt, *, remaining: float) -> Summary:
        import aiohttp

        if remaining <= 0:
            raise DeadlineExceededError("Gemini budget exhausted")
        if self._session is None:
            raise ConfigurationError("Gemini not started")
        try:
            # No SDK hidden retry/background work; TLS endpoint is fixed and the
            # key is in a header, never a query string or diagnostic field.
            async with self._session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json={"systemInstruction": {"parts": [{"text": prompt.instruction}]},
                      "contents": [{"role": "user", "parts": [{"text": prompt.data}]}],
                      "generationConfig": {"responseMimeType": "application/json",
                          "maxOutputTokens": 25000, "temperature": 0.5},
                      "safetySettings": [{"category": category, "threshold": "BLOCK_NONE"}
                          for category in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                              "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]},
                timeout=aiohttp.ClientTimeout(total=min(60, remaining), connect=min(10, remaining),
                                               sock_read=min(30, remaining)),
                allow_redirects=False,
            ) as response:
                if response.status == 429 or 500 <= response.status <= 599:
                    raise ExternalTemporaryError("Gemini temporarily unavailable")
                if response.status != 200:
                    raise ExternalPermanentError("Gemini rejected request")
                data = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    data.extend(chunk)
                    if len(data) > 512_000:
                        raise MalformedSummary("Gemini response too large")
                return self.parse(bytes(data))
        except (ExternalTemporaryError, ExternalPermanentError, MalformedSummary):
            raise
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
            raise DeadlineExceededError("Gemini call deadline") from None
        except (aiohttp.ClientError, OSError):
            raise ExternalTemporaryError("Gemini transport failed") from None
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ExternalPermanentError("Gemini request failed") from None

    @staticmethod
    def parse(raw: bytes) -> Summary:
        try:
            body = json.loads(raw)
            candidate = body["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("incomplete result")
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
            value = json.loads(text)
            result = Summary(value["overall"], tuple(Topic(**topic) for topic in value["topics"]),
                             body.get("usageMetadata", {}).get("promptTokenCount", 0))
            result.validate()
            return result
        except Exception:
            raise MalformedSummary("invalid Gemini result") from None

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            await session.close()
