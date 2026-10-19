"""Async client for documented UniFi Network Integration API read endpoints."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import Profile, safe_segment
from .errors import (
    ApiError,
    ConfigurationError,
    ConnectionFailed,
    InvalidResponse,
    PermissionDenied,
    RateLimited,
    ResourceNotFound,
)
from .models import (
    Capability,
    CapabilityState,
    ConnectionMode,
    DiscoveryReport,
    Evidence,
    NetworkSnapshot,
    ResourceList,
    ResourceRecord,
    Site,
    SiteSnapshot,
    Topology,
    TopologyEdge,
    TopologyNode,
)
from .normalize import normalize_resource, normalize_site
from .transport import ReadOnlyTransport, tls_verification

PAGE_SIZE = 200
MAX_RECORDS = 10_000
MAX_TOPOLOGY_DEVICE_DETAILS = 50

RESOURCE_ENDPOINTS: dict[str, str] = {
    "devices": "/v1/sites/{site_id}/devices",
    "clients": "/v1/sites/{site_id}/clients",
    "networks": "/v1/sites/{site_id}/networks",
    "wifi_broadcasts": "/v1/sites/{site_id}/wifi/broadcasts",
    "firewall_policies": "/v1/sites/{site_id}/firewall/policies",
    "firewall_zones": "/v1/sites/{site_id}/firewall/zones",
    "acl_rules": "/v1/sites/{site_id}/acl-rules",
    "dns_policies": "/v1/sites/{site_id}/dns/policies",
    "traffic_matching_lists": "/v1/sites/{site_id}/traffic-matching-lists",
    "switch_lags": "/v1/sites/{site_id}/switching/lags",
    "switch_stacks": "/v1/sites/{site_id}/switching/switch-stacks",
    "wans": "/v1/sites/{site_id}/wans",
    "vpn_servers": "/v1/sites/{site_id}/vpn/servers",
    "site_to_site_vpn_tunnels": "/v1/sites/{site_id}/vpn/site-to-site-tunnels",
    "radius_profiles": "/v1/sites/{site_id}/radius/profiles",
    "device_tags": "/v1/sites/{site_id}/device-tags",
}

DETAIL_ENDPOINTS: dict[str, str] = {
    "devices": "/v1/sites/{site_id}/devices/{resource_id}",
    "clients": "/v1/sites/{site_id}/clients/{resource_id}",
    "networks": "/v1/sites/{site_id}/networks/{resource_id}",
    "firewall_policies": "/v1/sites/{site_id}/firewall/policies/{resource_id}",
    "firewall_zones": "/v1/sites/{site_id}/firewall/zones/{resource_id}",
}

DETAIL_DISCOVERY_ENDPOINTS = (
    ("device_details", "devices", DETAIL_ENDPOINTS["devices"]),
    (
        "device_statistics",
        "devices",
        "/v1/sites/{site_id}/devices/{resource_id}/statistics/latest",
    ),
    ("client_details", "clients", DETAIL_ENDPOINTS["clients"]),
)

DISCOVERY_KINDS = (
    "devices",
    "clients",
    "networks",
    "wifi_broadcasts",
    "firewall_policies",
    "firewall_zones",
    "acl_rules",
    "dns_policies",
    "wans",
)

SNAPSHOT_KINDS = (
    "devices",
    "clients",
    "networks",
    "wifi_broadcasts",
    "firewall_policies",
    "firewall_zones",
    "wans",
)


class UniFiClient:
    def __init__(
        self,
        profile: Profile,
        api_key: str,
        *,
        allow_insecure_tls: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.profile = profile
        origins = {
            f"{urlsplit(root).scheme}://{urlsplit(root).netloc}" for root in profile.api_roots()
        }
        self._transport = ReadOnlyTransport(
            api_key=api_key,
            allowed_origins=origins,
            timeout_seconds=profile.timeout_seconds,
            verify=tls_verification(profile.ca_bundle, allow_insecure_tls=allow_insecure_tls),
            transport=transport,
            max_rate_limit_retries=(
                2 if profile.mode is ConnectionMode.REMOTE else 0
            ),
        )
        self._api_root: str | None = None
        self._application_version: str | None = None

    async def __aenter__(self) -> UniFiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._transport.close()

    @property
    def api_root(self) -> str:
        if not self._api_root:
            raise RuntimeError("The client has not completed discovery")
        return self._api_root

    async def get_application_info(self) -> dict[str, Any]:
        await self._ensure_api_root()
        return {"applicationVersion": self._application_version}

    async def list_sites(self) -> list[Site]:
        await self._ensure_api_root()
        records = await self._all_pages("/v1/sites", operation="list sites")
        return [normalize_site(item) for item in records]

    async def list_resources(self, kind: str, site_id: str) -> ResourceList:
        try:
            template = RESOURCE_ENDPOINTS[kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported resource kind: {kind}") from exc
        site = safe_segment(site_id, "site ID")
        path = template.format(site_id=site)
        records = await self._all_pages(path, operation=f"list {kind}")
        items = [normalize_resource(kind, site_id, item) for item in records]
        return ResourceList(kind=kind, site_id=site_id, count=len(items), items=items)

    async def get_resource(
        self, kind: str, site_id: str, resource_id: str
    ) -> ResourceRecord:
        try:
            template = DETAIL_ENDPOINTS[kind]
        except KeyError as exc:
            raise ValueError(f"Resource details are not supported for: {kind}") from exc
        site = safe_segment(site_id, "site ID")
        resource = safe_segment(resource_id, f"{kind} ID")
        path = template.format(site_id=site, resource_id=resource)
        payload = await self._get(path, operation=f"get {kind} details")
        return normalize_resource(kind, site_id, payload)

    async def get_device_statistics(self, site_id: str, device_id: str) -> ResourceRecord:
        site = safe_segment(site_id, "site ID")
        device = safe_segment(device_id, "device ID")
        payload = await self._get(
            f"/v1/sites/{site}/devices/{device}/statistics/latest",
            operation="get latest device statistics",
        )
        normalized = dict(payload)
        normalized.setdefault("id", device_id)
        normalized.setdefault("name", f"Latest statistics for {device_id}")
        return normalize_resource("device_statistics", site_id, normalized)

    async def discover(self) -> DiscoveryReport:
        await self._ensure_api_root()
        sites = await self.list_sites()
        capabilities = [
            Capability(
                name="application_info",
                state=CapabilityState.AVAILABLE,
                endpoint="GET /v1/info",
                evidence=Evidence.VERIFIED,
            ),
            Capability(
                name="sites",
                state=CapabilityState.AVAILABLE,
                endpoint="GET /v1/sites",
                evidence=Evidence.VERIFIED,
            ),
        ]
        limitations: list[str] = []
        if sites:
            capabilities.extend(await self._probe_site(sites[0].id))
            if len(sites) > 1:
                limitations.append(
                    "Resource capabilities were probed on the first site; "
                    "access can still vary by site."
                )
        else:
            limitations.append("No sites were returned, so site-scoped capabilities are unknown.")
            for kind in DISCOVERY_KINDS:
                capabilities.append(
                    Capability(
                        name=kind,
                        state=CapabilityState.UNKNOWN,
                        endpoint=f"GET {RESOURCE_ENDPOINTS[kind]}",
                        evidence=Evidence.UNAVAILABLE,
                        detail="No site ID was available for a safe probe.",
                    )
                )
        limitations.append(
            "Connected-client results are live state, not an offline or historical "
            "client inventory."
        )
        return DiscoveryReport(
            profile=self.profile.name,
            connection=self.profile.mode,
            application_version=self._application_version,
            api_root=self.api_root,
            sites=sites,
            capabilities=capabilities,
            limitations=limitations,
        )

    async def snapshot(self, site_ids: Iterable[str] | None = None) -> NetworkSnapshot:
        await self._ensure_api_root()
        all_sites = await self.list_sites()
        selected_ids = set(site_ids) if site_ids is not None else {site.id for site in all_sites}
        selected = [site for site in all_sites if site.id in selected_ids]
        missing = selected_ids - {site.id for site in selected}
        if missing:
            raise ValueError(f"Unknown site ID(s): {', '.join(sorted(missing))}")

        snapshots: list[SiteSnapshot] = []
        for site in selected:
            resources: dict[str, list] = {}
            unavailable: dict[str, str] = {}
            for kind in SNAPSHOT_KINDS:
                try:
                    result = await self.list_resources(kind, site.id)
                    resources[kind] = result.items
                except (PermissionDenied, ResourceNotFound) as exc:
                    unavailable[kind] = str(exc)
            snapshots.append(SiteSnapshot(site=site, resources=resources, unavailable=unavailable))
        return NetworkSnapshot(
            profile=self.profile.name,
            application_version=self._application_version,
            sites=snapshots,
            limitations=[
                "The snapshot contains current API results only; it is not a historical database."
            ],
        )

    async def topology(self, site_id: str) -> Topology:
        devices = await self.list_resources("devices", site_id)
        clients = await self.list_resources("clients", site_id)
        device_details: dict[str, ResourceRecord] = {}
        limitations: list[str] = []
        for item in devices.items[:MAX_TOPOLOGY_DEVICE_DETAILS]:
            try:
                device_details[item.id] = await self.get_resource(
                    "devices", site_id, item.id
                )
            except ResourceNotFound:
                continue
            except PermissionDenied:
                limitations.append(
                    "Device details were forbidden, so device-to-device uplinks "
                    "could not be inferred."
                )
                break
        if len(devices.items) > MAX_TOPOLOGY_DEVICE_DETAILS:
            limitations.append(
                "Device-detail lookups were limited to the first "
                f"{MAX_TOPOLOGY_DEVICE_DETAILS} devices to bound API use."
            )
        nodes = [
            TopologyNode(
                id=item.id,
                label=item.name,
                kind="device",
                facts=device_details.get(item.id, item).facts,
            )
            for item in devices.items
        ] + [
            TopologyNode(id=item.id, label=item.name, kind="client", facts=item.facts)
            for item in clients.items
        ]
        device_ids = {item.id for item in devices.items}
        edges: list[TopologyEdge] = []
        for item in device_details.values():
            uplink = item.facts.get("uplink")
            parent = uplink.get("device_id") if isinstance(uplink, dict) else None
            if isinstance(parent, str) and parent in device_ids and parent != item.id:
                edges.append(
                    TopologyEdge(
                        source=parent,
                        target=item.id,
                        relationship="reported attachment",
                        basis="device detail field uplink.deviceId",
                    )
                )
        for item in clients.items:
            parent = item.facts.get("uplink_device_id")
            if isinstance(parent, str) and parent in device_ids:
                edges.append(
                    TopologyEdge(
                        source=parent,
                        target=item.id,
                        relationship="reported attachment",
                        basis="client field uplinkDeviceId",
                    )
                )
        if not edges:
            limitations.append(
                "The documented device-detail and client attachment fields did not "
                "identify any links."
            )
        limitations.append(
            "Edges are inferences from returned attachment fields, not a topology API."
        )
        return Topology(site_id=site_id, nodes=nodes, edges=edges, limitations=limitations)

    async def _ensure_api_root(self) -> None:
        if self._api_root:
            return
        last_not_found: ResourceNotFound | None = None
        for root in self.profile.api_roots():
            try:
                payload = await self._transport.request_json(
                    "GET", f"{root}/v1/info", operation="get application info"
                )
            except ResourceNotFound as exc:
                last_not_found = exc
                continue
            version = payload.get("applicationVersion")
            if not isinstance(version, str) or not version.strip():
                raise InvalidResponse(
                    "UniFi application info is missing a valid applicationVersion"
                )
            self._api_root = root
            self._application_version = version
            return
        raise last_not_found or ResourceNotFound("UniFi Network Integration API was not found")

    async def _all_pages(self, path: str, *, operation: str) -> list[dict[str, Any]]:
        await self._ensure_api_root()
        output: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = await self._transport.request_json(
                "GET",
                f"{self.api_root}{path}",
                operation=operation,
                params={"offset": offset, "limit": PAGE_SIZE},
            )
            data = payload.get("data")
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise InvalidResponse(f"UniFi returned an invalid page for {operation}")
            output.extend(data)
            if len(output) > MAX_RECORDS:
                raise InvalidResponse(f"{operation} exceeded the {MAX_RECORDS}-record safety limit")
            total = payload.get("totalCount")
            if not data or (isinstance(total, int) and len(output) >= total):
                break
            offset += len(data)
            if not isinstance(total, int) and len(data) < PAGE_SIZE:
                break
        return output

    async def _get(self, path: str, *, operation: str) -> dict[str, Any]:
        await self._ensure_api_root()
        return await self._transport.request_json(
            "GET", f"{self.api_root}{path}", operation=operation
        )

    async def _probe_site(self, site_id: str) -> list[Capability]:
        capabilities: list[Capability] = []
        sample_ids: dict[str, str] = {}
        site = safe_segment(site_id, "site ID")
        for index, kind in enumerate(DISCOVERY_KINDS):
            path = RESOURCE_ENDPOINTS[kind].format(site_id=site)
            endpoint = f"GET {RESOURCE_ENDPOINTS[kind]}"
            capability, payload, stop = await self._probe_get(
                name=kind,
                endpoint=endpoint,
                path=path,
                operation=f"probe {kind}",
                params={"offset": 0, "limit": 1},
            )
            if capability.state is CapabilityState.AVAILABLE:
                data = payload.get("data") if payload else None
                if not isinstance(data, list):
                    capability = Capability(
                        name=kind,
                        state=CapabilityState.UNKNOWN,
                        endpoint=endpoint,
                        evidence=Evidence.UNAVAILABLE,
                        detail="The endpoint returned an invalid collection shape.",
                    )
                elif data and isinstance(data[0], dict):
                    identifier = data[0].get("id")
                    if isinstance(identifier, str) and identifier:
                        sample_ids[kind] = identifier
            capabilities.append(capability)
            if stop:
                for remaining in DISCOVERY_KINDS[index + 1 :]:
                    capabilities.append(
                        Capability(
                            name=remaining,
                            state=CapabilityState.UNKNOWN,
                            endpoint=f"GET {RESOURCE_ENDPOINTS[remaining]}",
                            evidence=Evidence.UNAVAILABLE,
                            detail="Not probed after a connection or rate-limit failure.",
                        )
                    )
                for detail_name, _, detail_template in DETAIL_DISCOVERY_ENDPOINTS:
                    capabilities.append(
                        Capability(
                            name=detail_name,
                            state=CapabilityState.UNKNOWN,
                            endpoint=f"GET {detail_template}",
                            evidence=Evidence.UNAVAILABLE,
                            detail="Not probed after a connection or rate-limit failure.",
                        )
                    )
                return capabilities

        for index, (name, kind, template) in enumerate(DETAIL_DISCOVERY_ENDPOINTS):
            endpoint = f"GET {template}"
            identifier = sample_ids.get(kind)
            if not identifier:
                capabilities.append(
                    Capability(
                        name=name,
                        state=CapabilityState.UNKNOWN,
                        endpoint=endpoint,
                        evidence=Evidence.UNAVAILABLE,
                        detail=f"No {kind} ID was available for a safe probe.",
                    )
                )
                continue
            try:
                resource = safe_segment(identifier, f"{kind} ID")
            except ConfigurationError:
                capabilities.append(
                    Capability(
                        name=name,
                        state=CapabilityState.UNKNOWN,
                        endpoint=endpoint,
                        evidence=Evidence.UNAVAILABLE,
                        detail=f"The sampled {kind} ID was not safe to use in a path.",
                    )
                )
                continue
            path = template.format(site_id=site, resource_id=resource)
            capability, _, stop = await self._probe_get(
                name=name,
                endpoint=endpoint,
                path=path,
                operation=f"probe {name}",
                not_found_is_unsupported=False,
            )
            capabilities.append(capability)
            if stop:
                for remaining_name, _, remaining_template in DETAIL_DISCOVERY_ENDPOINTS[
                    index + 1 :
                ]:
                    capabilities.append(
                        Capability(
                            name=remaining_name,
                            state=CapabilityState.UNKNOWN,
                            endpoint=f"GET {remaining_template}",
                            evidence=Evidence.UNAVAILABLE,
                            detail="Not probed after a connection or rate-limit failure.",
                        )
                    )
                break
        return capabilities

    async def _probe_get(
        self,
        *,
        name: str,
        endpoint: str,
        path: str,
        operation: str,
        params: dict[str, str | int] | None = None,
        not_found_is_unsupported: bool = True,
    ) -> tuple[Capability, dict[str, Any] | None, bool]:
        stop = False
        try:
            payload = await self._transport.request_json(
                "GET",
                f"{self.api_root}{path}",
                operation=operation,
                params=params,
            )
        except PermissionDenied:
            state = CapabilityState.FORBIDDEN
            evidence = Evidence.VERIFIED
            detail = "The endpoint exists, but the API key was denied."
            payload = None
        except ResourceNotFound:
            if not_found_is_unsupported:
                state = CapabilityState.UNSUPPORTED
                evidence = Evidence.VERIFIED
                detail = "The endpoint returned HTTP 404."
            else:
                state = CapabilityState.UNKNOWN
                evidence = Evidence.UNAVAILABLE
                detail = (
                    "The sampled resource returned HTTP 404, so route support "
                    "could not be determined."
                )
            payload = None
        except ApiError as exc:
            if exc.status_code == 405:
                state = CapabilityState.UNSUPPORTED
                evidence = Evidence.VERIFIED
                detail = "The endpoint returned HTTP 405."
            else:
                state = CapabilityState.UNKNOWN
                evidence = Evidence.UNAVAILABLE
                detail = str(exc)
            payload = None
        except InvalidResponse as exc:
            state = CapabilityState.UNKNOWN
            evidence = Evidence.UNAVAILABLE
            detail = str(exc)
            payload = None
        except (ConnectionFailed, RateLimited) as exc:
            state = CapabilityState.UNKNOWN
            evidence = Evidence.UNAVAILABLE
            detail = str(exc)
            payload = None
            stop = True
        else:
            state = CapabilityState.AVAILABLE
            evidence = Evidence.VERIFIED
            detail = None
        return (
            Capability(
                name=name,
                state=state,
                endpoint=endpoint,
                evidence=evidence,
                detail=detail,
            ),
            payload,
            stop,
        )
