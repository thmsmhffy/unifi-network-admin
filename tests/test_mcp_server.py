from __future__ import annotations

import httpx
import pytest
from mcp import Client

from unifi_network_admin.config import Profile, ProfileStore
from unifi_network_admin.mcp_server import create_server


def api_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/v1/info"):
        return httpx.Response(200, json={"applicationVersion": "10.6.106"})
    if request.url.path.endswith("/v1/sites"):
        return httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 200,
                "count": 1,
                "totalCount": 1,
                "data": [{"id": "site-1", "name": "Main"}],
            },
        )
    return httpx.Response(
        200,
        json={"offset": 0, "limit": 1, "count": 0, "totalCount": 0, "data": []},
    )


@pytest.mark.anyio
async def test_mcp_exposes_only_typed_read_tools(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "profiles.json"
    ProfileStore(config_path).put(
        Profile(name="test", mode="local", url="https://console.test")
    )
    monkeypatch.setenv("UNIFI_API_KEY_TEST", "secret")
    server = create_server(
        profile_name="test",
        config_path=config_path,
        transport=httpx.MockTransport(api_handler),
    )

    async with Client(server, raise_exceptions=True) as client:
        tools = (await client.list_tools()).tools
        names = {tool.name for tool in tools}
        result = await client.call_tool("unifi_list_sites", {})

    assert "unifi_discover" in names
    assert "unifi_snapshot" in names
    assert result.is_error is False
    assert all(
        word not in name
        for name in names
        for word in ("apply", "create", "update", "delete", "raw_request")
    )
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools)
    assert all("profile" not in tool.input_schema.get("properties", {}) for tool in tools)
