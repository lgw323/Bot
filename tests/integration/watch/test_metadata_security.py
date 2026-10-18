import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

import pytest

from discordbot.platform.errors import AuthorizationError, CapacityError, ConfigurationError, ExternalTemporaryError
from discordbot.watch.adapters.control_schema import response_data
from discordbot.watch.adapters.metadata import OEmbed
from discordbot.watch.adapters.security import Capabilities, LoopbackAuth, loopback_url
from discordbot.watch.domain.policy import ProtocolFailure, RateLimited, protocol


class Provider:
    def __init__(self, body=b'{"title":"synthetic"}', status=200, gate=None, fail=None):
        self.body, self.status, self.gate, self.fail = body, status, gate, fail
        self.active = self.peak = self.calls = 0
        self.entered = asyncio.Event()

    @asynccontextmanager
    async def get(self, url, params, allow_redirects):
        assert url == "https://www.youtube.com/oembed" and not allow_redirects
        assert params["url"] == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
        self.active += 1
        self.calls += 1
        self.peak = max(self.peak, self.active)
        if self.active == 2:
            self.entered.set()
        try:
            if self.gate:
                await self.gate.wait()
            if self.fail:
                raise self.fail
            async def chunks(size):
                for offset in range(0, len(self.body), size):
                    yield self.body[offset:offset+size]
            yield SimpleNamespace(status=self.status, content=SimpleNamespace(iter_chunked=chunks))
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_oembed_two_active_four_waiters_and_cancellation_release():
    provider = Provider(gate=asyncio.Event())
    adapter = OEmbed(provider)
    tasks = [asyncio.create_task(adapter.title("aaaaaaaaaaa")) for _ in range(6)]
    try:
        await asyncio.wait_for(provider.entered.wait(), 2)
        with pytest.raises(CapacityError):
            await adapter.title("aaaaaaaaaaa")
        assert provider.peak == 2 and adapter._admitted == 6
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await adapter.close()
    assert not provider.active and not adapter._admitted


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [Provider(status=500), Provider(body=b"x"*65537), Provider(body=b"{bad"),
    Provider(body=b'{"title":4}'), Provider(fail=TimeoutError("secret=hidden"))])
async def test_oembed_safe_failure_no_retry(provider):
    adapter = OEmbed(provider)
    with pytest.raises(ExternalTemporaryError) as error:
        await adapter.title("aaaaaaaaaaa")
    assert "hidden" not in str(error.value) and provider.calls == 1
    await adapter.close()


@pytest.mark.asyncio
async def test_oembed_failure_preserves_fallback_playlist_title(service, invite):
    service.metadata = OEmbed(Provider(status=500))
    assert await service.add(invite.capability, "https://youtu.be/aaaaaaaaaaa", "A") == "알 수 없는 유튜브 비디오"
    assert (await service.resolve(invite.capability).call("playlist"))[0].video_title == "알 수 없는 유튜브 비디오"


@pytest.mark.parametrize("url", ["https://127.0.0.1:9001", "http://localhost:9001", "http://example.test:9001", "http://127.0.0.1:9001/private", "http://u:p@127.0.0.1:9001"])
def test_control_client_rejects_non_literal_loopback_or_ambiguous_url(url):
    with pytest.raises(ConfigurationError):
        loopback_url(url)


@pytest.mark.parametrize("change", ["host", "time", "signature", "body"])
def test_loopback_authentication_fail_closed(change):
    auth = LoopbackAuth("synthetic-auth-secret-32-characters")
    path, body, stamp, nonce = "/internal/watch/status", b"{}", "1000", "a"*32
    signature = auth.signature(path, body, stamp, nonce)
    with pytest.raises(AuthorizationError):
        auth.verify("192.0.2.1" if change == "host" else "127.0.0.1", path,
            b"changed" if change == "body" else body, "900" if change == "time" else stamp,
            nonce, "b"*64 if change == "signature" else signature, 1000)


def test_capabilities_are_session_specific_and_old_operation_time_never_reuses_token():
    cap = Capabilities("synthetic-capability-secret-32-characters")
    tokens = [cap.mint(g, u, op, stamp)[0] for g,u,op,stamp in
        [(100,42,"one",1000), (200,42,"one",1000), (100,43,"one",1000), (100,42,"two",1000), (100,42,"one",2000)]]
    assert len(set(tokens)) == 5 and all(len(token) == 43 for token in tokens)


@pytest.mark.parametrize("value", [{"type":"state_change","time":1,"state":[]}, {"type":"seek","time":float("nan")},
    {"type":"chat","text":"x"*501}, {"type":"join","username":3}, {"type":"sync_request","extra":True}])
def test_protocol_untrusted_shapes_are_typed(value):
    with pytest.raises(ProtocolFailure):
        protocol(value)


def test_control_response_schema_rejects_malformed_or_injected_payload():
    for operation, value in [("status", {"ready": "yes"}), ("create", {"capability": "<script>"}),
        ("cleanup", {"items": [{"channel": "secret"}]}), ("close", {"unexpected": True})]:
        with pytest.raises(ExternalTemporaryError):
            response_data(operation, value)
