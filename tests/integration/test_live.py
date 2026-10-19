from __future__ import annotations

import os

import pytest

from unifi_network_admin.client import UniFiClient
from unifi_network_admin.config import Profile


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_discovery_is_read_only() -> None:
    url = os.getenv("UNIFI_TEST_URL")
    api_key = os.getenv("UNIFI_TEST_API_KEY")
    if not url or not api_key:
        pytest.skip("Set UNIFI_TEST_URL and UNIFI_TEST_API_KEY for a live read-only test")
    profile = Profile(name="integration", mode="local", url=url)
    async with UniFiClient(profile, api_key) as client:
        report = await client.discover()
    assert report.application_version
    assert report.sites
