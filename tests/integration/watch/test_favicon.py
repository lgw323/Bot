"""The player icon must stay self-contained and work under the existing CSP."""

from html.parser import HTMLParser
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import httpx
import pytest

from discordbot.watch.adapters.web import build_public_app


class IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "icon" in values.get("rel", "").split():
            self.icons.append(values)


@pytest.mark.asyncio
async def test_player_favicon_is_inline_svg_allowed_by_existing_csp(service, invite):
    origin = "https://watch.example.test"
    app = build_public_app(service, origin)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        page = await client.get("/watch", params={"session": invite.capability})

    assert page.status_code == 200
    links = IconLinks()
    links.feed(page.text)
    assert len(links.icons) == 1
    icon = links.icons[0]
    assert icon["type"] == "image/svg+xml"
    assert icon["href"].startswith("data:image/svg+xml,")
    svg = ET.fromstring(unquote(icon["href"].split(",", 1)[1]))
    ns = "{http://www.w3.org/2000/svg}"
    assert svg.tag == ns + "svg"
    assert svg.attrib["viewBox"] == "0 0 64 64"
    assert [child.tag for child in svg] == [ns + "rect", ns + "path", ns + "circle"]
    assert [child.attrib["fill"] for child in svg] == ["#1c1d21", "#f7f7f2", "#35c7b0"]
    assert all(not any(key.endswith("href") for key in node.attrib) for node in svg.iter())
    assert "img-src 'self' data:" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-store"
