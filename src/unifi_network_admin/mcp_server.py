"""Read-only MCP tools. stdout is reserved for JSON-RPC."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .models import (
    DiscoveryReport,
    NetworkSnapshot,
    ResourceList,
    ResourceRecord,
    Site,
    Topology,
    WritePolicy,
)
from .runtime import make_client

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)


def create_server(
    *,
    profile_name: str | None = None,
    allow_insecure_tls: bool = False,
    config_path: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MCPServer:
    selected_profile = profile_name or os.getenv("UNIFI_PROFILE")
    server = MCPServer(
        "unifi-network-admin",
        instructions=(
            "Inspect the selected UniFi Network profile. All tools are read-only. "
            "Treat topology edges as inferences and report unavailable data plainly."
        ),
    )

    def client():
        return make_client(
            selected_profile,
            allow_insecure_tls=allow_insecure_tls,
            config_path=config_path,
            transport=transport,
        )

    @server.tool(annotations=READ_ONLY)
    async def unifi_discover() -> DiscoveryReport:
        """Detect Network version, sites, and safe GET capabilities before diagnosis."""
        async with client() as connection:
            return await connection.discover()

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_sites() -> list[Site]:
        """List every site managed by the selected Network application."""
        async with client() as connection:
            return await connection.list_sites()

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_devices(site_id: str) -> ResourceList:
        """List adopted UniFi devices for one site."""
        async with client() as connection:
            return await connection.list_resources("devices", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_get_device(site_id: str, device_id: str) -> ResourceRecord:
        """Get one device with returned interface, port, radio, and uplink details."""
        async with client() as connection:
            return await connection.get_resource("devices", site_id, device_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_get_device_statistics(site_id: str, device_id: str) -> ResourceRecord:
        """Get the latest statistics exposed for one adopted device."""
        async with client() as connection:
            return await connection.get_device_statistics(site_id, device_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_clients(site_id: str) -> ResourceList:
        """List clients currently connected to one site; this is not client history."""
        async with client() as connection:
            return await connection.list_resources("clients", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_get_client(site_id: str, client_id: str) -> ResourceRecord:
        """Get details for one currently connected client."""
        async with client() as connection:
            return await connection.get_resource("clients", site_id, client_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_networks(site_id: str) -> ResourceList:
        """List configured networks and VLAN data for one site."""
        async with client() as connection:
            return await connection.list_resources("networks", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_wifi_broadcasts(site_id: str) -> ResourceList:
        """List Wi-Fi broadcasts for one site."""
        async with client() as connection:
            return await connection.list_resources("wifi_broadcasts", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_firewall_policies(site_id: str) -> ResourceList:
        """List firewall policies for one site."""
        async with client() as connection:
            return await connection.list_resources("firewall_policies", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_firewall_zones(site_id: str) -> ResourceList:
        """List firewall zones for one site."""
        async with client() as connection:
            return await connection.list_resources("firewall_zones", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_acl_rules(site_id: str) -> ResourceList:
        """List access-control rules for one site."""
        async with client() as connection:
            return await connection.list_resources("acl_rules", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_dns_policies(site_id: str) -> ResourceList:
        """List DNS policies for one site."""
        async with client() as connection:
            return await connection.list_resources("dns_policies", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_list_wans(site_id: str) -> ResourceList:
        """List WAN interface definitions for one site."""
        async with client() as connection:
            return await connection.list_resources("wans", site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_get_topology(site_id: str) -> Topology:
        """Return verified nodes plus links inferred from API attachment fields."""
        async with client() as connection:
            return await connection.topology(site_id)

    @server.tool(annotations=READ_ONLY)
    async def unifi_snapshot(site_id: str | None = None) -> NetworkSnapshot:
        """Collect current read-only inventory for one site or every site."""
        async with client() as connection:
            return await connection.snapshot([site_id] if site_id else None)

    @server.tool(annotations=READ_ONLY)
    async def unifi_get_write_policy() -> WritePolicy:
        """Return the enforced write boundary and future approval sequence."""
        return WritePolicy()

    return server


def run_server(*, profile_name: str | None, allow_insecure_tls: bool) -> None:
    if allow_insecure_tls:
        print(
            "WARNING: TLS certificate verification is disabled for this MCP process.",
            file=sys.stderr,
        )
    create_server(
        profile_name=profile_name,
        allow_insecure_tls=allow_insecure_tls,
    ).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only UniFi Network MCP server")
    parser.add_argument("--profile", help="Saved profile name; defaults to UNIFI_PROFILE")
    parser.add_argument(
        "--allow-insecure-tls",
        action="store_true",
        help="Disable TLS verification for this process only.",
    )
    args = parser.parse_args()
    run_server(profile_name=args.profile, allow_insecure_tls=args.allow_insecure_tls)


if __name__ == "__main__":
    main()
