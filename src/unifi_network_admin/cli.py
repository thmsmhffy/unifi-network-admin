"""Human-facing command line interface."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .client import UniFiClient
from .config import Profile, ProfileStore, validate_profile_name
from .credentials import CredentialStore, profile_environment_key
from .errors import CredentialError, UniFiError
from .models import ConnectionMode, DiscoveryReport, ResourceList, Site, WritePolicy
from .runtime import make_client
from .site_manager import SiteManagerClient

app = typer.Typer(
    name="unifi-admin",
    help="Inspect a UniFi Network deployment without changing it.",
    no_args_is_help=True,
)
console = Console()
error_console = Console(stderr=True)

ProfileOption = Annotated[
    str | None,
    typer.Option(
        "--profile",
        "-p",
        help="Saved profile name; omit to use the default profile.",
    ),
]
SiteOption = Annotated[
    str | None,
    typer.Option(
        "--site",
        help="Site ID; omit only when the target is unambiguous.",
    ),
]
JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Print machine-readable JSON."),
]
InsecureTlsOption = Annotated[
    bool,
    typer.Option(
        "--allow-insecure-tls",
        help="Disable certificate checks for this command only.",
    ),
]
SkillDestinationArgument = Annotated[
    Path,
    typer.Argument(
        help="Agent skills directory; creates its unifi-network-admin child."
    ),
]


def _run(awaitable: Any) -> Any:
    try:
        return asyncio.run(awaitable)
    except (UniFiError, ValidationError, ValueError) as exc:
        error_console.print(_literal(f"Error: {exc}", style="red"))
        raise typer.Exit(1) from exc


def _as_json(value: BaseModel | list[BaseModel] | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        payload: Any = value.model_dump(mode="json")
    elif isinstance(value, list):
        payload = [item.model_dump(mode="json") for item in value]
    else:
        payload = value
    return json.dumps(payload, indent=2, sort_keys=True)


def _write_json(value: BaseModel | list[BaseModel] | dict[str, Any]) -> None:
    typer.echo(_as_json(value))


def _literal(value: Any, *, style: str | None = None) -> Text:
    text = "".join(
        char if ord(char) >= 32 and ord(char) != 127 else f"\\x{ord(char):02x}"
        for char in str(value)
    )
    return Text(text, style=style)


def _bundled_skill_path() -> Path:
    candidates = (
        Path(__file__).resolve().parents[2] / "skill" / "unifi-network-admin",
        Path(sys.prefix)
        / "share"
        / "unifi-network-admin"
        / "skill"
        / "unifi-network-admin",
    )
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise ValueError("The installed Agent Skill files could not be found")


def _print_sites(sites: list[Site]) -> None:
    table = Table(title="UniFi sites")
    table.add_column("Name")
    table.add_column("Site ID")
    table.add_column("Internal reference")
    for site in sites:
        table.add_row(
            _literal(site.name),
            _literal(site.id),
            _literal(site.internal_reference or ""),
        )
    console.print(table)


def _print_resources(result: ResourceList) -> None:
    table = Table(title=f"{result.kind.replace('_', ' ').title()} ({result.count})")
    table.add_column("Name")
    table.add_column("ID")
    table.add_column("Details")
    for item in result.items:
        preferred = (
            "state",
            "model",
            "ip_address",
            "mac_address",
            "vlan_id",
            "enabled",
            "firmware_version",
        )
        details = ", ".join(
            f"{key}={item.facts[key]}" for key in preferred if item.facts.get(key) is not None
        )
        table.add_row(_literal(item.name), _literal(item.id), _literal(details))
    console.print(table)


async def _discover_with(
    profile: Profile, api_key: str, *, allow_insecure_tls: bool
) -> DiscoveryReport:
    async with UniFiClient(
        profile, api_key, allow_insecure_tls=allow_insecure_tls
    ) as client:
        return await client.discover()


async def _remote_hosts(api_key: str) -> list[dict[str, Any]]:
    async with SiteManagerClient(api_key) as client:
        return await client.list_hosts()


def _host_id(host: dict[str, Any]) -> str | None:
    value = host.get("id") or host.get("hostId")
    return str(value) if value else None


def _host_name(host: dict[str, Any]) -> str:
    reported = host.get("reportedState")
    if isinstance(reported, dict):
        for key in ("hostname", "name"):
            if reported.get(key):
                return str(reported[key])
    return str(host.get("name") or _host_id(host) or "unnamed")


@app.command()
def setup(
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="Lowercase profile name using letters, numbers, or hyphens.",
    ),
    mode: str | None = typer.Option(None, help="local or remote"),
    url: str | None = typer.Option(None, help="Local console origin, including https://"),
    console_id: str | None = typer.Option(None, help="Remote Site Manager console ID."),
    ca_bundle: Path | None = typer.Option(  # noqa: B008
        None, help="CA file for a local console certificate."
    ),
    allow_insecure_tls: bool = typer.Option(
        False,
        "--allow-insecure-tls",
        help="Skip certificate checks for this setup run only.",
    ),
    no_store_key: bool = typer.Option(
        False,
        help="Do not save the key in the OS credential store.",
    ),
    make_default: bool = typer.Option(False, help="Use this profile when --profile is omitted."),
) -> None:
    """Create a profile, test it, and store its API key securely."""
    try:
        validate_profile_name(profile)
        selected_mode = (mode or typer.prompt("Connection type", default="local")).lower()
        connection = ConnectionMode(selected_mode)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    api_key = (
        os.getenv(profile_environment_key(profile))
        or os.getenv("UNIFI_API_KEY")
        or typer.prompt("UniFi API key", hide_input=True)
    )
    if connection is ConnectionMode.REMOTE:
        if url and url != "https://api.ui.com":
            raise typer.BadParameter("Remote mode always uses https://api.ui.com")
        url = "https://api.ui.com"
        if not console_id:
            hosts = _run(_remote_hosts(api_key))
            choices = [
                (identifier, _host_name(host))
                for host in hosts
                if (identifier := _host_id(host))
            ]
            if not choices:
                raise typer.BadParameter("Site Manager returned no consoles for this key")
            table = Table(title="Available UniFi consoles")
            table.add_column("Name")
            table.add_column("Console ID")
            for identifier, name in choices:
                table.add_row(_literal(name), _literal(identifier))
            console.print(table)
            console_id = choices[0][0] if len(choices) == 1 else typer.prompt("Console ID")
    else:
        url = url or typer.prompt("Console URL")

    if allow_insecure_tls:
        error_console.print(
            "[yellow]Warning:[/yellow] TLS verification is disabled for this setup run. "
            "Use a CA bundle for routine access."
        )
    if ca_bundle is not None:
        ca_bundle = ca_bundle.expanduser().resolve()
    candidate = Profile(
        name=profile,
        mode=connection,
        url=url,
        console_id=console_id,
        ca_bundle=ca_bundle,
    )
    with console.status("Checking the UniFi API..."):
        report = _run(
            _discover_with(candidate, api_key, allow_insecure_tls=allow_insecure_tls)
        )

    ProfileStore().put(candidate, make_default=make_default)
    stored = False
    if not no_store_key:
        try:
            CredentialStore().set(profile, api_key)
            stored = True
        except CredentialError as exc:
            error_console.print(_literal(exc, style="yellow"))

    console.print(
        _literal(
            f"Connected to UniFi Network {report.application_version or 'version unknown'}; "
            f"found {len(report.sites)} site(s)."
        )
    )
    if stored:
        console.print("The API key is in the OS credential store, not the profile file.")
    else:
        console.print("Set UNIFI_API_KEY before running commands for this profile.")
    if allow_insecure_tls:
        console.print(
            "Future commands also need --allow-insecure-tls until you configure a CA bundle."
        )


@app.command("profiles")
def list_profiles() -> None:
    """List saved profile names. Profile files never contain API keys."""
    store = ProfileStore()
    document = store.load()
    table = Table(title="UniFi profiles")
    table.add_column("Name")
    table.add_column("Mode")
    table.add_column("URL")
    table.add_column("Default")
    for name in sorted(document.profiles):
        item = document.profiles[name]
        table.add_row(
            _literal(name),
            _literal(item.mode.value),
            _literal(item.url),
            _literal("yes" if name == document.default_profile else ""),
        )
    console.print(table)


@app.command("export-skill")
def export_skill(destination: SkillDestinationArgument) -> None:
    """Copy the bundled Agent Skill into an agent's skills directory."""
    source = _bundled_skill_path()
    target = destination.expanduser().resolve() / source.name
    if target.exists():
        raise typer.BadParameter(f"Destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    console.print(_literal(f"Copied the Agent Skill to {target}"))


async def _report(profile: str | None, allow_insecure_tls: bool) -> DiscoveryReport:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        return await client.discover()


@app.command()
def doctor(
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Check credentials, API reachability, sites, and read capabilities."""
    report = _run(_report(profile, allow_insecure_tls))
    _print_report(report)


def _print_report(report: DiscoveryReport) -> None:
    console.print(_literal(f"Profile: {report.profile}"))
    console.print(_literal(f"Connection: {report.connection.value}"))
    console.print(_literal(f"Network version: {report.application_version or 'not reported'}"))
    console.print(_literal(f"Sites: {len(report.sites)}"))
    available = sum(item.state.value == "available" for item in report.capabilities)
    console.print(
        _literal(f"Verified read capabilities: {available}/{len(report.capabilities)}")
    )
    if report.limitations:
        console.print("Limits:")
        for item in report.limitations:
            console.print(_literal(f"  - {item}"))


@app.command()
def discover(
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Return the controller version, sites, and verified endpoint capabilities."""
    report = _run(_report(profile, allow_insecure_tls))
    if json_output:
        _write_json(report)
        return
    _print_report(report)


async def _sites(profile: str | None, allow_insecure_tls: bool) -> list[Site]:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        return await client.list_sites()


@app.command()
def sites(
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List every site returned by the selected Network application."""
    result = _run(_sites(profile, allow_insecure_tls))
    _write_json(result) if json_output else _print_sites(result)


async def _resolve_site(client: UniFiClient, site_id: str | None) -> str:
    if site_id:
        return site_id
    sites_result = await client.list_sites()
    if len(sites_result) == 1:
        return sites_result[0].id
    if not sites_result:
        raise ValueError("No UniFi sites are available")
    options = ", ".join(f"{item.name}={item.id}" for item in sites_result)
    raise ValueError(f"More than one site is available; pass --site. Choices: {options}")


async def _resources(
    kind: str, profile: str | None, site_id: str | None, allow_insecure_tls: bool
) -> ResourceList:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        selected = await _resolve_site(client, site_id)
        return await client.list_resources(kind, selected)


async def _resource_details(
    kind: str,
    resource_id: str,
    profile: str | None,
    site_id: str | None,
    allow_insecure_tls: bool,
) -> BaseModel:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        selected = await _resolve_site(client, site_id)
        return await client.get_resource(kind, selected, resource_id)


async def _device_statistics(
    device_id: str,
    profile: str | None,
    site_id: str | None,
    allow_insecure_tls: bool,
) -> BaseModel:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        selected = await _resolve_site(client, site_id)
        return await client.get_device_statistics(selected, device_id)


def _resource_output(
    kind: str,
    profile: str | None,
    site_id: str | None,
    json_output: bool,
    allow_insecure_tls: bool,
) -> None:
    result = _run(_resources(kind, profile, site_id, allow_insecure_tls))
    _write_json(result) if json_output else _print_resources(result)


@app.command()
def devices(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List adopted devices."""
    _resource_output("devices", profile, site_id, json_output, allow_insecure_tls)


@app.command()
def device(
    device_id: str,
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Get one adopted device with its returned interface and uplink details."""
    result = _run(
        _resource_details("devices", device_id, profile, site_id, allow_insecure_tls)
    )
    _write_json(result)


@app.command("device-stats")
def device_stats(
    device_id: str,
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Get the latest statistics exposed for one adopted device."""
    result = _run(
        _device_statistics(device_id, profile, site_id, allow_insecure_tls)
    )
    _write_json(result)


@app.command()
def clients(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List currently connected clients."""
    _resource_output("clients", profile, site_id, json_output, allow_insecure_tls)


@app.command()
def client(
    client_id: str,
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Get one currently connected client."""
    result = _run(
        _resource_details("clients", client_id, profile, site_id, allow_insecure_tls)
    )
    _write_json(result)


@app.command()
def networks(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List configured networks and VLAN IDs."""
    _resource_output("networks", profile, site_id, json_output, allow_insecure_tls)


@app.command()
def wifi(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List Wi-Fi broadcasts."""
    _resource_output("wifi_broadcasts", profile, site_id, json_output, allow_insecure_tls)


@app.command()
def firewall(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List firewall policies."""
    _resource_output("firewall_policies", profile, site_id, json_output, allow_insecure_tls)


@app.command()
def wans(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    json_output: JsonOption = False,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """List WAN interface definitions."""
    _resource_output("wans", profile, site_id, json_output, allow_insecure_tls)


async def _snapshot(
    profile: str | None, site_id: str | None, allow_insecure_tls: bool
) -> BaseModel:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        return await client.snapshot([site_id] if site_id else None)


@app.command()
def snapshot(
    site_id: str | None = typer.Option(None, "--site", help="Omit to include every site."),
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Print a JSON snapshot of current inventory and configuration."""
    _write_json(_run(_snapshot(profile, site_id, allow_insecure_tls)))


async def _topology(
    profile: str | None, site_id: str | None, allow_insecure_tls: bool
) -> BaseModel:
    async with make_client(profile, allow_insecure_tls=allow_insecure_tls) as client:
        selected = await _resolve_site(client, site_id)
        return await client.topology(selected)


@app.command()
def topology(
    site_id: SiteOption = None,
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Return verified nodes and clearly labeled inferred links as JSON."""
    _write_json(_run(_topology(profile, site_id, allow_insecure_tls)))


@app.command("write-policy")
def write_policy() -> None:
    """Explain the enforced mutation policy for this release."""
    _write_json(WritePolicy())


@app.command()
def mcp(
    profile: ProfileOption = None,
    allow_insecure_tls: InsecureTlsOption = False,
) -> None:
    """Run the MCP server over stdio for one selected profile."""
    from .mcp_server import run_server

    run_server(profile_name=profile, allow_insecure_tls=allow_insecure_tls)


if __name__ == "__main__":
    app()
