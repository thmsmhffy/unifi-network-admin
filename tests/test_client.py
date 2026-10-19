from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from unifi_network_admin.client import UniFiClient
from unifi_network_admin.config import Profile
from unifi_network_admin.errors import InvalidResponse
from unifi_network_admin.models import CapabilityState


def response_for(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    query = parse_qs(request.url.query.decode())
    if path == "/proxy/network/integration/v1/info":
        return httpx.Response(200, json={"applicationVersion": "10.6.106"})
    if path == "/proxy/network/integration/v1/sites":
        return httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 200,
                "count": 1,
                "totalCount": 1,
                "data": [{"id": "site-1", "name": "Main", "internalReference": "default"}],
            },
        )
    if path.endswith("/devices"):
        offset = int(query.get("offset", ["0"])[0])
        data = (
            [
                {
                    "id": "device-1",
                    "name": "Core Switch",
                    "model": "USW",
                    "state": "ONLINE",
                },
                {
                    "id": "device-2",
                    "name": "Access Point",
                    "model": "U7",
                    "state": "ONLINE",
                },
            ]
            if offset == 0
            else []
        )
        return httpx.Response(
            200,
            json={
                "offset": offset,
                "limit": 200,
                "count": len(data),
                "totalCount": 2,
                "data": data,
            },
        )
    if path.endswith("/clients"):
        return httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 200,
                "count": 1,
                "totalCount": 1,
                "data": [
                    {
                        "id": "client-1",
                        "name": "Laptop",
                        "ipAddress": "192.168.1.10",
                        "uplinkDeviceId": "device-2",
                    }
                ],
            },
        )
    if path.endswith("/devices/device-1"):
        return httpx.Response(
            200,
            json={
                "id": "device-1",
                "name": "Core Switch",
                "model": "USW",
                "interfaces": {"ports": [{"idx": 1, "speedMbps": 1000}]},
                "uplink": None,
            },
        )
    if path.endswith("/devices/device-2"):
        return httpx.Response(
            200,
            json={
                "id": "device-2",
                "name": "Access Point",
                "model": "U7",
                "uplink": {"deviceId": "device-1"},
            },
        )
    if path.endswith("/devices/device-1/statistics/latest"):
        return httpx.Response(200, json={"cpuUtilizationPct": 12.5})
    if path.endswith("/clients/client-1"):
        return httpx.Response(
            200,
            json={"id": "client-1", "name": "Laptop", "ipAddress": "192.168.1.10"},
        )
    if path.endswith("/networks"):
        return httpx.Response(403)
    if path.endswith("/wifi/broadcasts"):
        return httpx.Response(404)
    return httpx.Response(
        200,
        json={"offset": 0, "limit": 200, "count": 0, "totalCount": 0, "data": []},
    )


@pytest.fixture
def profile() -> Profile:
    return Profile(name="test", mode="local", url="https://console.test")


@pytest.mark.anyio
async def test_discovery_verifies_capabilities_without_guessing(profile) -> None:
    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(response_for)
    ) as client:
        report = await client.discover()

    assert report.application_version == "10.6.106"
    assert report.sites[0].id == "site-1"
    states = {item.name: item.state for item in report.capabilities}
    assert states["devices"] is CapabilityState.AVAILABLE
    assert states["networks"] is CapabilityState.FORBIDDEN
    assert states["wifi_broadcasts"] is CapabilityState.UNSUPPORTED
    assert states["device_details"] is CapabilityState.AVAILABLE
    assert states["device_statistics"] is CapabilityState.AVAILABLE
    assert states["client_details"] is CapabilityState.AVAILABLE


@pytest.mark.anyio
async def test_resources_are_normalized_and_topology_edges_are_inferred(profile) -> None:
    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(response_for)
    ) as client:
        devices = await client.list_resources("devices", "site-1")
        topology = await client.topology("site-1")

    assert devices.count == 2
    assert devices.items[0].facts["model"] == "USW"
    assert "uplink_device_id" not in devices.items[1].facts
    assert {(edge.source, edge.target) for edge in topology.edges} == {
        ("device-1", "device-2"),
        ("device-2", "client-1"),
    }
    assert all(edge.evidence.value == "inferred" for edge in topology.edges)


@pytest.mark.anyio
async def test_device_details_and_statistics_use_documented_get_paths(profile) -> None:
    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(response_for)
    ) as client:
        device = await client.get_resource("devices", "site-1", "device-1")
        statistics = await client.get_device_statistics("site-1", "device-1")

    assert device.facts["interfaces"]["ports"][0]["speed_mbps"] == 1000
    assert statistics.id == "device-1"
    assert statistics.facts["cpu_utilization_pct"] == 12.5


@pytest.mark.anyio
async def test_wifi_details_are_not_exposed_because_they_can_contain_secrets(profile) -> None:
    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(response_for)
    ) as client:
        with pytest.raises(ValueError, match="not supported"):
            await client.get_resource("wifi_broadcasts", "site-1", "wifi-1")


@pytest.mark.anyio
async def test_discovery_marks_rate_limit_unknown_and_stops_probing(profile) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
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
        return httpx.Response(429, headers={"Retry-After": "30"})

    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(handler)
    ) as client:
        report = await client.discover()

    states = {item.name: item.state for item in report.capabilities}
    assert states["devices"] is CapabilityState.UNKNOWN
    assert states["client_details"] is CapabilityState.UNKNOWN
    assert len(calls) == 3


@pytest.mark.anyio
async def test_application_info_requires_a_version(profile) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(InvalidResponse, match="applicationVersion"):
            await client.discover()


@pytest.mark.anyio
async def test_detail_probe_does_not_treat_a_missing_sample_as_unsupported(profile) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
        if request.url.path.endswith("/devices"):
            return httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 1,
                    "count": 1,
                    "totalCount": 1,
                    "data": [{"id": "gone-device", "name": "Gone"}],
                },
            )
        if "/devices/gone-device" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={"offset": 0, "limit": 1, "count": 0, "totalCount": 0, "data": []},
        )

    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(handler)
    ) as client:
        report = await client.discover()

    states = {item.name: item.state for item in report.capabilities}
    assert states["devices"] is CapabilityState.AVAILABLE
    assert states["device_details"] is CapabilityState.UNKNOWN
    assert states["device_statistics"] is CapabilityState.UNKNOWN


@pytest.mark.anyio
async def test_collection_pagination_aggregates_multiple_pages(profile) -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/info"):
            return httpx.Response(200, json={"applicationVersion": "10.6.106"})
        offset = int(parse_qs(request.url.query.decode()).get("offset", ["0"])[0])
        offsets.append(offset)
        data = (
            [{"id": f"device-{index}", "name": f"Device {index}"} for index in range(200)]
            if offset == 0
            else [{"id": "device-200", "name": "Device 200"}]
        )
        return httpx.Response(
            200,
            json={
                "offset": offset,
                "limit": 200,
                "count": len(data),
                "totalCount": 201,
                "data": data,
            },
        )

    async with UniFiClient(
        profile, "secret", transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.list_resources("devices", "site-1")

    assert result.count == 201
    assert result.items[-1].id == "device-200"
    assert offsets == [0, 200]
