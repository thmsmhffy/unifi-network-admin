"""Resolve one profile and credential without exposing either to MCP tools."""

from __future__ import annotations

from pathlib import Path

import httpx

from .client import UniFiClient
from .config import ProfileStore, load_profile
from .credentials import CredentialStore


def make_client(
    profile_name: str | None = None,
    *,
    allow_insecure_tls: bool = False,
    config_path: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UniFiClient:
    store = ProfileStore(config_path) if config_path else ProfileStore()
    profile = load_profile(profile_name, store=store)
    api_key = CredentialStore().get(profile.name)
    return UniFiClient(
        profile,
        api_key,
        allow_insecure_tls=allow_insecure_tls,
        transport=transport,
    )
