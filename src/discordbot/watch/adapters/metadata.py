"""Fixed-origin oEmbed adapter: two calls, four waiters, five seconds, no retries."""

import asyncio
import re
from typing import Any

from discordbot.platform.errors import CapacityError, ExternalTemporaryError, ShutdownError, ValidationError
from discordbot.watch.adapters.wire import decode


class OEmbed:
    def __init__(self, session: Any = None) -> None:
        self.session = session
        self._owned = session is None
        self._slots = asyncio.Semaphore(2)
        self._admitted = 0

    async def start(self) -> None:
        if self.session is None:
            import aiohttp
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5),
                connector=aiohttp.TCPConnector(limit=2), trust_env=False)

    async def title(self, video_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValidationError("invalid metadata identity")
        if self.session is None:
            raise ShutdownError("metadata adapter not started")
        if self._admitted >= 6:
            raise CapacityError("metadata capacity")
        self._admitted += 1
        try:
            async with asyncio.timeout(5), self._slots:
                async with self.session.get("https://www.youtube.com/oembed",
                        params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                        allow_redirects=False) as response:
                    if response.status != 200:
                        raise ExternalTemporaryError("metadata response failed")
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        if len(raw)+len(chunk) > 65536:
                            raise ExternalTemporaryError("metadata response limit")
                        raw.extend(chunk)
                    title = decode(bytes(raw)).get("title")
                    if not isinstance(title, str):
                        raise ExternalTemporaryError("metadata title missing")
                    return title.strip()[:200] or "알 수 없는 유튜브 비디오"
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ExternalTemporaryError("metadata unavailable") from None
        finally:
            self._admitted -= 1

    async def close(self) -> None:
        if self.session is not None and self._owned:
            await self.session.close()
        self.session = None
