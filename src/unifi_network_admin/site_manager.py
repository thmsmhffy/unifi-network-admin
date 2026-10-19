"""Minimal Site Manager inventory used to select a remote console."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import InvalidResponse
from .transport import ReadOnlyTransport

SITE_MANAGER_ORIGIN = "https://api.ui.com"
MAX_HOSTS = 1_000
MAX_HOST_PAGES = 100


class SiteManagerClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._transport = ReadOnlyTransport(
            api_key=api_key,
            allowed_origins={SITE_MANAGER_ORIGIN},
            timeout_seconds=20,
            transport=transport,
        )

    async def __aenter__(self) -> SiteManagerClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._transport.close()

    async def list_hosts(self) -> list[dict[str, Any]]:
        hosts: list[dict[str, Any]] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()
        page_count = 0
        while True:
            page_count += 1
            if page_count > MAX_HOST_PAGES:
                raise InvalidResponse("Site Manager host pagination exceeded the safety limit")
            params: dict[str, str | int] = {"pageSize": 100}
            if next_token:
                params["nextToken"] = next_token
            payload = await self._transport.request_json(
                "GET",
                f"{SITE_MANAGER_ORIGIN}/v1/hosts",
                operation="list Site Manager hosts",
                params=params,
            )
            data = payload.get("data")
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise InvalidResponse("Site Manager returned an invalid host page")
            hosts.extend(data)
            if len(hosts) > MAX_HOSTS:
                raise InvalidResponse("Site Manager host inventory exceeded the safety limit")
            token_value = payload.get("nextToken")
            if not token_value:
                break
            next_token = str(token_value)
            if next_token in seen_tokens:
                raise InvalidResponse("Site Manager repeated a host pagination token")
            seen_tokens.add(next_token)
        return hosts
