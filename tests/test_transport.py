from __future__ import annotations

import httpx
import pytest

from unifi_network_admin.errors import (
    AuthenticationFailed,
    ConfigurationError,
    InvalidResponse,
    PermissionDenied,
    RateLimited,
    ReadOnlyViolation,
    ResourceNotFound,
)
from unifi_network_admin.transport import ReadOnlyTransport


@pytest.mark.anyio
async def test_write_is_blocked_before_transport_receives_request() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    transport = ReadOnlyTransport(
        api_key="secret",
        allowed_origins={"https://console.test"},
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ReadOnlyViolation):
        await transport.request_json(
            "POST", "https://console.test/v1/sites", operation="mutate"
        )
    assert calls == 0
    await transport.close()


@pytest.mark.anyio
async def test_request_cannot_leave_profile_origin() -> None:
    transport = ReadOnlyTransport(api_key="secret", allowed_origins={"https://console.test"})
    with pytest.raises(ConfigurationError):
        await transport.request_json(
            "GET", "https://other.test/v1/info", operation="get info"
        )
    await transport.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationFailed),
        (403, PermissionDenied),
        (404, ResourceNotFound),
        (429, RateLimited),
    ],
)
async def test_http_errors_are_typed_and_do_not_include_key(status, error) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "super-secret"
        return httpx.Response(status, headers={"Retry-After": "2"})

    transport = ReadOnlyTransport(
        api_key="super-secret",
        allowed_origins={"https://console.test"},
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(error) as caught:
        await transport.request_json(
            "GET", "https://console.test/v1/info", operation="get info"
        )
    assert "super-secret" not in str(caught.value)
    await transport.close()


@pytest.mark.anyio
async def test_response_size_is_bounded() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"value":"too large"}')

    transport = ReadOnlyTransport(
        api_key="secret",
        allowed_origins={"https://console.test"},
        max_response_bytes=8,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(InvalidResponse):
        await transport.request_json(
            "GET", "https://console.test/v1/info", operation="get info"
        )
    await transport.close()


@pytest.mark.anyio
async def test_bounded_rate_limit_retry_honors_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2.5"})
        return httpx.Response(200, json={"ok": True})

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    transport = ReadOnlyTransport(
        api_key="secret",
        allowed_origins={"https://console.test"},
        max_rate_limit_retries=2,
        sleep=fake_sleep,
        transport=httpx.MockTransport(handler),
    )
    result = await transport.request_json(
        "GET", "https://console.test/v1/info", operation="get info"
    )

    assert result == {"ok": True}
    assert calls == 2
    assert delays == [2.5]
    await transport.close()
