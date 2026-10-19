from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from unifi_network_admin.errors import InvalidResponse
from unifi_network_admin.site_manager import SiteManagerClient


@pytest.mark.anyio
async def test_site_manager_follows_opaque_next_tokens() -> None:
    seen_tokens: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        token = query.get("nextToken", [None])[0]
        seen_tokens.append(token)
        if token is None:
            return httpx.Response(
                200,
                json={"data": [{"id": "host-1"}], "nextToken": "opaque:token"},
            )
        return httpx.Response(200, json={"data": [{"id": "host-2"}]})

    async with SiteManagerClient("secret", transport=httpx.MockTransport(handler)) as client:
        hosts = await client.list_hosts()

    assert [host["id"] for host in hosts] == ["host-1", "host-2"]
    assert seen_tokens == [None, "opaque:token"]


@pytest.mark.anyio
async def test_site_manager_rejects_repeated_next_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [], "nextToken": "same-token"})

    async with SiteManagerClient("secret", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(InvalidResponse, match="repeated"):
            await client.list_hosts()
