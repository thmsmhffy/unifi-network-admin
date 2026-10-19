"""A small HTTP boundary that cannot issue UniFi mutations."""

from __future__ import annotations

import asyncio
import json
import math
import os
import ssl
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import (
    ApiError,
    AuthenticationFailed,
    ConfigurationError,
    ConnectionFailed,
    InvalidResponse,
    PermissionDenied,
    RateLimited,
    ReadOnlyViolation,
    ResourceNotFound,
)

ALLOWED_METHODS = frozenset({"GET", "HEAD"})
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 60.0


def tls_verification(ca_bundle: Path | None, *, allow_insecure_tls: bool) -> bool | ssl.SSLContext:
    if allow_insecure_tls:
        return False
    if ca_bundle is None:
        return True
    if not ca_bundle.is_file() or not os.access(ca_bundle, os.R_OK):
        raise ConfigurationError(f"CA bundle is not a readable file: {ca_bundle}")
    return ssl.create_default_context(cafile=str(ca_bundle))


class ReadOnlyTransport:
    """Send bounded requests to fixed origins and reject writes before I/O."""

    def __init__(
        self,
        *,
        api_key: str,
        allowed_origins: set[str],
        timeout_seconds: float = 20.0,
        verify: bool | ssl.SSLContext = True,
        transport: httpx.AsyncBaseTransport | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_rate_limit_retries: int = 0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not 0 <= max_rate_limit_retries <= 5:
            raise ValueError("max_rate_limit_retries must be between 0 and 5")
        self._allowed_origins = allowed_origins
        self._max_response_bytes = max_response_bytes
        self._max_rate_limit_retries = max_rate_limit_retries
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "User-Agent": "unifi-network-admin/0.1",
                "X-API-Key": api_key,
            },
            timeout=timeout_seconds,
            verify=verify,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ReadOnlyTransport:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        params: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if method not in ALLOWED_METHODS:
            raise ReadOnlyViolation(f"HTTP {method} is blocked; this release is read-only")

        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme != "https" or origin not in self._allowed_origins:
            raise ConfigurationError("Request origin does not match the selected profile")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("Request URL contains forbidden components")

        for attempt in range(self._max_rate_limit_retries + 1):
            try:
                async with self._client.stream(method, url, params=params) as response:
                    self._raise_for_status(response, operation)
                    declared = response.headers.get("Content-Length")
                    if declared:
                        try:
                            too_large = int(declared) > self._max_response_bytes
                        except ValueError:
                            too_large = False
                        if too_large:
                            raise InvalidResponse(
                                "UniFi response exceeds the 10 MB safety limit"
                            )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_response_bytes:
                            raise InvalidResponse(
                                "UniFi response exceeds the 10 MB safety limit"
                            )
            except RateLimited as exc:
                if attempt >= self._max_rate_limit_retries:
                    raise
                await self._sleep(self._retry_delay(exc.retry_after))
                continue
            except httpx.RequestError as exc:
                raise ConnectionFailed(f"Cannot reach UniFi while running {operation}") from exc
            break

        if method == "HEAD" or not body:
            return {}
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidResponse(f"UniFi returned invalid JSON for {operation}") from exc
        if not isinstance(payload, dict):
            raise InvalidResponse(f"UniFi returned an unexpected JSON shape for {operation}")
        return payload

    @staticmethod
    def _retry_delay(retry_after: str | None) -> float:
        try:
            delay = float(retry_after) if retry_after is not None else MAX_RETRY_AFTER_SECONDS
        except ValueError:
            return MAX_RETRY_AFTER_SECONDS
        if not math.isfinite(delay):
            return MAX_RETRY_AFTER_SECONDS
        return min(max(delay, 0.1), MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 401:
            raise AuthenticationFailed("UniFi rejected the API key")
        if status == 403:
            raise PermissionDenied(f"The API key cannot perform {operation}")
        if status == 404:
            raise ResourceNotFound(f"UniFi does not expose {operation}")
        if status == 429:
            raise RateLimited(response.headers.get("Retry-After"))
        raise ApiError(status, operation)
